"use client";

import { useMemo, useState } from "react";
import type { ChatSession } from "./types";
import { Search, MessageCircle, Settings } from "lucide-react";

interface ChatSessionListProps {
  sessions: ChatSession[];
  selectedSessionId: string | number | null;
  onSelectSession: (session: ChatSession) => void;
  onOpenSettings: () => void;
  isLoading: boolean;
}

function formatSmartTime(dateStr: string): string {
  if (!dateStr) return "";
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) {
      return date.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
    }
    if (diffDays < 7) {
      return date.toLocaleDateString("id-ID", { weekday: "short" });
    }
    return date.toLocaleDateString("id-ID", { day: "2-digit", month: "2-digit", year: "numeric" });
  } catch {
    return dateStr;
  }
}

export default function ChatSessionList({
  sessions,
  selectedSessionId,
  onSelectSession,
  onOpenSettings,
  isLoading,
}: ChatSessionListProps) {
  const [searchQuery, setSearchQuery] = useState("");

  const filteredSessions = useMemo(() => {
    if (!searchQuery.trim()) return sessions;
    const q = searchQuery.toLowerCase();
    return sessions.filter((s) => {
      const name = `${s.first_name || ""} ${s.last_name || ""} ${s.username || ""}`.toLowerCase();
      const lastMsg = (s.last_message || "").toLowerCase();
      return name.includes(q) || lastMsg.includes(q);
    });
  }, [sessions, searchQuery]);

  return (
    <div className="flex flex-col h-full bg-zinc-950/60">
      {/* Search Header */}
      <div className="p-3 border-b border-zinc-800/80">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-zinc-500" />
          <input
            type="text"
            placeholder="Cari customer / chat..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-zinc-900/80 border border-zinc-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-600 transition"
          />
        </div>
      </div>

      {/* Session Items */}
      <div className="flex-1 overflow-y-auto divide-y divide-zinc-900/60">
        {isLoading && sessions.length === 0 ? (
          <div className="p-6 text-center text-xs text-zinc-500">
            Memuat daftar percakapan...
          </div>
        ) : filteredSessions.length === 0 ? (
          <div className="p-6 text-center text-xs text-zinc-500 flex flex-col items-center gap-2">
            <MessageCircle className="h-6 w-6 text-zinc-600" />
            <span>Belum ada percakapan masuk</span>
          </div>
        ) : (
          filteredSessions.map((session) => {
            const isSelected = String(session.name) === String(selectedSessionId);
            const displayName = [session.first_name, session.last_name]
              .filter(Boolean)
              .join(" ") || session.username || `Customer #${session.chat_id.slice(-4)}`;
            const initial = displayName.charAt(0).toUpperCase();

            return (
              <button
                key={session.name}
                type="button"
                onClick={() => onSelectSession(session)}
                className={`w-full text-left p-3.5 flex items-start gap-3 transition-colors ${
                  isSelected
                    ? "bg-zinc-800/80 border-l-2 border-cyan-400"
                    : "hover:bg-zinc-900/60"
                }`}
              >
                {/* Avatar Initial */}
                <div className="w-9 h-9 rounded-full bg-zinc-800 border border-zinc-700/60 flex items-center justify-center shrink-0 text-xs font-semibold text-zinc-200">
                  {initial}
                </div>

                {/* Info & Snippet */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-1 mb-0.5">
                    <span className="text-xs font-medium text-zinc-200 truncate">
                      {displayName}
                    </span>
                    <span className="text-[10px] text-zinc-500 shrink-0">
                      {formatSmartTime(session.last_interaction)}
                    </span>
                  </div>

                  <p className="text-[11px] text-zinc-400 truncate mb-1.5">
                    {session.last_message || "Memulai percakapan"}
                  </p>

                  <div className="flex items-center gap-2 flex-wrap">
                    {session.lead && (
                      <div className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-cyan-950/60 border border-cyan-800/40 text-[9px] text-cyan-400 font-mono">
                        <span>ERPNext:</span>
                        <span className="truncate max-w-[110px]">{session.lead}</span>
                      </div>
                    )}
                    {session.sales_order && (
                      <span className="text-[10px] text-zinc-400 font-mono">
                        Order: {session.sales_order}
                      </span>
                    )}
                  </div>
                </div>
              </button>
            );
          })
        )}
      </div>
      {/* Footer Settings Button (Antigravity Style: bottom-left) */}
      <div className="p-2.5 border-t border-zinc-800/80 bg-zinc-950/90 shrink-0">
        <button
          type="button"
          onClick={onOpenSettings}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900 transition-colors"
        >
          <Settings className="w-3.5 h-3.5 text-zinc-400" />
          <span>Pengaturan Bot</span>
        </button>
      </div>
    </div>
  );
}
