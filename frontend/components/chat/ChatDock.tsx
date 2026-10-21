"use client";

// Chat dock — port dari frontend/components/ChatDock.tsx, diadaptasi ke API
// backend implementasi (pilih sub-agent oleh USER sesuai FR-15, delegasi
// transparan, saran dari contoh pertanyaan tiap worker).
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, getCsrfToken } from "@/lib/api";
import { accentOf, rgbaOf, type Branch } from "@/lib/branches";
import type { WorkerInfo } from "@/lib/types";
import { DraftCard } from "./DraftCard";
import { AutomationDropdown } from "./AutomationDropdown";
import { X, Paperclip, Send, Square, Bot, Sparkles, Pencil } from "lucide-react";

interface ChatDockProps {
  branch: Branch;
  workers: WorkerInfo[];
  initialWorkerKey?: string;
  onClose: () => void;
}

interface ChatMsg {
  id: number;
  role: "user" | "ai";
  who?: string;
  delegate?: string;
  text: string;
}

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

const FALLBACK_SUGGESTIONS = [
  "Ringkas kondisi terkini",
  "Apa yang bisa Anda bantu?",
  "Analisis data terbaru",
];

const INPUT_MAX_HEIGHT = 120;
let msgSeq = 0;

const markdownComponents: any = {
  a({ node, href, children, ...props }: any) {
    if (href?.startsWith("/draft/")) {
      const draftId = href.replace("/draft/", "");
      return <DraftCard draftId={draftId} />;
    }
    return <a href={href} target="_blank" rel="noopener noreferrer" {...props}>{children}</a>;
  }
};

export default function ChatDock({ branch, workers, initialWorkerKey = "manager", onClose }: ChatDockProps) {
  const [msgs, setMsgs] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState<{name: string, content: string}[]>([]);
  const [thinking, setThinking] = useState(false);
  const [thinkingStep, setThinkingStep] = useState(0);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editText, setEditText] = useState("");
  const [workerKey, setWorkerKey] = useState<string>(initialWorkerKey);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [receiving, setReceiving] = useState(false); // delta pertama sudah datang
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const selectedWorker = workers.find((w) => w.key === workerKey);
  const chips = selectedWorker?.exampleQuestions?.length
    ? selectedWorker.exampleQuestions.slice(0, 3)
    : FALLBACK_SUGGESTIONS;

  useEffect(() => {
    setMsgs([
      {
        id: msgSeq++,
        role: "ai",
        who: `${branch.icon} ${branch.manager}`,
        delegate: "(Agent Primary)",
        text: `Halo! Saya AI Manager bidang ${branch.name}. Pilih sub-agent yang ingin dikonsultasikan di atas, lalu tanyakan apa saja tentang data perusahaan Anda.`,
      },
    ]);
    setWorkerKey(initialWorkerKey || "manager");
    setConversationId(null);
    setThinking(false);
    setThinkingStep(0);
    setReceiving(false);
    setAttachments([]);
    setEditText("");
    setEditingId(null);
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches === false) {
      const t = setTimeout(() => inputRef.current?.focus(), 500);
      return () => clearTimeout(t);
    }
  }, [branch, initialWorkerKey]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [msgs, thinking]);

  useEffect(() => {
    const onSelectWorker = (e: Event) => {
      const key = (e as CustomEvent).detail;
      if (key) setWorkerKey(key);
    };
    window.addEventListener("aios:select-worker", onSelectWorker);
    return () => window.removeEventListener("aios:select-worker", onSelectWorker);
  }, []);

  function autoGrowInput() {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, INPUT_MAX_HEIGHT)}px`;
  }

  useEffect(() => {
    if (!input && inputRef.current) inputRef.current.style.height = "auto";
  }, [input]);

  const THINKING_STEPS = [
    `${branch.manager} menganalisis pertanyaan…`,
    workerKey === "manager" ? "Menyiapkan konteks & data…" : `Meneruskan ke ${selectedWorker?.jobRole ?? "sub-agent"}…`,
    "Mengakses database client…",
    "Menyusun jawaban…",
  ];

  async function send(value?: string) {
    const text = (value !== undefined ? String(value) : input).trim();
    if ((!text && attachments.length === 0) || thinking) return;

    setInput("");
    const sentAttachments = [...attachments];
    setAttachments([]);
    if (inputRef.current) inputRef.current.style.height = "auto";

    const uiText = text + (sentAttachments.length > 0 ? `\n\n*(Melampirkan ${sentAttachments.length} dokumen)*` : "");
    let backendMessage = text;
    if (sentAttachments.length > 0) {
      backendMessage += "\n\n[USER ATTACHMENTS]\n" + sentAttachments.map(a => `--- ${a.name} ---\n${a.content}\n--- END OF ${a.name} ---`).join("\n\n");
    }

    setMsgs((m) => [...m, { id: msgSeq++, role: "user", text: uiText }]);
    setThinking(true);
    setThinkingStep(0);
    setReceiving(false);

    const stepTimer = setInterval(() => {
      setThinkingStep((s) => Math.min(s + 1, THINKING_STEPS.length - 1));
    }, 3000);

    const controller = new AbortController();
    abortRef.current = controller;

    // Pesan AI "hidup" — teksnya diisi bertahap saat delta stream masuk.
    const aiId = msgSeq++;
    setMsgs((m) => [
      ...m,
      { id: aiId, role: "ai", who: `${branch.icon} ${branch.manager}`, delegate: "(Agent Primary)", text: "" },
    ]);
    const patchAi = (patch: Partial<ChatMsg>) =>
      setMsgs((m) => m.map((msg) => (msg.id === aiId ? { ...msg, ...patch } : msg)));
    const appendDelta = (t: string) =>
      setMsgs((m) => m.map((msg) => (msg.id === aiId ? { ...msg, text: msg.text + t } : msg)));
    const watchdogTimer = setTimeout(() => {
      controller.abort();
    }, 90000);

    let attempts = 0;
    const maxAttempts = 2;
    let streamFailed: string | null = null;

    try {
      while (attempts < maxAttempts) {
        attempts++;
        try {
          // Jalur utama: streaming (SSE)
          const csrf = getCsrfToken();
          const res = await fetch(`/api/chat/${branch.id}/stream`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              ...(csrf ? { "X-Frappe-CSRF-Token": csrf } : {}),
            },
            body: JSON.stringify({ message: backendMessage, workerKey, conversationId }),
            signal: controller.signal,
          });

          if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buf = "";

          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            let nl: number;
            while ((nl = buf.indexOf("\n")) !== -1) {
              const line = buf.slice(0, nl).trim();
              buf = buf.slice(nl + 1);
              if (!line.startsWith("data:")) continue;
              let ev: {
                type?: string;
                conversationId?: number;
                text?: string;
                delegatedTo?: string | null;
                message?: string;
              };
              try {
                ev = JSON.parse(line.slice(5));
              } catch {
                continue;
              }
              if (ev.type === "meta" && typeof ev.conversationId === "number") {
                setConversationId(ev.conversationId);
              } else if (ev.type === "delta" && ev.text) {
                if (!receiving) setReceiving(true);
                appendDelta(ev.text);
              } else if (ev.type === "done") {
                if (typeof ev.conversationId === "number") setConversationId(ev.conversationId);
                const delegatedTo = ev.delegatedTo ?? null;
                patchAi({ delegate: delegatedTo ? `→ sub-agent: ${delegatedTo}` : "(Agent Primary)" });
                if (delegatedTo) {
                  const flare = workers.find((w) => w.jobRole === delegatedTo)?.key ?? delegatedTo;
                  window.dispatchEvent(new CustomEvent("aios:worker-used", { detail: { workerId: norm(flare) } }));
                }
              } else if (ev.type === "error") {
                streamFailed = ev.message ?? "Terjadi kesalahan.";
              }
            }
          }
          break; // Berhasil stream, keluar dari retry loop
        } catch (innerErr) {
          if (controller.signal.aborted) throw innerErr;
          if (attempts >= maxAttempts) throw innerErr;
          await new Promise((r) => setTimeout(r, 800));
        }
      }

      if (streamFailed) {
        setMsgs((m) =>
          m.map((msg) =>
            msg.id === aiId
              ? { ...msg, text: msg.text ? `${msg.text}\n\n⚠️ ${streamFailed}` : `⚠️ ${streamFailed}` }
              : msg,
          ),
        );
      }
    } catch (e) {
      const aborted = e instanceof DOMException && e.name === "AbortError";
      const msg = aborted
        ? "Respon AI membutuhkan waktu lebih lama dari biasanya. Silakan coba kembali."
        : e instanceof Error
          ? e.message
          : "Gagal menghubungi AI Manager.";
      setMsgs((m) =>
        m.map((m2) =>
          m2.id === aiId
            ? { ...m2, text: m2.text ? `${m2.text}\n\n⚠️ ${msg}` : `⚠️ ${msg}` }
            : m2,
        ),
      );
    } finally {
      clearTimeout(watchdogTimer);
      clearInterval(stepTimer);
      abortRef.current = null;
      setThinking(false);
      setReceiving(false);
      setThinkingStep(0);
      inputRef.current?.focus();
    }
  }

  function startEdit(m: ChatMsg) {
    setEditingId(m.id);
    setEditText(m.text);
  }
  function cancelEdit() {
    setEditingId(null);
    setEditText("");
  }
  async function submitEdit() {
    const text = editText.trim();
    if (!text) return;
    const idx = msgs.findIndex((m) => m.id === editingId);
    if (idx === -1) return;
    setMsgs(msgs.slice(0, idx));
    cancelEdit();
    await send(text);
  }
  function stopGeneration() {
    abortRef.current?.abort();
  }

  // Warna identitas bidang — dipakai CSS vars oleh stylesheet (avatar glow,
  // nama manager, chip saran) supaya dock "bernyawa" sesuai AI Manager-nya.
  const acc = accentOf(branch.id);
  const accVars = {
    "--acc": acc,
    "--acc-line": rgbaOf(acc, 0.45),
    "--acc-glow": rgbaOf(acc, 0.55),
    "--acc-soft": rgbaOf(acc, 0.16),
    "--acc-name": acc,
  } as React.CSSProperties;

  return (
    <aside className="chat-dock" style={accVars} aria-hidden={false}>
      <div className="dock-head">
        <div
          className="dock-title"
          onClick={() => {
            setWorkerKey("manager");
            window.dispatchEvent(new CustomEvent("aios:select-worker", { detail: "manager" }));
          }}
          style={{ cursor: "pointer" }}
          title="Klik untuk beralih ke AI Manager (Umum)"
        >
          <div className="dock-name">{branch.name}</div>
        </div>
        <button type="button" className="dock-close-btn" onClick={onClose} aria-label="Tutup panel chat" title="Tutup">
          <X size={18} />
        </button>
      </div>

      {/* Status agen yang diajak bicara (Dipilih via klik node di 3D view) */}
      <div className="dock-worker">
        <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12px", color: "var(--text-muted)" }}>
          <Bot size={13} style={{ color: "#22d3ee" }} />
          <span>Sedang mengobrol dengan:</span>
        </div>
        <div
          className="dock-worker-status"
          style={{
            padding: "5px 12px",
            background: "rgba(34, 211, 238, 0.08)",
            border: "1px solid rgba(34, 211, 238, 0.25)",
            color: "#67e8f9",
            borderRadius: "8px",
            fontSize: "12.5px",
            fontWeight: 600,
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            marginTop: "4px"
          }}
        >
          <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#22d3ee", display: "inline-block" }} />
          {workerKey === "manager" ? "AI Manager (Umum)" : workers.find(w => w.key === workerKey)?.jobRole || "AI Manager"}
        </div>
      </div>

      <div className="dock-messages" ref={listRef}>
        {msgs.map((m) =>
          m.role === "user" ? (
            editingId === m.id ? (
              <div key={m.id} className="msg msg-user msg-editing">
                <textarea
                  className="edit-area"
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      submitEdit();
                    } else if (e.key === "Escape") {
                      cancelEdit();
                    }
                  }}
                  aria-label="Edit pesan"
                  autoFocus
                />
                <div className="edit-actions">
                  <button type="button" className="btn btn-primary" onClick={submitEdit}>
                    Kirim
                  </button>
                  <button type="button" className="edit-cancel" onClick={cancelEdit}>
                    Batal
                  </button>
                </div>
              </div>
            ) : (
              <div key={m.id} className="msg-row-user">
                <button
                  type="button"
                  className="msg-edit-btn"
                  onClick={() => startEdit(m)}
                  aria-label="Edit pesan"
                  title="Edit pesan"
                  disabled={thinking}
                >
                  <Pencil size={12} />
                </button>
                <div className="msg msg-user">{m.text}</div>
              </div>
            )
          ) : (
            <div key={m.id} className="msg msg-ai">
              <div className="who">
                {m.who} <span className="delegate">{m.delegate}</span>
              </div>
              <div className="markdown-body">
                <ReactMarkdown 
                  remarkPlugins={[remarkGfm]}
                  components={markdownComponents}
                >
                  {m.text}
                </ReactMarkdown>
              </div>
            </div>
          )
        )}
        {thinking && !receiving && (
          <div className="delegate-note">
            <span className="spin" /> {THINKING_STEPS[thinkingStep]}
          </div>
        )}
      </div>

      <div className="dock-suggestions">
        {chips.map((s) => (
          <button key={s} type="button" className="suggestion-chip" onClick={() => send(s)} disabled={thinking}>
            {s}
          </button>
        ))}
      </div>

      <div className="dock-input-wrapper">
        {attachments.length > 0 && (
          <div className="dock-attachments">
            {attachments.map((a, i) => (
              <span key={i} className="dock-attachment-chip">
                <Paperclip size={12} /> {a.name}
                <button type="button" onClick={() => setAttachments(arr => arr.filter((_, idx) => idx !== i))} title="Hapus file">&times;</button>
              </span>
            ))}
          </div>
        )}

        <div className="dock-input-box">
          <textarea
            ref={inputRef}
            rows={1}
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              autoGrowInput();
            }}
            onKeyDown={(e) => {
              if (e.key !== "Enter") return;
              if (e.shiftKey) {
                e.preventDefault();
                const el = e.currentTarget;
                const start = el.selectionStart ?? el.value.length;
                const end = el.selectionEnd ?? el.value.length;
                const next = el.value.slice(0, start) + "\n" + el.value.slice(end);
                setInput(next);
                requestAnimationFrame(() => {
                  el.setSelectionRange(start + 1, start + 1);
                  autoGrowInput();
                });
                return;
              }
              e.preventDefault();
              send();
            }}
            placeholder={`Tanyakan pada ${selectedWorker?.jobRole ?? "AI Manager"}…`}
            aria-label="Tulis pertanyaan Anda"
            disabled={thinking}
          />

          <div className="dock-input-toolbar">
            <div className="dock-toolbar-left">
              <button 
                type="button" 
                className="btn-attach-icon" 
                onClick={() => fileInputRef.current?.click()}
                title="Lampirkan file (.txt, .md, .csv, .pdf)"
                disabled={thinking}
              >
                <Paperclip size={15} />
              </button>
              
              <AutomationDropdown
                branchKey={branch.id || branch.name}
                branchName={branch.name}
                disabled={thinking}
                onSelect={(preset) => {
                  if (preset.targetRole) {
                    const targetW = workers.find(w => w.key.toLowerCase().includes(preset.targetRole!.toLowerCase()) || preset.targetRole!.toLowerCase().includes(w.key.toLowerCase()));
                    if (targetW) {
                      setWorkerKey(targetW.key);
                    }
                  }
                  send(preset.prompt);
                }}
              />
            </div>

            <div className="dock-toolbar-right">
              {thinking ? (
                <button type="button" className="btn-stop" onClick={stopGeneration}>
                  <Square size={12} fill="currentColor" /> Stop
                </button>
              ) : (
                <button
                  type="button"
                  className="btn-send-action"
                  onClick={() => send()}
                  disabled={!input.trim() && attachments.length === 0}
                >
                  <Send size={13} /> Kirim
                </button>
              )}
            </div>
          </div>
        </div>

        <input 
          type="file" 
          ref={fileInputRef} 
          hidden 
          accept=".txt,.md,.csv,.pdf" 
          multiple 
          onChange={async (e) => {
            const files = Array.from(e.target.files ?? []);
            if (!files.length) return;
            
            setThinking(true);
            try {
              const newAtts = await Promise.all(files.map(async f => {
                if (f.name.toLowerCase().endsWith('.pdf')) {
                  const fd = new FormData();
                  fd.append("file", f);
                  const csrf = getCsrfToken();
                  const res = await fetch("/api/chat/parse-pdf", {
                    method: "POST",
                    headers: csrf ? { "X-Frappe-CSRF-Token": csrf } : {},
                    body: fd,
                  });
                  if (!res.ok) throw new Error(`Gagal parse PDF: ${f.name}`);
                  const json = await res.json();
                  return { name: f.name, content: json.text };
                }
                return { name: f.name, content: await f.text() };
              }));
              setAttachments(prev => [...prev, ...newAtts]);
            } catch (err) {
              alert(err instanceof Error ? err.message : "Gagal memproses file");
            } finally {
              setThinking(false);
              e.target.value = '';
            }
          }} 
        />
      </div>
    </aside>
  );
}
