"use client";

// Root: arahkan ke halaman sesuai portal (client vs developer middleware).
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import SpaceBackdrop from "@/components/shared/SpaceBackdrop";

export default function RootPage() {
  const router = useRouter();

  useEffect(() => {
    const dev = window.location.hostname.startsWith("developer.");
    router.replace(dev ? "/developer/login" : "/login");
  }, [router]);

  return (
    <main className="page grid place-items-center">
      <SpaceBackdrop />
      <div style={{ textAlign: "center" }}>
        <div
          className="brand"
          style={{ justifyContent: "center", display: "flex", gap: 10, fontWeight: 800, fontSize: 20, color: "#67e8f9", textShadow: "0 0 12px rgba(34,211,238,0.35)" }}
        >
          <span className="dot" />
          AIOS
        </div>
        <p className="page-sub" style={{ marginTop: 8 }}>Memuat orbit AIOS…</p>
      </div>
    </main>
  );
}
