"use client";

// C7: Edit koneksi database dari menu kapan saja.
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import TopBar from "@/components/shared/TopBar";

interface Status {
  payment: string;
  connected: boolean;
  connection: {
    id: number;
    label: string;
    engine: string;
    config: Record<string, string>;
    provisioned: boolean;
    provisionMode?: string;
  } | null;
  mappingStatus: string;
}

export default function SettingsPage() {
  const router = useRouter();
  const [status, setStatus] = useState<Status | null>(null);

  useEffect(() => {
    (async () => {
      try {
        await api("/auth/me");
        const s = await api<Status>("/connection/status");
        setStatus(s);
      } catch {
        router.replace("/login");
      }
    })();
  }, [router]);

  return (
    <>
      <TopBar />
      <main className="page grid place-items-center px-4 py-10">
        <div className="w-full" style={{ maxWidth: 720 }}>
        <div className="page-title">Koneksi database</div>
        <p className="page-sub">Ubah koneksi kapan saja — AIOS akan mempelajari ulang struktur database yang baru (adaptasi ulang otomatis).</p>

        {status ? (
          <div className="card card-pad mt-6">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`pill ${status.payment === "ACTIVE" ? "pill-ok" : "pill-warn"}`}>
                {status.payment === "ACTIVE" ? "Langganan aktif" : "Menunggu pembayaran"}
              </span>
              <span className={`pill ${status.connected ? "pill-ok" : "pill-bad"}`}>
                {status.connected ? "Database terhubung" : "Belum terhubung"}
              </span>
              <span className={`pill ${status.mappingStatus === "VALIDATED" ? "pill-ok" : status.mappingStatus === "NEEDS_REVIEW" ? "pill-warn" : ""}`}>
                Pemetaan:{" "}
                {status.mappingStatus === "VALIDATED" ? "tervalidasi" : status.mappingStatus === "NEEDS_REVIEW" ? "perlu peninjauan" : "belum ada"}
              </span>
            </div>

            {status.connection ? (
              <table className="tbl mt-4">
                <tbody>
                  <tr>
                    <th style={{ width: 150 }}>Label</th>
                    <td>{status.connection.label}</td>
                  </tr>
                  <tr>
                    <th>Engine</th>
                    <td className="mono">{status.connection.engine}</td>
                  </tr>
                  <tr>
                    <th>Lokasi / database</th>
                    <td className="mono">
                      {status.connection.engine === "sqlite"
                        ? status.connection.config.path
                        : `${status.connection.config.host}:${status.connection.config.port}/${status.connection.config.database}`}
                    </td>
                  </tr>
                  <tr>
                    <th>Sumber</th>
                    <td>
                      {status.connection.provisioned
                        ? `Dibuat AIOS (mode ${status.connection.provisionMode}) — database ini milik Anda (Client Database)`
                        : "Kredensial milik perusahaan Anda"}
                    </td>
                  </tr>
                </tbody>
              </table>
            ) : (
              <p className="page-sub mt-4">Belum ada koneksi database.</p>
            )}

            <div className="mt-5 flex flex-wrap gap-3 justify-between">
              <button type="button" className="btn btn-primary" onClick={() => router.push("/onboarding?change=1")}>
                {status.connected ? "Ganti / edit koneksi" : "Hubungkan database"}
              </button>
              {status.mappingStatus !== "NONE" && (
                <button type="button" className="btn btn-outline" onClick={() => router.push("/onboarding/mapping")}>
                  Lihat &amp; validasi pemetaan
                </button>
              )}
              <button type="button" className="btn btn-outline" onClick={() => router.push("/home")}>
                Kembali ke AIOS
              </button>
            </div>
          </div>
        ) : (
          <p className="page-sub mt-6">Memuat…</p>
        )}
      </div>
    </main>
    </>
  );
}
