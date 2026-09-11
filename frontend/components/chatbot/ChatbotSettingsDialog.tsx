"use client";

import { useState, useEffect } from "react";
import { X, Check, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import type { ChatbotSettings } from "./types";

interface ChatbotSettingsDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

const PERSONA_OPTIONS = [
  {
    id: "Ramah & Kasual",
    title: "Ramah & Kasual",
    description: "Bahasa santai, hangat, dan bersahabat dengan emotikon secukupnya. Cocok untuk ritel/F&B/UMKM.",
  },
  {
    id: "Formal & Profesional",
    title: "Formal & Profesional",
    description: "Bahasa baku, tertata rapi, dan profesional. Cocok untuk B2B, kantor hukum, atau konsultan.",
  },
  {
    id: "Ringkas & Solutif",
    title: "Ringkas & Solutif",
    description: "Jawaban singkat, padat, langsung ke inti solusi (to the point) tanpa basa-basi.",
  },
];

export default function ChatbotSettingsDialog({ isOpen, onClose }: ChatbotSettingsDialogProps) {
  const [personaTone, setPersonaTone] = useState("Ramah & Kasual");
  const [customInstructions, setCustomInstructions] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    if (!isOpen) return;

    setLoading(true);
    setErrorMessage("");
    setSavedSuccess(false);

    api<ChatbotSettings>("/chatbot/settings")
      .then((data) => {
        if (data.persona_tone) setPersonaTone(data.persona_tone);
        if (data.custom_instructions !== undefined) setCustomInstructions(data.custom_instructions);
      })
      .catch((err) => {
        console.error("Gagal mengambil pengaturan chatbot:", err);
        setErrorMessage("Gagal memuat pengaturan chatbot.");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSave = async () => {
    setSaving(true);
    setErrorMessage("");
    setSavedSuccess(false);

    try {
      await api<{ success: boolean; message: string }>("/chatbot/settings", {
        method: "POST",
        body: JSON.stringify({
          persona_tone: personaTone,
          custom_instructions: customInstructions,
        }),
      });
      setSavedSuccess(true);
      setTimeout(() => {
        setSavedSuccess(false);
      }, 2500);
    } catch (err: any) {
      console.error("Gagal menyimpan pengaturan chatbot:", err);
      setErrorMessage(err.message || "Gagal menyimpan pengaturan.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-in fade-in duration-150">
      <div className="w-full max-w-[460px] max-h-[490px] rounded-xl border border-zinc-800 bg-zinc-950 shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="p-3 px-4 border-b border-zinc-800/80 bg-zinc-900/60 flex items-center justify-between shrink-0">
          <div>
            <h2 className="text-xs font-semibold text-zinc-100">Pengaturan Bot</h2>
            <p className="text-[10px] text-zinc-400">
              Atur gaya komunikasi dan instruksi khusus customer support
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-md text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/80 transition-colors"
            title="Tutup Pengaturan"
            aria-label="Tutup"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-4 overflow-y-auto space-y-3.5 flex-1">
          {loading ? (
            <div className="py-8 flex flex-col items-center justify-center gap-2 text-zinc-500">
              <Loader2 className="w-4 h-4 animate-spin text-zinc-400" />
              <p className="text-xs">Memuat pengaturan...</p>
            </div>
          ) : (
            <>
              {/* Section 1: Personalisasi / Tone */}
              <div>
                <label className="block text-[11px] font-semibold text-zinc-200 mb-1.5">
                  Personalisasi Gaya Bahasa
                </label>
                <div className="space-y-1.5">
                  {PERSONA_OPTIONS.map((opt) => {
                    const isSelected = personaTone === opt.id;
                    return (
                      <div
                        key={opt.id}
                        onClick={() => setPersonaTone(opt.id)}
                        className={`p-2.5 px-3 rounded-lg border text-left cursor-pointer transition-all ${
                          isSelected
                            ? "bg-zinc-900 border-cyan-500/60 ring-1 ring-cyan-500/30"
                            : "bg-zinc-900/40 border-zinc-800/80 hover:border-zinc-700 hover:bg-zinc-900/70"
                        }`}
                      >
                        <div className="flex items-center justify-between mb-0.5">
                          <span
                            className={`text-xs font-medium ${
                              isSelected ? "text-cyan-300" : "text-zinc-200"
                            }`}
                          >
                            {opt.title}
                          </span>
                          <div
                            className={`w-3.5 h-3.5 rounded-full border flex items-center justify-center ${
                              isSelected
                                ? "border-cyan-400 bg-cyan-400"
                                : "border-zinc-600 bg-transparent"
                            }`}
                          >
                            {isSelected && <div className="w-1.5 h-1.5 rounded-full bg-zinc-950" />}
                          </div>
                        </div>
                        <p className="text-[10px] text-zinc-400 leading-snug">
                          {opt.description}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Section 2: Instruksi Khusus */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-[11px] font-semibold text-zinc-200">
                    Instruksi Khusus Tambahan
                  </label>
                  <span className="text-[10px] text-zinc-500 font-mono">
                    {customInstructions.length} / 1000 karakter
                  </span>
                </div>
                <p className="text-[10px] text-zinc-400 mb-1.5">
                  Arahan spesifik untuk bot (misal: jam operasional toko, penawaran diskon, atau kontak WhatsApp).
                </p>
                <textarea
                  value={customInstructions}
                  onChange={(e) => setCustomInstructions(e.target.value.slice(0, 1000))}
                  placeholder="Contoh: Toko buka pukul 08:00 - 21:00 WIB. Diskon hanya berlaku dengan kode HEMAT10."
                  rows={3}
                  className="w-full rounded-lg border border-zinc-800 bg-zinc-900/70 px-3 py-2 text-xs text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600 focus:ring-1 focus:ring-zinc-600 resize-none transition-colors"
                />
              </div>

              {/* Feedback Notifications */}
              {errorMessage && (
                <div className="p-2 rounded-md bg-red-950/40 border border-red-800/40 text-[11px] text-red-400">
                  {errorMessage}
                </div>
              )}

              {savedSuccess && (
                <div className="p-2 rounded-md bg-emerald-950/40 border border-emerald-800/40 text-[11px] text-emerald-400 flex items-center gap-1.5">
                  <Check className="w-3.5 h-3.5 shrink-0" />
                  <span>Pengaturan chatbot berhasil disimpan.</span>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="p-2.5 px-4 border-t border-zinc-800/80 bg-zinc-950/90 flex items-center justify-end gap-2 shrink-0">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="px-3 py-1.5 rounded-lg border border-zinc-800 bg-zinc-900 text-xs font-medium text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100 transition-colors disabled:opacity-50"
          >
            Tutup
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || loading}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-zinc-100 text-xs font-medium text-zinc-900 hover:bg-zinc-200 transition-colors disabled:opacity-50"
          >
            {saving ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>Menyimpan...</span>
              </>
            ) : (
              <span>Simpan Pengaturan</span>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
