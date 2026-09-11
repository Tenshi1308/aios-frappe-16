"use client";

import { useEffect, useState } from "react";
import {
  X,
  UserSearch,
  ChevronRight,
  ArrowLeft,
  Clock,
  Globe,
  Quote,
  MessageSquare,
  Share2,
  Calendar,
  ExternalLink,
} from "lucide-react";
import {
  LeadItem,
  SortOrder,
  sortLeads,
  MOCK_LEADS,
  formatSmartTimestamp,
  formatFullTimestamp,
} from "@/lib/mock-leads";

interface LeadModalProps {
  isOpen: boolean;
  onClose: () => void;
}

// Komponen Logo Aplikasi Resmi (Instagram, Facebook, Forum)
function PlatformLogo({
  platform,
  size = 18,
  showLabel = false,
}: {
  platform: string;
  size?: number;
  showLabel?: boolean;
}) {
  if (platform === "instagram") {
    return (
      <span className="platform-logo-wrap" title="Instagram" aria-label="Instagram">
        <svg
          width={size}
          height={size}
          viewBox="0 0 24 24"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="platform-svg"
        >
          <defs>
            <linearGradient id="ig-grad-lead" x1="0%" y1="100%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#f09433" />
              <stop offset="25%" stopColor="#e6683c" />
              <stop offset="50%" stopColor="#dc2743" />
              <stop offset="75%" stopColor="#cc2366" />
              <stop offset="100%" stopColor="#bc1888" />
            </linearGradient>
          </defs>
          <rect x="2" y="2" width="20" height="20" rx="5.5" stroke="url(#ig-grad-lead)" strokeWidth="2.2" />
          <circle cx="12" cy="12" r="4.5" stroke="url(#ig-grad-lead)" strokeWidth="2.2" />
          <circle cx="17.5" cy="6.5" r="1.3" fill="url(#ig-grad-lead)" />
        </svg>
        {showLabel && <span className="platform-name-text">Instagram</span>}
      </span>
    );
  }

  if (platform === "facebook") {
    return (
      <span className="platform-logo-wrap" title="Facebook" aria-label="Facebook">
        <svg
          width={size}
          height={size}
          viewBox="0 0 24 24"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="platform-svg"
        >
          <rect width="24" height="24" rx="5.5" fill="#1877F2" />
          <path
            d="M15.5 12.5H13V20H10V12.5H8.5V10H10V8.25C10 6.75 11 5.5 13 5.5H15.5V8H14C13.5 8 13 8.35 13 9V10H15.5L15 12.5Z"
            fill="white"
          />
        </svg>
        {showLabel && <span className="platform-name-text">Facebook</span>}
      </span>
    );
  }

  // Forum / Komunitas
  return (
    <span className="platform-logo-wrap" title="Forum Diskusi Publik" aria-label="Forum Diskusi Publik">
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="platform-svg"
      >
        <rect width="24" height="24" rx="5.5" fill="rgba(245, 158, 11, 0.2)" stroke="#f59e0b" strokeWidth="1.5" />
        <path d="M7 8.5C7 7.4 7.9 6.5 9 6.5H15C16.1 6.5 17 7.4 17 8.5V12C17 13.1 16.1 14 15 14H10L7 17V8.5Z" fill="#f59e0b" />
      </svg>
      {showLabel && <span className="platform-name-text">Forum Diskusi</span>}
    </span>
  );
}

export default function LeadModal({ isOpen, onClose }: LeadModalProps) {
  const [selectedLead, setSelectedLead] = useState<LeadItem | null>(null);
  const [sortOrder, setSortOrder] = useState<SortOrder>("asc"); // asc = terbaru (default), desc = terlama
  const leads = sortLeads(MOCK_LEADS, sortOrder);

  // Reset state saat modal ditutup
  useEffect(() => {
    if (!isOpen) {
      setSelectedLead(null);
    }
  }, [isOpen]);

  // Listener tombol Escape
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (selectedLead) {
          setSelectedLead(null); // Jika di detail, tekan Esc kembali ke list
        } else {
          onClose(); // Jika di list, tekan Esc menutup modal
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, selectedLead, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="lead-modal-backdrop"
      onClick={(e) => {
        // Klik di area backdrop luar akan menutup modal
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="lead-modal-title"
    >
      <div
        className="lead-modal-dialog"
        onClick={(e) => e.stopPropagation()} // Cegah event tembus ke canvas/peta
        onWheel={(e) => e.stopPropagation()} // Cegah event wheel dibajak oleh zoom peta
      >
        {/* Header Modal */}
        <div className="lead-modal-header">
          <div className="lead-modal-title-wrap">
            <div className="lead-modal-icon-badge">
              <UserSearch size={20} />
            </div>
            <div className="lead-modal-title-text">
              <h3 id="lead-modal-title">
                Lead AI Generator
              </h3>
              <p>Daftar calon customer potensial untuk produk perusahaan Anda</p>
            </div>
          </div>
          <button
            type="button"
            className="lead-modal-close-btn"
            onClick={onClose}
            aria-label="Tutup pop-up"
            title="Tutup (Esc)"
          >
            <X size={18} />
          </button>
        </div>

        {/* Body Modal: List View ATAU Detail View */}
        <div className="lead-modal-body" onWheel={(e) => e.stopPropagation()}>
          {selectedLead === null ? (
            /* ============================================================
               1. TAMPILAN LIST VIEW (DAFTAR PROSPEK - NEWEST FIRST)
               ============================================================ */
            <div className="lead-list-view">
              <div className="lead-list-header">
                <span className="lead-list-count">
                  Menampilkan <strong>{leads.length}</strong> calon customer potensial
                </span>
                <div className="lead-sort-control">
                  <div className="lead-sort-group">
                    <button
                      type="button"
                      className={`lead-sort-btn ${sortOrder === "asc" ? "active" : ""}`}
                      onClick={() => setSortOrder("asc")}
                      title="Urutkan dari yang terbaru (Asc)"
                    >
                      Terbaru (Asc)
                    </button>
                    <button
                      type="button"
                      className={`lead-sort-btn ${sortOrder === "desc" ? "active" : ""}`}
                      onClick={() => setSortOrder("desc")}
                      title="Urutkan dari yang terlama (Desc)"
                    >
                      Terlama (Desc)
                    </button>
                  </div>
                </div>
              </div>

              <div className="lead-list">
                {leads.map((lead) => (
                  <div
                    key={lead.id}
                    className="lead-item"
                    onClick={() => setSelectedLead(lead)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setSelectedLead(lead);
                      }
                    }}
                    title="Klik untuk melihat detail postingan & kontak"
                  >
                    {/* Sisi Kiri: Nama + Logo Platform + Snippet Postingan */}
                    <div className="lead-item-left">
                      <div className="lead-item-identity">
                        <span className="lead-item-name">{lead.name}</span>
                        <PlatformLogo platform={lead.platform} size={17} />
                      </div>
                      <div className="lead-item-preview">
                        &ldquo;{lead.content}&rdquo;
                      </div>
                    </div>

                    {/* Sisi Kanan: Smart Timestamp + Indikator Panah */}
                    <div className="lead-item-right">
                      <span className="lead-timestamp">
                        {formatSmartTimestamp(lead.detectedAt)}
                      </span>
                      <ChevronRight size={16} className="lead-chevron" />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            /* ============================================================
               2. TAMPILAN DETAIL VIEW (SAAT ITEM LIST DIKLIK)
               ============================================================ */
            <div className="lead-detail-wrap">
              {/* Baris Navigasi Kembali */}
              <div className="lead-detail-nav">
                <button
                  type="button"
                  className="lead-back-btn"
                  onClick={() => setSelectedLead(null)}
                  title="Kembali ke daftar calon customer"
                >
                  <ArrowLeft size={14} /> Kembali ke Daftar
                </button>
                <div className="lead-detail-timestamp-top">
                  <Calendar size={12} />
                  <span>{formatFullTimestamp(selectedLead.detectedAt)}</span>
                </div>
              </div>

              {/* Card 1: Identitas & Akun Kontak */}
              <div className="lead-card-section">
                <div className="lead-profile-header">
                  <div className="lead-profile-main">
                    <h4>{selectedLead.name}</h4>
                    <span className="lead-contact-handle">
                      {selectedLead.contact}
                    </span>
                  </div>
                  <div>
                    <PlatformLogo platform={selectedLead.platform} size={22} showLabel={true} />
                  </div>
                </div>

                {/* Keterangan Platform Asal Temuan & Link Postingan Asli */}
                <div className="lead-platform-origin">
                  <Globe size={15} style={{ color: "#22d3ee", flexShrink: 0, marginTop: "2px" }} />
                  <div className="lead-platform-origin-body">
                    <div>
                      Ditemukan pada postingan publik di saluran <strong>{selectedLead.platformLabel}</strong>
                    </div>
                    <a
                      href={selectedLead.sourceUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="lead-source-link"
                      title="Buka postingan asli di tab baru"
                    >
                      <span>{selectedLead.sourceUrl}</span>
                      <ExternalLink size={12} />
                    </a>
                  </div>
                </div>
              </div>

              {/* Card 2: Isi Postingan / Pesan Asli Calon Customer */}
              <div className="lead-quote-card">
                <div className="lead-quote-title">
                  <Quote size={15} />
                  <span>Kutipan Postingan Asli Calon Customer:</span>
                </div>

                <div className="lead-quote-content">
                  &ldquo;{selectedLead.content}&rdquo;
                </div>

                <div className="lead-quote-footer">
                  <Share2 size={12} />
                  <span>
                    Dipindai secara otomatis oleh AIOS Lead Engine • Akun sumber: {selectedLead.contact}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
