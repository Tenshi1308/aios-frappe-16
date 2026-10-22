"use client";

// D1/D2: Dashboard monitoring Ekasa Developer — pemakaian token & estimasi
// biaya per perusahaan. Drill-down INLINE: detail bidang melebar persis di
// bawah baris perusahaan yang diklik; rincian worker melebar persis di bawah
// bidang yang diklik. Tanpa akses data bisnis/percakapan client.
import { Fragment, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, apiMethod, fmtNum } from "@/lib/api";
import SpaceBackdrop from "@/components/shared/SpaceBackdrop";
import type { UsageBranch, UsageCompany, UsageWorker } from "@/lib/types";

const fmtRp = (n: number) => "Rp " + fmtNum(Math.round(n));

export default function DeveloperDashboardPage() {
  const router = useRouter();
  const [companies, setCompanies] = useState<UsageCompany[]>([]);
  const [pricing, setPricing] = useState<{ per1kInputIdr: number; per1kOutputIdr: number } | null>(null);
  const [expandedCompany, setExpandedCompany] = useState<string | null>(null);
  const [branches, setBranches] = useState<Record<string, UsageBranch[]>>({});
  const [expandedBranchKey, setExpandedBranchKey] = useState<string | null>(null);
  const [workersMap, setWorkersMap] = useState<Record<string, UsageWorker[]>>({});
  const [loadingBranchKey, setLoadingBranchKey] = useState<string | null>(null);

  useEffect(() => {
    api("/auth/me")
      .then(() =>
        api<{ companies: UsageCompany[]; pricing: { per1kInputIdr: number; per1kOutputIdr: number } }>("/monitoring/usage"),
      )
      .then((d) => {
        setCompanies(d.companies);
        setPricing(d.pricing);
      })
      .catch(() => router.replace("/developer/login"));
  }, [router]);

  useEffect(() => {
    apiMethod<{ csrf_token: string }>("/method/aios_v1.setup.get_session_context")
      .then((ctx) => {
        if (typeof window !== "undefined") (window as any).csrf_token = ctx.csrf_token;
      })
      .catch(() => {});
  }, []);

  const toggleCompany = useCallback(
    async (c: UsageCompany) => {
      if (expandedCompany === c.id) {
        setExpandedCompany(null);
        setExpandedBranchKey(null);
        return;
      }
      setExpandedCompany(c.id);
      setExpandedBranchKey(null);
      if (!branches[c.id]) {
        const d = await api<{ branches: UsageBranch[] }>(`/monitoring/usage/${encodeURIComponent(c.id)}`);
        setBranches((prev) => ({ ...prev, [c.id]: d.branches }));
      }
    },
    [expandedCompany, branches],
  );

  const toggleBranch = useCallback(
    async (userId: string, branch: string) => {
      const key = `${userId}:${branch}`;
      if (expandedBranchKey === key) {
        setExpandedBranchKey(null);
        return;
      }
      setExpandedBranchKey(key);
      if (!workersMap[key]) {
        setLoadingBranchKey(key);
        try {
          const d = await api<{ workers: UsageWorker[] }>(`/monitoring/usage/${encodeURIComponent(userId)}/${encodeURIComponent(branch)}`);
          setWorkersMap((prev) => ({ ...prev, [key]: d.workers }));
        } finally {
          setLoadingBranchKey(null);
        }
      }
    },
    [expandedBranchKey, workersMap],
  );

  const totalIn = companies.reduce((s, c) => s + c.inputTokens, 0);
  const totalOut = companies.reduce((s, c) => s + c.outputTokens, 0);
  const totalCost = companies.reduce((s, c) => s + c.costIdr, 0);

  const logout = async () => {
    await api("/method/logout", { method: "POST" }).catch(() => {});
    router.replace("/developer/login");
  };

  return (
    <main className="page px-4 py-0">
      <SpaceBackdrop />
      <header className="page-topbar">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 22px" }}>
          <div className="brand">
            <span className="dot" />
            AIOS <span className="page-sub" style={{ marginTop: 0 }}>· Ekasa Developer</span>
          </div>
          <button type="button" className="btn btn-outline btn-sm" onClick={logout}>
            Keluar
          </button>
        </div>
      </header>

      <div className="mx-auto w-full py-8" style={{ maxWidth: 1024, flex: 1 }}>
        <div className="page-title">Monitoring pemakaian token</div>
        <p className="page-sub">
          Ringkasan per perusahaan — klik baris untuk membuka rincian bidang tepat di bawahnya; klik bidang untuk rincian worker.
          {pricing && (
            <> Estimasi biaya: {fmtRp(pricing.per1kInputIdr)}/1k token input · {fmtRp(pricing.per1kOutputIdr)}/1k token output.</>
          )}
        </p>

        <div className="mt-5 grid gap-3 sm:grid-cols-4">
          <div className="stat">
            <div className="k">Perusahaan client</div>
            <div className="v">{companies.length}</div>
          </div>
          <div className="stat">
            <div className="k">Input token</div>
            <div className="v cyan">{fmtNum(totalIn)}</div>
          </div>
          <div className="stat">
            <div className="k">Consumed token</div>
            <div className="v violet">{fmtNum(totalOut)}</div>
          </div>
          <div className="stat">
            <div className="k">Estimasi biaya total</div>
            <div className="v">{fmtRp(totalCost)}</div>
          </div>
        </div>

        <section className="card mt-5" style={{ overflow: "hidden" }}>
          <div style={{ padding: "16px 18px 0" }}>
            <div style={{ fontWeight: 800 }}>Pemakaian per client</div>
          </div>
          <div className="overflow-x-auto mt-2">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Perusahaan</th>
                  <th>Status</th>
                  <th className="num">Percakapan</th>
                  <th className="num">Input token</th>
                  <th className="num">Consumed token</th>
                  <th className="num">Estimasi biaya</th>
                </tr>
              </thead>
              <tbody>
                {companies.map((c) => (
                  <Fragment key={c.id}>
                    <tr
                      className="rowbtn-parent"
                      style={{ cursor: "pointer" }}
                      onClick={() => toggleCompany(c)}
                    >
                      <td style={{ fontWeight: 700 }}>
                        <span style={{ display: "inline-block", width: 14, color: "var(--primary)" }}>
                          {expandedCompany === c.id ? "▾" : "▸"}
                        </span>
                        {c.name}
                      </td>
                      <td>
                        <span className={`pill ${c.status === "ACTIVE" ? "pill-ok" : "pill-warn"}`}>{c.status}</span>
                      </td>
                      <td className="num">{c.conversations}</td>
                      <td className="num" style={{ color: "var(--primary)" }}>{fmtNum(c.inputTokens)}</td>
                      <td className="num" style={{ color: "var(--accent)" }}>{fmtNum(c.outputTokens)}</td>
                      <td className="num">{fmtRp(c.costIdr)}</td>
                    </tr>

                    {/* D2: rincian bidang — INLINE, persis di bawah baris perusahaan */}
                    {expandedCompany === c.id && (
                      <tr className="detail-row">
                        <td colSpan={6}>
                          {(branches[c.id] ?? []).length === 0 ? (
                            <p className="page-sub">Belum ada pemakaian tercatat.</p>
                          ) : (
                            <div style={{ display: "grid", gap: 2 }}>
                              {(branches[c.id] ?? []).map((b) => {
                                const max = Math.max(
                                  1,
                                  ...(branches[c.id] ?? []).map((x) => x.inputTokens + x.outputTokens),
                                );
                                const w = ((b.inputTokens + b.outputTokens) / max) * 100;
                                const branchKey = `${c.id}:${b.branch}`;
                                const open = expandedBranchKey === branchKey;
                                const isLoading = loadingBranchKey === branchKey;
                                const workerList = workersMap[branchKey] ?? [];
                                return (
                                  <div key={b.branch}>
                                    <button type="button" className="rowbtn branch-item" onClick={() => toggleBranch(c.id, b.branch)}>
                                      <div className="bi-head">
                                        <span className="bi-name">
                                          <span style={{ display: "inline-block", width: 12, color: "var(--primary)" }}>{open ? "▾" : "▸"}</span>
                                          {b.branch}
                                        </span>
                                        <span className="muted" style={{ fontSize: 12 }}>
                                          in {fmtNum(b.inputTokens)} · out {fmtNum(b.outputTokens)} · {b.calls} panggilan · {fmtRp(b.costIdr)}
                                        </span>
                                      </div>
                                      <div className="meter mt-1">
                                        <span style={{ width: `${w}%` }} />
                                      </div>
                                    </button>

                                    {/* rincian worker — INLINE, persis di bawah bidangnya */}
                                    {open && (
                                      isLoading ? (
                                        <p className="page-sub" style={{ margin: "6px 0 10px 20px" }}>Memuat rincian worker...</p>
                                      ) : workerList.length === 0 ? (
                                        <p className="page-sub" style={{ margin: "6px 0 10px 20px" }}>Belum ada pemakaian worker tercatat.</p>
                                      ) : (
                                        <table className="tbl" style={{ margin: "6px 0 10px 20px", width: "calc(100% - 20px)" }}>
                                          <thead>
                                            <tr>
                                              <th>Worker</th>
                                              <th className="num">Input</th>
                                              <th className="num">Consumed</th>
                                              <th className="num">Panggilan</th>
                                              <th className="num">Estimasi biaya</th>
                                            </tr>
                                          </thead>
                                          <tbody>
                                            {workerList.map((w2) => (
                                              <tr key={w2.workerKey}>
                                                <td className="mono">{w2.workerKey}</td>
                                                <td className="num" style={{ color: "var(--primary)" }}>{fmtNum(w2.inputTokens)}</td>
                                                <td className="num" style={{ color: "var(--accent)" }}>{fmtNum(w2.outputTokens)}</td>
                                                <td className="num">{w2.calls}</td>
                                                <td className="num">{fmtRp(w2.costIdr)}</td>
                                              </tr>
                                            ))}
                                          </tbody>
                                        </table>
                                      )
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
                {companies.length === 0 && (
                  <tr>
                    <td colSpan={6} className="page-sub" style={{ textAlign: "center", padding: 18 }}>
                      Belum ada client terdaftar
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </main>
  );
}
