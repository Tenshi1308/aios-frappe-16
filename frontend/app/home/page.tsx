"use client";

// Home — port tata letak frontend/app/page.tsap lama (TopBar + HomeHub),
// plus gerbang onboarding & popup perubahan skema (C14) versi implementasi.
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { WorkerInfo } from "@/lib/types";
import TopBar from "@/components/shared/TopBar";
import HomeHub from "@/components/home/HomeHub";

export default function HomePage() {
  const router = useRouter();
  const [workersByBranch, setWorkersByBranch] = useState<Record<string, WorkerInfo[]>>({});
  const [drift, setDrift] = useState<{ changed: boolean } | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        await api("/auth/me");
      } catch {
        router.replace("/login");
        return;
      }

      // gerbang onboarding: bayar → koneksi → validasi mapping (C3/C4/C6).
      // Selama analisis skema berjalan (C5 async), client tetap boleh masuk
      // home — chat baru aktif setelah mapping divalidasi.
      try {
        const st = await api<{ payment: string; connected: boolean; mappingStatus: string; adapting: boolean }>("/connection/status");
        if (st.payment !== "ACTIVE") {
          router.replace("/payment");
          return;
        }
        if (!st.connected || (st.mappingStatus === "NONE" && !st.adapting)) {
          router.replace("/onboarding");
          return;
        }
        if (st.mappingStatus === "NEEDS_REVIEW") {
          router.replace("/onboarding/mapping");
          return;
        }
      } catch {
        router.replace("/login");
        return;
      }

      try {
        const d = await api<{ branches: { key: string; workers: WorkerInfo[] }[] }>("/branches");
        const map: Record<string, WorkerInfo[]> = {};
        for (const b of d.branches) map[b.key] = b.workers.filter((w) => w.enabled);
        setWorkersByBranch(map);
      } catch {
        /* peta tetap jalan dengan data statis; dock tanpa saran spesifik */
      }

      // C14: cek perubahan skema → popup konfirmasi
      api<{ changed: boolean }>("/connection/check-drift", { method: "POST" })
        .then((d) => {
          if (d.changed) setDrift(d);
        })
        .catch(() => {});

      setReady(true);
    })();
  }, [router]);

  return (
    <>
      <TopBar />
      {ready ? (
        <HomeHub workersByBranch={workersByBranch} />
      ) : (
        <div className="grid flex-1 place-items-center" style={{ minHeight: "60vh" }}>
          <p className="muted">Menyiapkan jaringan AIOS…</p>
        </div>
      )}

      {drift?.changed && (
        <div
          className="fixed inset-0 z-50 grid place-items-center"
          style={{ background: "rgba(1, 4, 14, 0.72)" }}
          role="dialog"
          aria-modal="true"
        >
          <div className="card card-pad" style={{ width: "min(92vw, 440px)" }}>
            <div className="page-title">Struktur database berubah</div>
            <p className="page-sub" style={{ marginTop: 8 }}>
              AIOS mendeteksi perubahan skema pada database perusahaan Anda dan sedang mempelajari ulang strukturnya di
              background. Pantau statusnya di bagian atas layar — setelah selesai, mohon periksa pemetaan terbaru
              sebelum lanjut menggunakan AI.
            </p>
            <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
              <button
                type="button"
                className="btn btn-primary"
                style={{ flex: 1 }}
                onClick={() => router.push("/onboarding/mapping")}
              >
                Periksa &amp; Konfirmasi
              </button>
              <button type="button" className="btn btn-outline" onClick={() => setDrift(null)}>
                Nanti
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
