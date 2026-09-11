"use client";

import { useEffect, useState } from "react";
import { MessageSquare, X, Bot } from "lucide-react";
import { api } from "@/lib/api";
import type { ChatSession, ChatMessage } from "./types";
import ChatSessionList from "./ChatSessionList";
import ChatTranscriptView from "./ChatTranscriptView";
import ChatbotSettingsDialog from "./ChatbotSettingsDialog";

interface ChatbotMonitoringWidgetProps {
  isDockOpen?: boolean;
}

export default function ChatbotMonitoringWidget({ isDockOpen = false }: ChatbotMonitoringWidgetProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isMounted, setIsMounted] = useState(false);
  const [isVisible, setIsVisible] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [selectedSession, setSelectedSession] = useState<ChatSession | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  // Smooth open animation
  const openWidget = () => {
    setIsMounted(true);
    setIsOpen(true);
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        setIsVisible(true);
      });
    });
  };

  // Smooth close animation toward bottom-right button
  const closeWidget = () => {
    setIsVisible(false);
    setIsOpen(false);
    setIsSettingsOpen(false);
    setTimeout(() => {
      setIsMounted(false);
    }, 220);
  };

  const toggleWidget = () => {
    if (isOpen) {
      closeWidget();
    } else {
      openWidget();
    }
  };

  // Otomatis menutup saat ChatDock dibuka oleh client
  useEffect(() => {
    if (isDockOpen && (isOpen || isMounted)) {
      closeWidget();
    }
  }, [isDockOpen]);

  // Fetch sessions from Frappe backend
  const fetchSessions = async () => {
    try {
      const data = await api<{ sessions: ChatSession[] }>("/chatbot/sessions");
      setSessions(data.sessions || []);
      // Auto select first session if none selected
      setSelectedSession((curr) => {
        if (curr) {
          const found = (data.sessions || []).find((s) => String(s.name) === String(curr.name));
          return found || curr;
        }
        return data.sessions && data.sessions.length > 0 ? data.sessions[0] : null;
      });
    } catch (err) {
      console.error("Gagal memuat sesi chatbot:", err);
    }
  };

  // Fetch messages for active session
  const fetchMessages = async (sessionId: string | number) => {
    setLoadingMessages(true);
    try {
      const data = await api<{ messages: ChatMessage[] }>(`/chatbot/messages?session_id=${sessionId}`);
      setMessages(data.messages || []);
    } catch (err) {
      console.error("Gagal memuat pesan chatbot:", err);
    } finally {
      setLoadingMessages(false);
    }
  };

  // Load sessions when opened
  useEffect(() => {
    if (isOpen) {
      setLoadingSessions(true);
      fetchSessions().finally(() => setLoadingSessions(false));

      const interval = setInterval(() => {
        fetchSessions();
      }, 5000);
      return () => clearInterval(interval);
    }
  }, [isOpen]);

  // Load messages when selected session changes
  useEffect(() => {
    if (selectedSession && isOpen) {
      fetchMessages(selectedSession.name);

      const interval = setInterval(() => {
        fetchMessages(selectedSession.name);
      }, 4000);
      return () => clearInterval(interval);
    }
  }, [selectedSession, isOpen]);

  return (
    <>
      {/* Floating Action Button di Pojok Kanan Bawah */}
      <button
        type="button"
        onClick={toggleWidget}
        className={`fixed bottom-6 z-40 w-13 h-13 rounded-full bg-zinc-900 border border-cyan-500/40 text-cyan-400 hover:text-cyan-300 hover:bg-zinc-800 hover:border-cyan-400 shadow-2xl backdrop-blur-md flex items-center justify-center transition-all duration-300 ease-out hover:scale-105 active:scale-95 group chatbot-widget-btn ${
          isDockOpen ? "right-[604px]" : "right-6"
        }`}
        title="Chatbot Monitoring"
        aria-label="Buka Chatbot Monitoring"
      >
        <MessageSquare className="h-6 w-6 transition-transform group-hover:scale-110" />
      </button>

      {/* Pop-up Window Slide-Up di Kanan Bawah */}
      {isMounted && (
        <div
          className={`fixed bottom-22 z-50 w-[840px] max-w-[calc(100vw-3rem)] h-[580px] max-h-[calc(100vh-7.5rem)] bg-zinc-950/95 border border-zinc-800 rounded-2xl shadow-2xl backdrop-blur-xl flex flex-col overflow-hidden chatbot-monitoring-popup origin-bottom-right transition-all duration-300 ease-out ${
            isDockOpen ? "right-[604px]" : "right-6"
          } ${
            isVisible
              ? "scale-100 opacity-100 translate-y-0"
              : "scale-0 opacity-0 translate-y-4 pointer-events-none"
          }`}
          role="dialog"
          aria-modal="true"
        >
          {/* Header Pop-up */}
          <div className="p-3.5 px-4 bg-zinc-900/80 border-b border-zinc-800 flex items-center justify-between shrink-0">
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-cyan-950 border border-cyan-600/30 flex items-center justify-center text-cyan-400">
                <Bot className="h-4 w-4" />
              </div>
              <div>
                <h2 className="text-xs font-semibold text-zinc-100">Chatbot Monitoring</h2>
                <p className="text-[10px] text-zinc-400">Live feed percakapan customer Telegram &amp; Website</p>
              </div>
            </div>

            <button
              type="button"
              onClick={closeWidget}
              className="p-1 rounded-lg text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/80 transition"
              title="Tutup Monitoring"
              aria-label="Tutup"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Body Pop-up (Dua Panel) */}
          <div className="flex-1 flex overflow-hidden">
            {/* Panel Kiri: Daftar Sesi Customer */}
            <div className="w-72 sm:w-80 shrink-0 border-r border-zinc-800/80 h-full">
              <ChatSessionList
                sessions={sessions}
                selectedSessionId={selectedSession?.name ?? null}
                onSelectSession={(s) => setSelectedSession(s)}
                onOpenSettings={() => setIsSettingsOpen(true)}
                isLoading={loadingSessions}
              />
            </div>

            {/* Panel Kanan: Balon Chat WhatsApp */}
            <ChatTranscriptView
              session={selectedSession}
              messages={messages}
              isLoading={loadingMessages}
            />
          </div>

          {/* Settings Modal (Overlay di dalam pop-up) */}
          <ChatbotSettingsDialog
            isOpen={isSettingsOpen}
            onClose={() => setIsSettingsOpen(false)}
          />
        </div>
      )}
    </>
  );
}
