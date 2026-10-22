"use client";

// Halaman pengaturan lama (koneksi database) tidak relevan setelah #13.
// Pengaturan kuota/persona/status akan menjadi jendela desktop di #12.
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import TopBar from "@/components/shared/TopBar";

export default function SettingsPage() {
  const router = useRouter();

  useEffect(() => {
    api("/auth/me").catch(() => router.replace("/login"));
  }, [router]);

  return (
    <>
      <TopBar />
      <main className="page grid place-items-center px-4 py-10">
        <div className="card card-pad" style={{ maxWidth: 720 }}>
          <div className="page-title">Pengaturan</div>
          <p className="page-sub">
            Pengaturan kuota, persona, dan status akan tersedia sebagai jendela desktop AIOS.
          </p>
          <button type="button" className="btn btn-outline mt-5" onClick={() => router.push("/home")}>
            Kembali ke AIOS
          </button>
        </div>
      </main>
    </>
  );
}
