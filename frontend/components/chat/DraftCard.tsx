"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";

interface DraftCardProps {
  draftId: string;
}

export function DraftCard({ draftId }: DraftCardProps) {
  const [draft, setDraft] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    console.log("[DraftCard] mount/re-mount untuk draftId:", draftId);
    const fetchDraft = async () => {
      console.log("[DraftCard] mulai fetch...");
      try {
        const res = await api<any>(`/method/aios_v1.lib.draft_manager.get_draft?draft_id=${draftId}`);
        console.log("[DraftCard] response raw:", res);
        const actual = res.message || res.data || res;
        console.log("[DraftCard] data draft:", actual);
        setDraft(actual);
      } catch (e: any) {
        console.error("[DraftCard] error fetch:", e);
        setError(e.message || "Gagal memuat draf");
      } finally {
        console.log("[DraftCard] fetch selesai, setLoading false");
        setLoading(false);
      }
    };
    fetchDraft();
  }, [draftId]);

  const handleAction = async (action: "approve_draft" | "reject_draft") => {
    setProcessing(true);
    try {
      await api(`/method/aios_v1.lib.draft_manager.${action}`, {
        method: "POST",
        body: JSON.stringify({ draft_id: draftId })
      });
      // Update local state to reflect the change
      setDraft((prev: any) => ({
        ...prev,
        status: action === "approve_draft" ? "APPROVED" : "REJECTED"
      }));
    } catch (e: any) {
      alert(e.message || `Gagal ${action}`);
    } finally {
      setProcessing(false);
    }
  };

  if (loading) return <div className="draft-card loading">Memuat draf {draftId}...</div>;
  if (error) return <div className="draft-card error">Error: {error}</div>;
  if (!draft) return null;

  // Pretty print JSON if payload is stringified JSON
  let formattedPayload = draft.payload;
  try {
    const parsed = JSON.parse(draft.payload);
    formattedPayload = JSON.stringify(parsed, null, 2);
  } catch (e) {
    // Keep as is if not valid JSON
  }

  // Render minimal card
  return (
    <div className={`draft-card status-${draft.status.toLowerCase()}`}>
      <div className="draft-header">
        <h4>&#128196; Draf Aksi: {draft.type}</h4>
        <span className="badge">{draft.status}</span>
      </div>
      <div className="draft-body">
        <p><strong>ID:</strong> {draft.name}</p>
        <p><strong>Task:</strong> {draft.task_id}</p>
        <pre className="draft-payload">{formattedPayload}</pre>
      </div>
      
      {draft.status === "PENDING_APPROVAL" && (
        <div className="draft-actions">
          <button 
            className="btn btn-approve" 
            onClick={() => handleAction("approve_draft")}
            disabled={processing}
          >
            &#10003; Setujui
          </button>
          <button 
            className="btn btn-reject" 
            onClick={() => handleAction("reject_draft")}
            disabled={processing}
          >
            &#10007; Tolak
          </button>
        </div>
      )}
      
      <style jsx>{`
        .draft-card {
          border: 1px solid var(--acc-line, #ccc);
          border-radius: 8px;
          padding: 12px;
          margin: 12px 0;
          background: var(--acc-soft, rgba(0,0,0,0.05));
          font-family: monospace;
        }
        .draft-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
          font-family: sans-serif;
        }
        .draft-header h4 {
          margin: 0;
          font-size: 14px;
        }
        .badge {
          font-size: 11px;
          padding: 3px 8px;
          border-radius: 12px;
          background: #444;
          color: white;
          font-weight: bold;
        }
        .status-approved { border-color: #10b981; }
        .status-approved .badge { background: #10b981; }
        .status-rejected { border-color: #ef4444; }
        .status-rejected .badge { background: #ef4444; }
        .status-expired .badge { background: #6b7280; }
        .draft-body p {
          margin: 4px 0;
          font-size: 13px;
          font-family: sans-serif;
        }
        .draft-payload {
          background: rgba(0,0,0,0.4);
          color: #e2e8f0;
          padding: 10px;
          border-radius: 6px;
          font-size: 12px;
          overflow-x: auto;
          white-space: pre-wrap;
          margin-top: 10px;
          border: 1px solid rgba(255,255,255,0.1);
        }
        .draft-actions {
          display: flex;
          gap: 8px;
          margin-top: 12px;
        }
        .btn {
          flex: 1;
          padding: 8px;
          border: none;
          border-radius: 6px;
          cursor: pointer;
          font-weight: 600;
          color: white;
          transition: opacity 0.2s;
        }
        .btn:hover { opacity: 0.9; }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-approve { background: #10b981; }
        .btn-reject { background: #ef4444; }
      `}</style>
    </div>
  );
}
