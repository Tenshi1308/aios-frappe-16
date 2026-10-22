"use client";

// Home — port tata letak frontend/app/page.tsap lama (TopBar + HomeHub).
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { WorkerInfo } from "@/lib/types";
import TopBar from "@/components/shared/TopBar";
import HomeHub from "@/components/home/HomeHub";

export default function HomePage() {
  const router = useRouter();
  const [workersByBranch, setWorkersByBranch] = useState<Record<string, WorkerInfo[]>>({});
  const [ready, setReady] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        await api("/auth/me");
      } catch {
        router.replace("/login");
        return;
      }

      // Gate payment/onboarding legacy dilepas: workspace langsung terbuka.
      // Jalur PoC memakai ERPNext; adapter DB eksternal sudah dihapus di #13.

      try {
        const d = await api<{ branches: { key: string; workers: WorkerInfo[] }[] }>("/branches");
        const map: Record<string, WorkerInfo[]> = {};
        for (const b of d.branches) map[b.key] = b.workers.filter((w) => w.enabled);
        setWorkersByBranch(map);
      } catch {
        /* peta tetap jalan dengan data statis; dock tanpa saran spesifik */
      }

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
    </>
  );
}
