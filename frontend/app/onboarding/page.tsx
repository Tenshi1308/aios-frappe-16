"use client";

// C4: Hubungkan database — 2 jalur (FR-32A): kredensial existing atau buat
// database baru (provisioning Ekasa, template/custom — FR-32B/C).
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import SpaceBackdrop from "@/components/shared/SpaceBackdrop";

interface CustomTable {
  name: string;
  columns: { name: string; type: "text" | "number" | "date" }[];
}

export default function OnboardingPage() {
  const router = useRouter();
  const [path, setPath] = useState<"existing" | "new">("existing");
  const [engine, setEngine] = useState<"sqlite" | "postgres" | "mariadb">("sqlite");
  const [conn, setConn] = useState({ host: "localhost", port: 5432, user: "postgres", password: "", database: "", path: "" });
  const [provMode, setProvMode] = useState<"template" | "custom">("template");
  const [tables, setTables] = useState<CustomTable[]>([{ name: "", columns: [{ name: "", type: "text" }] }]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  // Layar progres adaptasi background (C5): analisis skema jalan di server,
  // halaman ini hanya memantau statusnya via polling. Waktu mulai diambil
  // dari SERVER (bukan browser) agar navigasi tidak mereset timer.
  const [view, setView] = useState<"form" | "progress">("form");
  const [done, setDone] = useState(false);
  const [adaptError, setAdaptError] = useState<string | null>(null);
  const [serverStartedAt, setServerStartedAt] = useState<number | null>(null);
  const [localStartedAt, setLocalStartedAt] = useState<number | null>(null);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [elapsed, setElapsed] = useState(0);
  // Mode "ganti DB" — datang dari /settings (?change=1) → tampilkan tombol kembali.
  const [changeMode, setChangeMode] = useState(false);

  useEffect(() => {
    (async () => {
      // 1. Wajib login terlebih dahulu
      try {
        await api("/auth/me");
      } catch {
        router.replace("/login");
        return;
      }

      // 2. Datang dari /settings untuk GANTI database (?change=1) → biarkan form
      // tampil, jangan auto-redirect ke mapping.
      const isChange =
        typeof window !== "undefined" &&
        new URLSearchParams(window.location.search).get("change") === "1";
      if (isChange) {
        setChangeMode(true);
        return;
      }

      // 3. Cek status koneksi & mapping
      try {
        const d = await api<{ adapting: boolean; mappingStatus: string }>("/connection/status");
        if (d.mappingStatus === "NEEDS_REVIEW" || d.mappingStatus === "VALIDATED") {
          router.replace("/onboarding/mapping");
          return;
        }
        if (d.adapting) enterProgress();
      } catch {
        router.replace("/login");
      }
    })();
  }, [router]);

  const enterProgress = () => {
    setLocalStartedAt(Date.now());
    setElapsed(0);
    setDone(false);
    setAdaptError(null);
    setView("progress");
  };

  // Polling status adaptasi selama layar progres aktif
  useEffect(() => {
    if (view !== "progress" || done || adaptError) return;
    const tick = () =>
      api<{
        adapting: boolean;
        adaptError: string | null;
        mappingStatus: string;
        startedAt: string | null;
        progress: { done: number; total: number } | null;
      }>("/connection/status")
        .then((d) => {
          if (d.startedAt) setServerStartedAt(Date.parse(d.startedAt));
          if (d.progress) setProgress(d.progress);
          if (d.mappingStatus === "NEEDS_REVIEW" || d.mappingStatus === "VALIDATED") {
            setDone(true);
          } else if (!d.adapting) {
            setAdaptError(
              d.adaptError ??
                "Proses analisis terhenti (kemungkinan server dimulai ulang). Silakan hubungkan ulang database.",
            );
          }
        })
        .catch(() => {});
    tick();
    const id = setInterval(tick, 4000);
    return () => clearInterval(id);
  }, [view, done, adaptError]);

  // Timer berjalan selama analisis belum selesai — pakai waktu mulai SERVER
  const effectiveStart = serverStartedAt ?? localStartedAt;
  useEffect(() => {
    if (view !== "progress" || done || adaptError || !effectiveStart) return;
    const id = setInterval(() => setElapsed(Math.max(0, Math.floor((Date.now() - effectiveStart) / 1000))), 1000);
    return () => clearInterval(id);
  }, [view, done, adaptError, effectiveStart]);

  const connectExisting = async () => {
    setBusy(true);
    setError("");
    try {
      const body = engine === "sqlite" ? { engine, path: conn.path } : { engine, ...conn, port: Number(conn.port) };
      await api<{ adapting: boolean }>("/connection/connect", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setInfo("Database terhubung. Analisis skema berjalan di background.");
      enterProgress();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const provisionNew = async () => {
    setBusy(true);
    setError("");
    try {
      const body =
        provMode === "template"
          ? { mode: "template" }
          : {
              mode: "custom",
              tables: tables.filter((t) => t.name.trim()).map((t) => ({ name: t.name.trim(), columns: t.columns.filter((c) => c.name.trim()) })),
            };
      const res = await api<{ adapting: boolean; connection: { database: string } }>(
        "/connection/provision",
        { method: "POST", body: JSON.stringify(body) },
      );
      setInfo(`Database baru dibuat (${res.connection.database}). Analisis skema berjalan di background.`);
      enterProgress();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="page items-center px-4 py-10" style={{ display: "flex", flexDirection: "column", justifyContent: "center" }}>
      <SpaceBackdrop />
      <div className="w-full" style={{ maxWidth: 720 }}>
        <div className="page-title">Hubungkan database perusahaan</div>
        <p className="page-sub">AIOS menempel pada sistem Anda apa adanya — sistem Anda tidak perlu diubah.</p>

        <div className="mt-6 grid gap-3 sm:grid-cols-2">
          <button type="button" className="card card-pad" style={{ textAlign: "left", cursor: "pointer", borderColor: path === "existing" ? "var(--primary)" : undefined }} onClick={() => setPath("existing")}>
            <div style={{ fontWeight: 800 }}>Database yang sudah ada</div>
            <div className="page-sub">Masukkan kredensial database perusahaan Anda (SQLite / PostgreSQL / MariaDB).</div>
          </button>
          <button type="button" className="card card-pad" style={{ textAlign: "left", cursor: "pointer", borderColor: path === "new" ? "var(--primary)" : undefined }} onClick={() => setPath("new")}>
            <div style={{ fontWeight: 800 }}>Buat database baru</div>
            <div className="page-sub">Belum punya database? Ekasa menyediakannya untuk Anda — tanpa form kredensial.</div>
          </button>
        </div>

        {view === "progress" ? (
          <div className="card card-pad mt-4" style={{ display: "grid", gap: 14 }}>
            {!done && !adaptError && (
              <>
                <div style={{ fontWeight: 800 }}>
                  ⏳ AIOS sedang menganalisis database Anda
                  {progress && progress.total > 0 ? ` — ${progress.done}/${progress.total} tabel` : "…"}
                </div>
                <p className="page-sub">
                  Setiap tabel dianalisis satu per satu oleh LLM lokal, jadi proses ini bisa memakan waktu cukup lama —
                  aman untuk menunggu. Kamu bisa kembali ke beranda; status analisis juga selalu tampil di bagian atas
                  layar.
                </p>
                {progress && progress.total > 0 && (
                  <div className="muted mono">
                    progres: {progress.done}/{progress.total} tabel ({Math.round((progress.done / progress.total) * 100)}%)
                  </div>
                )}
                <div className="muted mono">waktu berjalan: {Math.floor(elapsed / 60)}m {elapsed % 60}s</div>
                <div className="flex flex-wrap gap-3">
                  <button type="button" className="btn btn-outline" onClick={() => router.push(changeMode ? "/settings" : "/home")}>
                    ← Kembali ke beranda
                  </button>
                </div>
              </>
            )}
            {done && (
              <>
                <div style={{ fontWeight: 800, color: "var(--primary)" }}>✓ Analisis selesai!</div>
                <p className="page-sub">Pemetaan skema sudah siap. Tinjau hasilnya sebelum chat diaktifkan.</p>
                <div className="flex flex-wrap gap-3">
                  <button type="button" className="btn btn-primary" onClick={() => router.push("/onboarding/mapping")}>
                    Lihat hasil mapping →
                  </button>
                </div>
              </>
            )}
            {adaptError && (
              <>
                <div className="alert alert-err">Analisis gagal: {adaptError}</div>
                <div className="flex flex-wrap gap-3">
                  <button
                    type="button"
                    className="btn btn-outline"
                    onClick={() => {
                      setAdaptError(null);
                      setDone(false);
                      setView("form");
                    }}
                  >
                    Kembali ke form koneksi
                  </button>
                </div>
              </>
            )}
          </div>
        ) : path === "existing" ? (
          <div className="card card-pad mt-4" style={{ display: "grid", gap: 14 }}>
            <div className="flex gap-2">
              {(["sqlite", "postgres", "mariadb"] as const).map((e) => (
                <button
                  key={e}
                  type="button"
                  className={`pill ${engine === e ? "pill-info" : ""}`}
                  style={{ cursor: "pointer", textTransform: "capitalize" }}
                  onClick={() => {
                    setEngine(e);
                    setConn({ ...conn, port: e === "postgres" ? 5432 : 3306 });
                  }}
                >
                  {e}
                </button>
              ))}
            </div>

            {engine === "sqlite" ? (
              <label className="field">
                <span className="label">Path file database</span>
                <input className="input" placeholder="G:/…/retail_glm.sqlite" value={conn.path} onChange={(e) => setConn({ ...conn, path: e.target.value })} />
              </label>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="field">
                  <span className="label">Host</span>
                  <input className="input" value={conn.host} onChange={(e) => setConn({ ...conn, host: e.target.value })} />
                </label>
                <label className="field">
                  <span className="label">Port</span>
                  <input type="number" className="input" value={conn.port} onChange={(e) => setConn({ ...conn, port: Number(e.target.value) })} />
                </label>
                <label className="field">
                  <span className="label">User</span>
                  <input className="input" value={conn.user} onChange={(e) => setConn({ ...conn, user: e.target.value })} />
                </label>
                <label className="field">
                  <span className="label">Password</span>
                  <input type="password" className="input" value={conn.password} onChange={(e) => setConn({ ...conn, password: e.target.value })} />
                </label>
                <label className="field sm:col-span-2">
                  <span className="label">Nama database</span>
                  <input className="input" placeholder={engine === "postgres" ? "client_glm_legacy" : "client_glm_maria"} value={conn.database} onChange={(e) => setConn({ ...conn, database: e.target.value })} />
                </label>
              </div>
            )}

            <div className="flex flex-wrap gap-3 justify-between">
              <button type="button" className="btn btn-primary" disabled={busy} onClick={connectExisting}>
                {busy ? "Menghubungkan…" : "Hubungkan & analisis"}
              </button>
              {changeMode && (
                <button type="button" className="btn btn-outline" onClick={() => router.push("/settings")}>
                  Kembali
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className="card card-pad mt-4" style={{ display: "grid", gap: 14 }}>
            <div className="flex gap-2">
              <button type="button" className={`pill ${provMode === "template" ? "pill-info" : ""}`} style={{ cursor: "pointer" }} onClick={() => setProvMode("template")}>
                Template standar Ekasa
              </button>
              <button type="button" className={`pill ${provMode === "custom" ? "pill-info" : ""}`} style={{ cursor: "pointer" }} onClick={() => setProvMode("custom")}>
                Buat sendiri
              </button>
            </div>

            {provMode === "template" ? (
              <p className="page-sub">
                Database baru berisi skema + data contoh siap pakai (produk, pelanggan, karyawan, penjualan) — langsung bisa dipakai mencoba semua bidang AIOS.
              </p>
            ) : (
              <div style={{ display: "grid", gap: 10 }}>
                <p className="page-sub">Tentukan tabel &amp; kolom yang Anda butuhkan:</p>
                {tables.map((t, ti) => (
                  <div key={ti} className="card" style={{ padding: 12 }}>
                    <input
                      className="input mono"
                      placeholder="nama_tabel"
                      value={t.name}
                      onChange={(e) => {
                        const next = [...tables];
                        next[ti] = { ...t, name: e.target.value };
                        setTables(next);
                      }}
                    />
                    <div className="mt-2" style={{ display: "grid", gap: 6 }}>
                      {t.columns.map((c, ci) => (
                        <div key={ci} className="flex gap-2">
                          <input
                            className="input mono"
                            placeholder="nama_kolom"
                            value={c.name}
                            onChange={(e) => {
                              const next = [...tables];
                              next[ti].columns[ci] = { ...c, name: e.target.value };
                              setTables(next);
                            }}
                          />
                          <select
                            className="input"
                            style={{ width: 110 }}
                            value={c.type}
                            onChange={(e) => {
                              const next = [...tables];
                              next[ti].columns[ci] = { ...c, type: e.target.value as "text" | "number" | "date" };
                              setTables(next);
                            }}
                          >
                            <option value="text">text</option>
                            <option value="number">number</option>
                            <option value="date">date</option>
                          </select>
                        </div>
                      ))}
                      <button
                        type="button"
                        style={{ color: "var(--primary)", background: "none", border: "none", cursor: "pointer", font: "inherit", fontSize: 12.5, textAlign: "left", padding: 0 }}
                        onClick={() => {
                          const next = [...tables];
                          next[ti].columns.push({ name: "", type: "text" });
                          setTables(next);
                        }}
                      >
                        + kolom
                      </button>
                    </div>
                  </div>
                ))}
                <button
                  type="button"
                  style={{ color: "var(--primary)", background: "none", border: "none", cursor: "pointer", font: "inherit", fontSize: 12.5, textAlign: "left", padding: 0 }}
                  onClick={() => setTables([...tables, { name: "", columns: [{ name: "", type: "text" }] }])}
                >
                  + tabel
                </button>
              </div>
            )}

            <div className="flex flex-wrap gap-3 justify-between">
              <button type="button" className="btn btn-primary" disabled={busy} onClick={provisionNew}>
                {busy ? "Membuat database…" : "Buat database baru"}
              </button>
              {changeMode && (
                <button type="button" className="btn btn-outline" onClick={() => router.push("/settings")}>
                  Kembali
                </button>
              )}
            </div>
          </div>
        )}

        {error && <div className="alert alert-err mt-4">{error}</div>}
        {info && <div className="alert alert-ok mt-4">{info}</div>}
      </div>
    </main>
  );
}
