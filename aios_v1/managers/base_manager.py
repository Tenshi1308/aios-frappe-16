import json
import frappe
from aios_v1.shared.aios_ethos import AIOS_ETHOS
from aios_v1.shared.base_persona import BASE_PERSONA
from aios_v1.lib.llm_client import chat_stream
from aios_v1.plugin_manager.registry import get_branches, get_worker

class BaseManager:
    def __init__(self, branch_def):
        self.branch = branch_def

    def manager_persona(self) -> str:
        return self.branch.get("manager_persona") or f"Anda adalah AI Manager bidang {self.branch['name']} di AIOS — manajer yang mengoordinasikan seluruh spesialis/worker di bidang ini."

    def ensure_conversation(self, user: str) -> int:
        existing = frappe.get_all(
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

    def build_system_prompt(self, worker_def) -> str:
        if worker_def:
            parts = self._build_worker_prompt(worker_def)
        else:
            parts = self._build_manager_prompt()

        parts.append("""ATURAN JAWABAN (WAJIB):
1. Jawab dalam bahasa Indonesia, ramah, ringkas, terstruktur dan profesional.
2. Anda adalah bagian dari AIOS (platform AI enterprise), bukan asisten publik umum.
3. Bantu pengguna menganalisis data, memberikan rekomendasi operasional, dan menjawab pertanyaan terkait bidang Anda.""")

        return "\n\n".join(parts)

    def handle_stream(self, company_id: int, user_message: str, worker_key: str = None, conversation_id: int = None, user: str = None):
        user = user or frappe.session.user
        # 0. Flush initial buffer untuk bypass proxy/nginx buffering
        yield f": {' ' * 1024}\n\n"

        if not conversation_id:
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
        frappe.db.commit()

        # 3. Ambil Riwayat Percakapan
        recent_messages = frappe.get_all(
            "AIOS Message",
            filters={"conversation": str(conversation_id)},
            fields=["role", "worker_key", "content"],
            order_by="creation desc",
            limit=6
        )
        recent_messages.reverse()

        worker_def = self.get_worker_def(worker_key)
        system_prompt = self.build_system_prompt(worker_def)

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

        # Ambil konsep data canonical yang aktif dan tersedia untuk tenant ini
        try:
            from aios_v1.data_access.query_engine import get_available_concepts
            available_concepts = get_available_concepts(company_id)
            if available_concepts:
                concepts_summary = "\n".join([f"- {ent}: {', '.join(fields)}" for ent, fields in available_concepts.items()])
                llm_messages.append({
                    "role": "system",
                    "content": (
                        "[STATUS KONEKSI & KONSEP DATA AKTIF]:\n"
                        "Sistem AIOS Anda saat ini TERHUBUNG AKTIF ke database perusahaan client.\n"
                        "Berikut adalah konsep data bisnis yang berhasil dipetakan dan dapat diakses:\n"
                        f"{concepts_summary}\n\n"
                        "Pedoman: Jika pengguna menanyakan apakah database terdeteksi atau menanyakan struktur/tabel/data apa saja yang Anda miliki, "
                        "tegaskan bahwa sistem terhubung ke konsep-konsep data di atas tanpa mengarang atau meminta pengguna melampirkan file dokumen secara manual."
                    )
                })
        except Exception as e:
            frappe.log_error(f"Error fetching available concepts: {e}", "AIOS Concepts Context")

        # Ambil data faktual dari database client via Safe Query Engine
        data_used = []
        try:
            from aios_v1.data_access.query_engine import get_relevant_business_data
            data_context, data_used = get_relevant_business_data(company_id, user_message, self.branch["key"], worker_def)
            if data_context:
                llm_messages.append({"role": "system", "content": data_context})
        except Exception as e:
            frappe.log_error(f"Error fetching business data in manager: {e}", "AIOS Data Query")

        llm_messages.append({"role": "user", "content": user_message})

        # Estimasi input tokens dari seluruh payload messages
        total_input_chars = sum(len(msg.get("content", "")) for msg in llm_messages)
        est_input_tokens = max(1, int(total_input_chars / 3.8))
        user_msg_doc.input_tokens = est_input_tokens
        user_msg_doc.save(ignore_permissions=True)
        frappe.db.commit()

        # 4. Stream Jawaban dari LLM
        full_reply = ""
        delegated_to = worker_def["jobRole"] if worker_def else "Manager"

        for delta in chat_stream(llm_messages):
            full_reply += delta
            yield f"data: {json.dumps({'type': 'delta', 'text': delta})}\n\n"

        # Pastikan full_reply tidak kosong agar tidak melanggar mandatory constraint Frappe
        if not full_reply or not full_reply.strip():
            full_reply = "Mohon maaf, tidak ada respon yang dapat dihasilkan atau koneksi terputus. Silakan coba ajukan pertanyaan kembali."
            yield f"data: {json.dumps({'type': 'delta', 'text': full_reply})}\n\n"

        # Estimasi output tokens dari teks balasan AI
        est_output_tokens = max(1, int(len(full_reply) / 3.8))

        # 5. Simpan Pesan Assistant ke DocType AIOS Message
        asst_msg_doc = frappe.new_doc("AIOS Message")
        asst_msg_doc.conversation = str(conversation_id)
        asst_msg_doc.role = "manager" if not worker_def else "worker"
        asst_msg_doc.worker_key = worker_key or "manager"
        asst_msg_doc.content = full_reply
        asst_msg_doc.output_tokens = est_output_tokens
        asst_msg_doc.insert(ignore_permissions=True)
        frappe.db.commit()

        # 6. Kirim Done Event
        yield f"data: {json.dumps({'type': 'done', 'conversationId': conversation_id, 'delegatedTo': delegated_to, 'dataUsed': data_used, 'limitation': '', 'tokens': est_output_tokens})}\n\n"
