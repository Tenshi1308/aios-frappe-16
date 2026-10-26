import json

import frappe

from aios_v1.lib.desktop_modules import get_module_definition
from aios_v1.lib.error_utils import log_exception, safe_error
from aios_v1.lib.llm_client import chat_stream
from aios_v1.lib.tool_registry import (
    MAX_DELEGATION_DEPTH,
    ToolContextError,
    execute_tool,
    get_tools_schema_for_worker,
)
from aios_v1.lib.workspace import WorkspaceError, attach_private_files_to_message, build_attachment_context
from aios_v1.plugin_manager.registry import get_branch, get_worker, is_branch_enabled
from aios_v1.services.usage import record_token_usage_batch
from aios_v1.shared.aios_ethos import AIOS_ETHOS
from aios_v1.shared.base_persona import BASE_PERSONA
from aios_v1.shared.trace_events import (
    approval_card_artifact,
    file_artifact,
    trace_cross_branch,
    trace_delegate_start,
    trace_subagent_prompt,
    trace_subagent_result,
    trace_subagent_tool,
)

MAX_TOOL_ROUNDS = 6
TOOL_CONTEXT_ERROR_MESSAGE = "Konteks sesi untuk menjalankan tool tidak valid. Silakan mulai percakapan kembali."
MAX_TOOL_ROUNDS_MESSAGE = "Batas langkah penggunaan tool tercapai. Silakan persempit permintaan dan coba lagi."
TRUNCATION_NOTICE = "_[Jawaban terpotong karena batas output model.]_"


def _workspace_artifact_event(tool_name, result_json):
    """Event `artifact_created` FILE dari hasil `workspace_create_file`; None bila bukan/belum dibuat."""
    if tool_name != "workspace_create_file":
        return None
    try:
        payload = json.loads(result_json)
    except (TypeError, ValueError) as exc:
        log_exception("AIOS Workspace Artifact Event", exc=exc)
        return None
    if (
        not isinstance(payload, dict)
        or payload.get("status") != "created"
        or not isinstance(payload.get("artifact"), dict)
    ):
        log_exception("AIOS Workspace Artifact Event", context="payload artefak file tidak valid")
        return None
    return file_artifact(payload["artifact"])


def _approval_card_event(tool_name, result_json, branch):
    """Event `artifact_created` APPROVAL_CARD dari hasil `erpnext_action_draft_create`; None bila bukan kartu.

    Dipakai di loop manager dan loop sub-agent (fase 2a: kartu dari sub-agent
    juga harus sampai ke stream).
    """
    if tool_name != "erpnext_action_draft_create":
        return None
    try:
        payload = json.loads(result_json)
    except (TypeError, ValueError) as exc:
        log_exception("AIOS Approval Card Event", exc=exc)
        return None
    if (
        not isinstance(payload, dict)
        or payload.get("status") != "PENDING_APPROVAL"
        or not payload.get("draft_id")
    ):
        return None
    return approval_card_artifact(
        payload["draft_id"],
        payload.get("action_type", ""),
        payload.get("doctype", ""),
        branch or "",
    )


def _open_module_event(tool_name, result_json):
    """Build a UI control event only from a successful, catalog-valid tool result."""
    if tool_name != "open_module":
        return None
    try:
        payload = json.loads(result_json)
    except (TypeError, ValueError) as exc:
        log_exception("AIOS Open Module Event", exc=exc)
        return None
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return None
    module_key = payload.get("module")
    if not isinstance(module_key, str) or not get_module_definition(module_key):
        log_exception("AIOS Open Module Event", context="hasil tool tidak berisi key modul katalog.")
        return None
    return {"type": "open_module", "module": module_key}


class BaseManager:
    def __init__(self, branch_def):
        self.branch = branch_def

    def manager_persona(self) -> str:
        return self.branch.get("manager_persona") or f"Anda adalah AI Manager bidang {self.branch['name']} di AIOS — manajer yang mengoordinasikan seluruh spesialis/worker di bidang ini."

    def ensure_conversation(self, user: str, force_new: bool = False) -> int:
        if not force_new:
            existing = frappe.get_list(
                "AIOS Conversation",
                filters={"user": user, "branch": self.branch["key"]},
                order_by="modified desc",
                limit=1
            )
            if existing:
                return int(existing[0].name)

        doc = frappe.new_doc("AIOS Conversation")
        doc.user = user
        doc.branch = self.branch["key"]
        if force_new:
            doc.title = f"Sesi {self.branch['name']} — {frappe.utils.now_datetime().strftime('%d %b %H:%M')}"
        else:
            doc.title = f"Sesi {self.branch['name']}"
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return int(doc.name)

    def get_worker_def(self, worker_key: str):
        if not worker_key or worker_key == "manager":
            return None
        return get_worker(self.branch["key"], worker_key)

    def _build_worker_prompt(self, worker_def: dict) -> list:
        """Menyusun identitas mandiri dan keahlian mendalam sub-agent spesialis."""
        parts = [
            AIOS_ETHOS,
            f"IDENTITAS PERAN:\n"
            f"Anda adalah {worker_def['jobRole']} di bidang {self.branch['name']} pada platform AIOS.\n"
            f"Fokus tugas utama: {worker_def['description']}\n"
            f"Batas data yang relevan dengan peran Anda: {', '.join(worker_def.get('relevantEntities', []))}.\n\n"
            f"PEDOMAN IDENTITAS MANDIRI (MUTLAK):\n"
            f"- Jawablah murni sebagai {worker_def['jobRole']}.\n"
            f"- JANGAN mengaku sebagai AI Manager atau mengatakan Anda 'sedang berperan sebagai'.\n"
            f"- Anda adalah staf ahli spesialis yang berinteraksi langsung dengan pengguna untuk menyelesaikan tugas di bidang Anda."
        ]

        has_skill_depth = (
            worker_def.get("personality") or
            worker_def.get("priorities") or
            worker_def.get("answerStructure") or
            worker_def.get("antiPatterns")
        )

        if has_skill_depth:
            skill_lines = ["[SKILL DEPTH & GAYA ANALISIS SPESIALIS]"]
            if worker_def.get("personality"):
                skill_lines.append(f"- Karakter Peran: {worker_def['personality']}")
            if worker_def.get("priorities"):
                skill_lines.append("- Prioritas Utama saat Menganalisis:")
                for i, p in enumerate(worker_def["priorities"], 1):
                    skill_lines.append(f"  {i}. {p}")
            if worker_def.get("answerStructure"):
                skill_lines.append(f"- Struktur Jawaban: {' -> '.join(worker_def['answerStructure'])}.")
            if worker_def.get("antiPatterns"):
                skill_lines.append("- Batasan Tegas (JANGAN LAKUKAN):")
                for ap in worker_def["antiPatterns"]:
                    skill_lines.append(f"  - {ap}")
            parts.append("\n".join(skill_lines))
        else:
            parts.append(BASE_PERSONA)

        return parts

    def _build_manager_prompt(self) -> list:
        """Menyusun identitas kepemimpinan dan orkestrator umum AI Manager."""
        return [
            AIOS_ETHOS,
            self.manager_persona(),
            BASE_PERSONA,
            f"IDENTITAS & FOKUS KEPEMIMPINAN:\n"
            f"Anda adalah AI MANAGER (UMUM) yang memimpin bidang {self.branch['name']} di AIOS.\n"
            f"Fokus tugas: Memimpin operasional, mengoordinasikan, dan mengarahkan seluruh spesialis/worker di bidang {self.branch['name']}.\n\n"
            f"PENTING:\n"
            f"- Jangan meniru atau melanjutkan peran sub-agent spesialis tertentu dari riwayat percakapan lama.\n"
            f"- Jawablah murni dari perspektif manajer umum yang bertugas memimpin cabang ini."
        ]

    def build_system_prompt(self, worker_def, user: str = None) -> str:
        if worker_def:
            parts = self._build_worker_prompt(worker_def)
        else:
            parts = self._build_manager_prompt()

        setting = frappe.get_single("AIOS Setting")
        persona_context = (setting.get("company_context_persona") or "").strip()
        user_context = frappe.db.get_value(
            "User",
            user or frappe.session.user,
            ["aios_persona", "aios_persona_context"],
            as_dict=True,
        ) or {}
        context_lines = ["KONTEKS ORGANISASI DAN PENGGUNA:"]
        if persona_context:
            context_lines.append(f"Konteks company: {persona_context}")
        if user_context.get("aios_persona"):
            context_lines.append(f"Persona pengguna: {user_context['aios_persona']}")
        if user_context.get("aios_persona_context"):
            context_lines.append(f"Konteks persona pengguna: {user_context['aios_persona_context']}")
        if len(context_lines) > 1:
            parts.append("\n".join(context_lines))

        parts.append("""ATURAN JAWABAN (WAJIB):
1. Jawab dalam bahasa Indonesia, ramah, ringkas, terstruktur dan profesional.
2. Anda adalah bagian dari AIOS (platform AI enterprise), bukan asisten publik umum.
3. Bantu pengguna menganalisis data, memberikan rekomendasi operasional, dan menjawab pertanyaan terkait bidang Anda.""")

        prompt = "\n\n".join(parts)
        from aios_v1.lib.skills_loader import compose_worker_system_prompt
        if worker_def:
            prompt = compose_worker_system_prompt(self.branch["key"], worker_def["key"], prompt)
        else:
            prompt = compose_worker_system_prompt(self.branch["key"], "manager", prompt)
        return prompt

    def _run_subagent(self, worker_key: str, task_instruction: str, context_data: dict,
                      user: str, usage_records: list, result_holder: list | None = None,
                      conversation_id=None, created_file_ids: list | None = None):
        """Jalankan loop worker internal; hanya trace yang keluar dari generator."""
        import time

        branch = self.branch["key"]
        started = time.monotonic()
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        status, summary = "failed", "Sub-agent gagal menyelesaikan tugas."
        worker_def = get_worker(branch, worker_key)
        if not is_branch_enabled(branch) or not worker_def:
            log_exception("AIOS Sub-agent Unavailable", context=f"branch={branch}; worker={worker_key}")
            yield trace_subagent_result(branch, worker_key, "failed", summary, usage, 0)
            result = json.dumps(safe_error("Sub-agent tidak tersedia.", "SUBAGENT_UNAVAILABLE"))
            if result_holder is not None:
                result_holder.append(result)
            return
        role_summary = f"{worker_def.get('jobRole', worker_key)}: {worker_def.get('description', '')}"
        yield trace_subagent_prompt(branch, worker_key, role_summary, task_instruction)
        try:
            prompt = self.build_system_prompt(worker_def, user)
            schemas = get_tools_schema_for_worker(branch, worker_key)
        except Exception as exc:
            log_exception("AIOS Sub-agent Prompt", exc=exc)
            usage_records.append({"branch": branch, "agent": worker_key, "input_tokens": 0,
                                 "output_tokens": 0, "total_tokens": 0, "provider": "", "model": ""})
            yield trace_subagent_result(branch, worker_key, "failed", summary, usage,
                                        int((time.monotonic() - started) * 1000))
            result = json.dumps(safe_error("Sub-agent gagal disiapkan.", "SUBAGENT_FAILED"))
            if result_holder is not None:
                result_holder.append(result)
            return
        messages = [{"role": "system", "content": prompt},
                    {"role": "user", "content": task_instruction +
                     ("\n\nKonteks tugas: " + json.dumps(context_data, ensure_ascii=False) if context_data else "")}]
        reply = ""
        completed = False
        llm_failed = False
        tool_progress = False
        for round_number in range(MAX_TOOL_ROUNDS):
            turn_usage, calls = {}, []
            try:
                for fragment in chat_stream(messages, usage=turn_usage, tools=schemas, tool_calls=calls):
                    reply += fragment
                for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    usage[key] += int(turn_usage.get(key) or 0)
                usage["provider"] = turn_usage.get("provider", usage.get("provider", ""))
                usage["model"] = turn_usage.get("model", usage.get("model", ""))
                if turn_usage.get("failed"):
                    llm_failed = True
                    break
                if not calls:
                    completed = True
                    break
                messages.append({"role": "assistant", "content": None, "tool_calls": calls})
                for call in calls:
                    function = call.get("function") or {}
                    name = function.get("name", "")
                    try:
                        args = json.loads(function.get("arguments") or "{}")
                    except (TypeError, ValueError) as exc:
                        log_exception("AIOS Sub-agent Tool Arguments", exc=exc)
                        args = {}
                    yield trace_subagent_tool(branch, worker_key, name, args)
                    subagent_tool_context = {
                        "user": user, "branch": branch, "worker_key": worker_key,
                        "delegation_depth": MAX_DELEGATION_DEPTH - 1,
                        "_created_file_ids": created_file_ids,
                    }
                    if conversation_id is not None:
                        subagent_tool_context["conversation_id"] = str(conversation_id)
                    result = execute_tool(name, function.get("arguments") or "{}", context=subagent_tool_context)
                    tool_progress = True
                    artifact_event = _workspace_artifact_event(name, result)
                    if artifact_event is not None:
                        yield artifact_event
                    card_event = _approval_card_event(name, result, branch)
                    if card_event is not None:
                        yield card_event
                    messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result})
                if round_number == MAX_TOOL_ROUNDS - 1:
                    break
            except Exception as exc:
                log_exception("AIOS Sub-agent Runner", exc=exc)
                llm_failed = True
                break
        if llm_failed:
            status = "partial" if tool_progress else "failed"
            summary = "Sub-agent berhenti setelah sebagian proses." if tool_progress else "Sub-agent gagal menyelesaikan tugas."
        elif reply.strip():
            summary = reply[:500]
            status = "success" if completed else "partial"
        elif completed:
            status, summary = "success", "Tugas selesai tanpa ringkasan teks."
        usage_records.append({"provider": usage.get("provider", ""), "model": usage.get("model", ""),
            "branch": branch, "agent": worker_key, "input_tokens": usage["prompt_tokens"],
            "output_tokens": usage["completion_tokens"],
            "total_tokens": usage["total_tokens"] or usage["prompt_tokens"] + usage["completion_tokens"]})
        elapsed = int((time.monotonic() - started) * 1000)
        yield trace_subagent_result(branch, worker_key, status, summary, usage, elapsed)
        if status == "failed":
            result = json.dumps(safe_error("Sub-agent gagal menyelesaikan tugas.", "SUBAGENT_FAILED"))
        else:
            result = json.dumps({"status": status, "summary": reply, "usage": usage}, ensure_ascii=False)
        if result_holder is not None:
            result_holder.append(result)

    def handle_stream(self, user_message: str, worker_key: str = None, conversation_id: int = None,
                      user: str = None, attachments: list | None = None, new_conversation: bool = False):
        user = user or frappe.session.user
        # 0. Flush initial buffer untuk bypass proxy/nginx buffering
        yield f": {' ' * 1024}\n\n"

        if new_conversation:
            # Flag menang atas conversation_id: sesi baru tidak boleh bercampur
            # dengan percakapan lama.
            conversation_id = self.ensure_conversation(user, force_new=True)
        elif not conversation_id:
            conversation_id = self.ensure_conversation(user)

        # 1. Kirim Meta Event
        yield f"data: {json.dumps({'type': 'meta', 'conversationId': conversation_id})}\n\n"

        # 2. Simpan Pesan User ke DocType AIOS Message
        user_msg_doc = frappe.new_doc("AIOS Message")
        user_msg_doc.conversation = str(conversation_id)
        user_msg_doc.role = "user"
        user_msg_doc.worker_key = worker_key or "manager"
        user_msg_doc.content = user_message
        user_msg_doc.insert(ignore_permissions=True)
        attachment_ids = (
            [item.get("file_id") for item in attachments if isinstance(item, dict)]
            if isinstance(attachments, list)
            else []
        )
        if attachment_ids:
            try:
                attach_private_files_to_message(attachment_ids, user_msg_doc.name, conversation_id, user)
            except WorkspaceError as exc:
                # Keep the File attached to its conversation if a parent link cannot be made.
                log_exception("AIOS User Message File Binding", exc=exc, context=exc.code)
        frappe.db.commit()

        # 3. Ambil Riwayat Percakapan
        recent_messages = frappe.get_list(
            "AIOS Message",
            filters={"conversation": str(conversation_id)},
            fields=["role", "worker_key", "content"],
            order_by="creation desc",
            limit=6
        )
        recent_messages.reverse()

        worker_def = self.get_worker_def(worker_key)
        system_prompt = self.build_system_prompt(worker_def, user)

        llm_messages = [{"role": "system", "content": system_prompt}]
        for m in recent_messages[:-1]:
            content = m.content
            # Jika sedang di mode Manager, tandai riwayat sub-agent lama agar model tidak terdistraksi
            if worker_def is None and m.worker_key and m.worker_key != "manager":
                content = f"[{m.worker_key}]: {m.content}"
            llm_messages.append({"role": "user" if m.role == "user" else "assistant", "content": content})

        # Suntikkan direktif peran aktif dan data aktual database client
        if worker_def is None:
            llm_messages.append({
                "role": "system",
                "content": (
                    f"[DIREKTIF PERAN AKTIF]: Anda adalah AI MANAGER {self.branch['name'].upper()} (UMUM). "
                    f"Jawablah tegas sebagai manajer umum yang mengoordinasikan seluruh sub-agent di bidang ini."
                )
            })
        else:
            llm_messages.append({
                "role": "system",
                "content": (
                    f"[DIREKTIF PERAN AKTIF]: Anda adalah {worker_def['jobRole']} di bidang {self.branch['name']}. "
                    f"Jawablah murni dan konsisten sebagai {worker_def['jobRole']}. "
                    f"JANGAN mengaku sebagai AI Manager atau mengatakan Anda 'sedang berperan sebagai'. "
                    f"Terapkan keahlian mendalam peran {worker_def['jobRole']}."
                )
            })

        data_used = []

        if attachments:
            if not isinstance(attachments, list) or not all(isinstance(item, dict) for item in attachments):
                log_exception("AIOS Attachments", context="attachments bukan list of dict; metadata diabaikan")
            else:
                attachment_context = build_attachment_context(attachments)
                if attachment_context:
                    llm_messages.append({"role": "system", "content": attachment_context})

        llm_messages.append({"role": "user", "content": user_message})

        # Estimasi input tokens dari seluruh payload messages
        total_input_chars = sum(len(msg.get("content", "")) for msg in llm_messages)
        est_input_tokens = max(1, int(total_input_chars / 3.8))
        user_msg_doc.input_tokens = est_input_tokens
        user_msg_doc.save(ignore_permissions=True)
        frappe.db.commit()

        # 4. Stream Jawaban dari LLM dan jalankan tool call secara berurutan.
        full_reply = ""
        delegated_to = worker_def["jobRole"] if worker_def else "Manager"
        accumulated_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        usage_records = []
        created_file_ids = []
        failed = False
        last_finish_reason = ""
        tool_schemas = get_tools_schema_for_worker(self.branch.get("key"), worker_key or "manager")

        def stream_llm_turn():
            nonlocal full_reply, failed, last_finish_reason
            turn_usage = {}
            turn_tool_calls = []
            for delta in chat_stream(llm_messages, usage=turn_usage, tools=tool_schemas, tool_calls=turn_tool_calls):
                full_reply += delta
                yield f"data: {json.dumps({'type': 'delta', 'text': delta})}\n\n"
            failed = failed or bool(turn_usage.get("failed"))
            # Reset per turn: `length` pada turn tool-call tidak boleh membocor
            # ke penilaian turn jawaban akhir.
            last_finish_reason = turn_usage.get("finish_reason") or ""
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                if turn_usage.get(key) is not None:
                    accumulated_usage[key] += int(turn_usage[key] or 0)
            if turn_usage.get("provider"):
                accumulated_usage["provider"] = turn_usage["provider"]
            if turn_usage.get("model"):
                accumulated_usage["model"] = turn_usage["model"]
            return turn_tool_calls

        for tool_round in range(MAX_TOOL_ROUNDS):
            tool_calls = yield from stream_llm_turn()
            if failed or not tool_calls:
                break
            llm_messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls})
            for call in tool_calls:
                call_id = call.get("id") or ""
                function = call.get("function") or {}
                try:
                    tool_name = function.get("name", "")
                    if tool_name == "orchestrator_delegate_to_subagent":
                        try:
                            args = json.loads(function.get("arguments", "{}"))
                        except (TypeError, ValueError) as exc:
                            log_exception("AIOS Delegation Arguments", exc=exc)
                            args = None
                        if not isinstance(args, dict):
                            result = json.dumps(safe_error("Argumen delegasi tidak valid.", "DELEGATION_INVALID"))
                            llm_messages.append({"role": "tool", "tool_call_id": call_id, "content": result})
                            continue
                        target_branch = args.get("branch")
                        target_worker = args.get("worker_key")
                        instruction = args.get("task_instruction")
                        if (worker_def is not None or target_branch != self.branch.get("key")
                                or not isinstance(instruction, str) or not instruction.strip()
                                or not isinstance(args.get("context_data") or {}, dict)):
                            result = json.dumps(safe_error("Delegasi tidak valid.", "DELEGATION_FORBIDDEN"))
                        elif not is_branch_enabled(target_branch):
                            result = json.dumps(safe_error("Cabang ini belum tersedia.", "BRANCH_DISABLED"))
                        else:
                            target_def = get_worker(target_branch, target_worker)
                            if not target_def:
                                # Worker tidak dikenal: kembalikan daftar worker valid agar
                                # model bisa mengoreksi key, tanpa menjalankan runner yang
                                # pasti gagal sebagai SUBAGENT_UNAVAILABLE.
                                valid_workers = ", ".join(
                                    worker["key"] for worker in self.branch.get("workers", [])
                                )
                                log_exception(
                                    "AIOS Delegation Unknown Worker",
                                    context=f"branch={target_branch}; worker={target_worker}",
                                )
                                result = json.dumps(safe_error(
                                    f"Sub-agent '{target_worker}' tidak dikenal di cabang ini. "
                                    f"Worker yang tersedia: {valid_workers}.",
                                    "DELEGATION_INVALID",
                                ))
                            else:
                                yield "data: " + json.dumps(trace_delegate_start(
                                    target_branch, target_def["jobRole"], instruction[:500])) + "\n\n"
                                result_holder = []
                                runner = self._run_subagent(
                                    target_def["key"], instruction, args.get("context_data") or {}, user,
                                    usage_records, result_holder, conversation_id=conversation_id,
                                    created_file_ids=created_file_ids)
                                for trace_event in runner:
                                    yield "data: " + json.dumps(trace_event, ensure_ascii=False) + "\n\n"
                                result = result_holder[0]
                    else:
                        # Trace tool Orchestrator (fase 2a, D1): pakai ulang
                        # trace_subagent_tool dengan agent="Orchestrator";
                        # cross_branch_consultation dikecualikan (sudah punya
                        # trace_cross_branch sendiri).
                        try:
                            trace_args = json.loads(function.get("arguments") or "{}")
                        except (TypeError, ValueError) as exc:
                            log_exception("AIOS Orchestrator Trace Arguments", exc=exc)
                            trace_args = {}
                        if not isinstance(trace_args, dict):
                            trace_args = {}
                        if tool_name not in {"cross_branch_consultation", "open_module"}:
                            yield "data: " + json.dumps(trace_subagent_tool(
                                self.branch.get("key", ""), "Orchestrator", tool_name, trace_args,
                            ), ensure_ascii=False) + "\n\n"
                        result = execute_tool(
                            tool_name,
                            function.get("arguments", "{}"),
                            context={
                                "user": user,
                                "branch": self.branch.get("key"),
                                "worker_key": worker_key or "manager",
                                "delegation_depth": MAX_DELEGATION_DEPTH - 2 if worker_def is None else MAX_DELEGATION_DEPTH - 1,
                                "conversation_id": str(conversation_id),
                                "_created_file_ids": created_file_ids,
                            },
                        )
                        card_event = _approval_card_event(tool_name, result, self.branch.get("key", ""))
                        if card_event is not None:
                            yield "data: " + json.dumps(card_event, ensure_ascii=False) + "\n\n"
                        open_module_event = _open_module_event(tool_name, result)
                        if open_module_event is not None:
                            yield "data: " + json.dumps(open_module_event, ensure_ascii=False) + "\n\n"
                        if worker_def is None and tool_name == "cross_branch_consultation":
                            try:
                                trace_args = json.loads(function.get("arguments", "{}"))
                            except (TypeError, ValueError) as exc:
                                log_exception("AIOS Cross-Branch Trace Arguments", exc=exc)
                                trace_args = {}
                            if not isinstance(trace_args, dict):
                                log_exception("AIOS Cross-Branch Trace Arguments", context="JSON args bukan object.")
                                trace_args = {}
                            try:
                                trace_result = json.loads(result)
                            except (TypeError, ValueError) as exc:
                                log_exception("AIOS Cross-Branch Trace Result", exc=exc)
                                trace_result = {"status": "failed", "message": "Hasil konsultasi tidak valid."}
                            if not isinstance(trace_result, dict):
                                log_exception("AIOS Cross-Branch Trace Result", context="JSON result bukan object.")
                                trace_result = {"status": "failed", "message": "Hasil konsultasi tidak valid."}
                            event = trace_cross_branch(
                                from_branch=self.branch.get("key"),
                                to_branch=trace_args.get("to_branch", ""),
                                payload=trace_args.get("payload", {}),
                                result=trace_result,
                            )
                            yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                        file_event = _workspace_artifact_event(tool_name, result)
                        if file_event is not None:
                            yield "data: " + json.dumps(file_event, ensure_ascii=False) + "\n\n"
                except ToolContextError as exc:
                    log_exception("AIOS Tool Context", exc=exc)
                    error = safe_error(TOOL_CONTEXT_ERROR_MESSAGE, "TOOL_CONTEXT_INVALID")
                    message = error["error"]
                    full_reply += message
                    yield f"data: {json.dumps({'type': 'delta', 'text': message})}\n\n"
                    failed = True
                    break
                llm_messages.append({"role": "tool", "tool_call_id": call_id, "content": result})
            if failed:
                break
            if tool_round == MAX_TOOL_ROUNDS - 1:
                log_exception("AIOS Tool Loop Limit", context=f"Batas {MAX_TOOL_ROUNDS} putaran tool tercapai.")
                full_reply += MAX_TOOL_ROUNDS_MESSAGE
                yield f"data: {json.dumps({'type': 'delta', 'text': MAX_TOOL_ROUNDS_MESSAGE})}\n\n"
                break

        # Penanda jujur bila jawaban akhir berhenti karena batas output model,
        # bukan karena model selesai (finish_reason == "length" pada turn terakhir).
        if last_finish_reason == "length":
            full_reply += TRUNCATION_NOTICE
            yield f"data: {json.dumps({'type': 'delta', 'text': TRUNCATION_NOTICE})}\n\n"
            frappe.log_error(
                "AIOS LLM Output Truncated",
                message=f"finish_reason=length pada jawaban akhir; conversation={conversation_id}",
            )

        # Pastikan full_reply tidak kosong agar tidak melanggar mandatory constraint Frappe
        if not full_reply or not full_reply.strip():
            full_reply = "Mohon maaf, tidak ada respon yang dapat dihasilkan atau koneksi terputus. Silakan coba ajukan pertanyaan kembali."
            yield f"data: {json.dumps({'type': 'delta', 'text': full_reply})}\n\n"

        # Estimasi output tokens dari teks balasan AI
        est_output_tokens = max(1, int(len(full_reply) / 3.8))

        input_tokens = int(accumulated_usage["prompt_tokens"] or est_input_tokens)
        output_tokens = int(accumulated_usage["completion_tokens"] or est_output_tokens)
        total_tokens = int(accumulated_usage["total_tokens"] or input_tokens + output_tokens)

        # 5. Simpan Pesan Assistant ke DocType AIOS Message
        asst_msg_doc = frappe.new_doc("AIOS Message")
        asst_msg_doc.conversation = str(conversation_id)
        asst_msg_doc.role = "manager" if not worker_def else "worker"
        asst_msg_doc.worker_key = worker_key or "manager"
        asst_msg_doc.content = full_reply
        asst_msg_doc.output_tokens = output_tokens
        asst_msg_doc.insert(ignore_permissions=True)
        if created_file_ids:
            try:
                attach_private_files_to_message(
                    created_file_ids,
                    asst_msg_doc.name,
                    conversation_id,
                    user,
                )
            except WorkspaceError as exc:
                # Preserve generated files as conversation-level files if binding fails.
                log_exception("AIOS Assistant Message File Binding", exc=exc, context=exc.code)

        # 5b. Ledger per agent dan counter agregat dalam satu transaksi.
        usage_records.append({
            "provider": accumulated_usage.get("provider") or "",
            "model": accumulated_usage.get("model") or "",
            "branch": self.branch.get("key") or "",
            "agent": worker_key or "manager", "input_tokens": input_tokens,
            "output_tokens": output_tokens, "total_tokens": total_tokens,
        })
        record_token_usage_batch(user, usage_records)

        frappe.db.commit()

        # 6. Kirim Done Event
        yield f"data: {json.dumps({'type': 'done', 'conversationId': conversation_id, 'delegatedTo': delegated_to, 'dataUsed': data_used, 'limitation': '', 'tokens': total_tokens + sum(int(item.get('total_tokens') or 0) for item in usage_records[:-1])})}\n\n"
