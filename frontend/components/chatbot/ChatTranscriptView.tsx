"use client";

import { useEffect, useRef } from "react";
import type { ChatSession, ChatMessage } from "./types";
import { Bot, MessageSquare, ShoppingBag } from "lucide-react";

interface ChatTranscriptViewProps {
  session: ChatSession | null;
  messages: ChatMessage[];
  isLoading: boolean;
}

function formatMessageTime(dateStr: string): string {
  if (!dateStr) return "";
  try {
    const d = new Date(dateStr);
    return d.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

export default function ChatTranscriptView({
  session,
  messages,
  isLoading,
}: ChatTranscriptViewProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (!session) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-zinc-500">
        <div className="w-12 h-12 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center mb-3 text-zinc-400">
          <MessageSquare className="h-6 w-6" />
        </div>
        <p className="text-sm font-medium text-zinc-300">Pilih Sesi Obrolan</p>
        <p className="text-xs text-zinc-500 max-w-xs mt-1">
          Klik salah satu customer di sebelah kiri untuk melihat transkrip percakapan langsung dengan bot AIOS.
        </p>
      </div>
    );
  }

  const displayName = [session.first_name, session.last_name]
    .filter(Boolean)
    .join(" ") || session.username || `Customer #${session.chat_id.slice(-4)}`;

  return (
    <div className="flex-1 flex flex-col h-full bg-zinc-950">
      {/* Active Header */}
      <div className="p-3.5 px-4 border-b border-zinc-800/80 bg-zinc-950/90 flex items-center justify-between shrink-0">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-xs font-semibold text-zinc-100">{displayName}</h3>
            <span className="text-[10px] text-zinc-400">Telegram Customer</span>
          </div>
          <p className="text-[10px] text-zinc-500 mt-0.5">
            Chat ID: {session.chat_id} {session.username ? `(@${session.username})` : ""}
          </p>
        </div>

        {session.lead && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-zinc-900 border border-zinc-800 text-xs">
            <span className="text-[10px] text-zinc-400">Lead ERPNext:</span>
            <span className="text-[11px] font-mono text-cyan-400">{session.lead}</span>
          </div>
        )}
      </div>

      {/* WhatsApp-Style Chat Bubbles Container */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3.5 bg-zinc-950/40">
        {isLoading && messages.length === 0 ? (
          <div className="p-6 text-center text-xs text-zinc-500">
            Memuat transkrip pesan...
          </div>
        ) : messages.length === 0 ? (
          <div className="p-6 text-center text-xs text-zinc-500">
            Belum ada pesan yang tercatat pada sesi ini.
          </div>
        ) : (
          messages.map((msg) => {
            const isUser = msg.sender === "user";

            return isUser ? (
              // Customer Bubble (Lawan bicara di sisi KIRI)
              <div key={msg.name} className="flex items-start gap-2.5 mr-8">
                <div className="w-7 h-7 rounded-full bg-zinc-800 border border-zinc-700/80 flex items-center justify-center shrink-0 text-[11px] font-medium text-zinc-300 mt-0.5">
                  {displayName.charAt(0).toUpperCase()}
                </div>
                <div className="max-w-[80%] rounded-2xl rounded-tl-xs bg-zinc-900 border border-zinc-800/80 px-3.5 py-2 text-zinc-200 shadow-sm">
                  <p className="text-xs whitespace-pre-wrap leading-relaxed">
                    {msg.message}
                  </p>
                  <p className="text-[9px] text-zinc-500 text-right mt-1">
                    {formatMessageTime(msg.sent_at)}
                  </p>
                </div>
              </div>
            ) : (
              // Bot Bubble (Chatbot AIOS / Sisi Kita di sisi KANAN)
              <div key={msg.name} className="flex justify-end ml-8">
                <div className="max-w-[80%] rounded-2xl rounded-tr-xs bg-zinc-800 border border-zinc-700/60 px-3.5 py-2 text-zinc-100 shadow-sm">
                  <p className="text-xs whitespace-pre-wrap leading-relaxed">
                    {msg.message}
                  </p>

                  {msg.order_info && (
                    <div className="mt-2.5 p-3 rounded-xl bg-zinc-900/90 border border-zinc-700/60 space-y-2 text-left">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5">
                          <ShoppingBag className="w-3.5 h-3.5 text-zinc-400 shrink-0" />
                          <span className="text-xs font-mono font-medium text-zinc-200">
                            {msg.order_info.sales_order}
                          </span>
                        </div>
                        <span className="px-1.5 py-0.5 rounded text-[10px] bg-zinc-800 border border-zinc-700 text-zinc-300 font-medium">
                          Draft
                        </span>
                      </div>

                      <p className="text-xs text-zinc-300 leading-relaxed">
                        {msg.order_info.items_summary}
                      </p>

                      <div className="flex items-center justify-between pt-1.5 border-t border-zinc-800 text-xs">
                        <span className="text-zinc-400">Total</span>
                        <span className="font-semibold text-zinc-100">
                          Rp {msg.order_info.grand_total.toLocaleString("id-ID")}
                        </span>
                      </div>

                      <p className="text-[10px] text-zinc-400">
                        Draf pesanan penjualan berhasil dicatat ke ERPNext.
                      </p>
                    </div>
                  )}

                  <p className="text-[9px] text-zinc-400 text-right mt-1">
                    {formatMessageTime(msg.sent_at)}
                  </p>
                </div>
              </div>
            );
          })
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
