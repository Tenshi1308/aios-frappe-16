"use client";

// C6/C14: Validasi hasil mapping — confidence, konfirmasi, edit manual.
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import SpaceBackdrop from "@/components/shared/SpaceBackdrop";
import type { MappingView } from "@/lib/types";

interface SchemaOptions {
  tables: { name: string; columns: string[] }[];
}

export default function MappingPage() {
  const router = useRouter();
  const [mapping, setMapping] = useState<MappingView | null>(null);
  const [schemaOptions, setSchemaOptions] = useState<SchemaOptions>({ tables: [] });
  const [edits, setEdits] = useState<Record<number, { table: string; column: string }>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    try {
      await api("/auth/me");
      const d = await api<{ mapping: MappingView; schemaOptions: SchemaOptions }>("/mapping/review");
      setMapping(d.mapping);
      setSchemaOptions(d.schemaOptions);
    } catch (err) {
      const msg = (err as Error)?.message || "";
      if (msg.includes("401") || msg.includes("Belum login")) {
        router.replace("/login");
        return;
      }
      setError(msg);
    }
  }, [router]);

  useEffect(() => {
    load();
  }, [load]);

  const grouped = useMemo(() => {
    const g: Record<string, MappingView["entries"]> = {};
    for (const e of mapping?.entries ?? []) (g[e.canonicalEntity] ??= []).push(e);
    return g;
  }, [mapping]);

  const lowCount = mapping?.entries.filter((e) => e.lowConfidence).length ?? 0;

  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      const updates = (mapping?.entries ?? []).map((e) => {
        const edit = edits[e.id];
        if (edit) return { entryId: e.id, action: "edit" as const, sourceTable: edit.table, sourceColumn: edit.column };
        return { entryId: e.id, action: "confirm" as const };
      });
      await api("/mapping/validate", { method: "POST", body: JSON.stringify({ updates }) });
      setSaved(true);
      setTimeout(() => router.push("/home"), 900);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="page px-4 py-10">
      <SpaceBackdrop />
      <div className="mx-auto w-full" style={{ maxWidth: 920 }}>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <div className="page-title">Validasi pemahaman data Anda</div>
            <p className="page-sub">AIOS telah mempelajari struktur database Anda. Periksa pemetaan berikut — perbaiki bila kurang tepat, lalu konfirmasi.</p>
          </div>
          {mapping && (
            <div style={{ textAlign: "right" }}>
              <span className={`pill ${mapping.status === "VALIDATED" ? "pill-ok" : "pill-warn"}`}>
                {mapping.status === "VALIDATED" ? "Tervalidasi" : "Menunggu konfirmasi Anda"}
              </span>
              <div className="page-sub" style={{ marginTop: 4 }}>
                versi v{mapping.version} · keyakinan {(mapping.overallConfidence * 100).toFixed(0)}%
              </div>
            </div>
          )}
        </div>

        {lowCount > 0 && (
          <div className="alert alert-warn mt-4">{lowCount} pemetaan memiliki keyakinan rendah — mohon periksa baris bertanda kuning.</div>
        )}
        {error && <div className="alert alert-err mt-4">{error}</div>}
        {saved && <div className="alert alert-ok mt-4">Pemetaan tervalidasi — menuju AIOS…</div>}

        <div className="mt-6" style={{ display: "grid", gap: 18 }}>
          {Object.entries(grouped).map(([entity, entries]) => (
            <section key={entity} className="card card-pad">
              <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 12 }}>
                <span className="mono" style={{ fontSize: 15, fontWeight: 700, color: "#a5e9fb" }}>{entity}</span>
                <span className="page-sub">{entries.length} konsep dipetakan</span>
              </div>
              <div className="overflow-x-auto">
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>Konsep AIOS</th>
                      <th>Data Anda</th>
                      <th>Keyakinan</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {entries.map((e) => {
                      const edit = edits[e.id];
                      const cols = schemaOptions.tables.find((t) => t.name === (edit?.table ?? e.sourceTable))?.columns ?? [];
                      return (
                        <tr key={e.id} style={e.lowConfidence ? { background: "rgba(251,191,36,0.05)" } : undefined}>
                          <td className="mono">{e.canonicalEntity}.{e.canonicalField}</td>
                          <td>
                            <div className="flex gap-1.5">
                              <select
                                className="input mono"
                                style={{ width: 150, padding: "5px 8px", fontSize: 12.5 }}
                                value={edit?.table ?? e.sourceTable}
                                onChange={(ev) => setEdits({ ...edits, [e.id]: { table: ev.target.value, column: "" } })}
                              >
                                <option value={edit?.table ?? e.sourceTable}>{edit?.table ?? e.sourceTable}</option>
                                {schemaOptions.tables.filter((t) => t.name !== (edit?.table ?? e.sourceTable)).map((t) => (
                                  <option key={t.name} value={t.name}>{t.name}</option>
                                ))}
                              </select>
                              <select
                                className="input mono"
                                style={{ width: 150, padding: "5px 8px", fontSize: 12.5 }}
                                value={edit?.column ?? e.sourceColumn}
                                onChange={(ev) => setEdits({ ...edits, [e.id]: { table: edit?.table ?? e.sourceTable, column: ev.target.value } })}
                              >
                                <option value={edit?.column ?? e.sourceColumn}>{edit?.column ?? e.sourceColumn}</option>
                                {cols.filter((c) => c !== (edit?.column ?? e.sourceColumn)).map((c) => (
                                  <option key={c} value={c}>{c}</option>
                                ))}
                              </select>
                            </div>
                          </td>
                          <td>
                            <span className={`pill ${e.confidence >= 0.9 ? "pill-ok" : e.confidence >= 0.7 ? "pill-info" : "pill-warn"}`}>
                              {(e.confidence * 100).toFixed(0)}%
                            </span>
                          </td>
                          <td>
                            <span className={`pill ${edits[e.id] ? "pill-info" : (e.state || "AI_SUGGESTED") === "AI_SUGGESTED" ? "" : "pill-ok"}`}>
                              {edits[e.id] ? "diedit" : (e.state || "AI_SUGGESTED") === "AI_SUGGESTED" ? "usulan AI" : (e.state || "").toLowerCase()}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          ))}
        </div>

        {mapping && (
          <div className="mt-8 flex items-center gap-3">
            <button type="button" className="btn btn-primary" disabled={busy} onClick={submit}>
              {busy ? "Menyimpan…" : "Konfirmasi & mulai pakai AIOS"}
            </button>
            <button type="button" className="btn btn-outline" onClick={() => router.push("/home")}>
              Nanti saja
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
