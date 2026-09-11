"use client";

// C3: Pembayaran (mock payment gateway) → aktivasi otomatis (FR-29).
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import SpaceBackdrop from "@/components/shared/SpaceBackdrop";

export default function PaymentPage() {
  const router = useRouter();
  const [status, setStatus] = useState<"loading" | "PENDING" | "ACTIVE">("loading");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [isErr, setIsErr] = useState(false);

  useEffect(() => {
    api<{ companyStatus: string }>("/payment/status")
      .then((d) => setStatus(d.companyStatus === "ACTIVE" ? "ACTIVE" : "PENDING"))
      .catch(() => router.replace("/login"));
  }, [router]);

  const pay = async (simulate: "success" | "fail") => {
    setBusy(true);
    setMessage("");
    try {
      const res = await api<{ message: string }>("/payment/checkout", {
        method: "POST",
        body: JSON.stringify({ simulate }),
      });
      setIsErr(simulate === "fail");
      setMessage(res.message);
      if (simulate === "success") setTimeout(() => router.push("/onboarding"), 1100);
    } catch (err) {
      setIsErr(true);
      setMessage((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="page grid place-items-center px-4 py-10">
      <SpaceBackdrop />
      <div className="card card-pad w-full" style={{ maxWidth: 480 }}>
        <div className="page-title">Aktivasi langganan AIOS</div>
        <p className="page-sub">Selesaikan pembayaran untuk membuka seluruh kapabilitas AI (9 bidang, 36 spesialis).</p>

        <div className="mt-5 grid grid-cols-2 gap-3">
          <div className="stat">
            <div className="k">Paket</div>
            <div className="v">AIOS Business</div>
          </div>
          <div className="stat">
            <div className="k">Harga</div>
            <div className="v cyan">Rp 250.000</div>
          </div>
        </div>

        {status === "loading" ? (
          <p className="page-sub mt-5">Memeriksa status…</p>
        ) : status === "ACTIVE" ? (
          <div className="mt-5">
            <span className="pill pill-ok">Akun sudah aktif</span>
            <div className="mt-4">
              <button type="button" className="btn btn-primary" onClick={() => router.push("/home")}>
                Buka AIOS
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="alert alert-warn mt-5">
              Payment gateway disimulasikan pada prototype — pilih hasil pembayaran untuk demo.
            </div>
            <div className="mt-4 flex gap-3">
              <button type="button" className="btn btn-primary" style={{ flex: 1 }} disabled={busy} onClick={() => pay("success")}>
                Bayar (sukses)
              </button>
              <button type="button" className="btn btn-outline" style={{ flex: 1 }} disabled={busy} onClick={() => pay("fail")}>
                Simulasikan gagal
              </button>
            </div>
          </>
        )}

        {message && <div className={`alert mt-4 ${isErr ? "alert-err" : "alert-ok"}`}>{message}</div>}
      </div>
    </main>
  );
}
