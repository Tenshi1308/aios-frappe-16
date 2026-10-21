"use client";

// C2: Login portal Ekasa Developer (developer.localhost) — bahasa desain AIOS.
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import SpaceBackdrop from "@/components/shared/SpaceBackdrop";

export default function DeveloperLoginPage() {
  const router = useRouter();
  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && window.location.hostname.startsWith("client.")) {
      router.replace("/login");
    }
  }, [router]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api("/method/login", {
        method: "POST",
        body: JSON.stringify({ usr: form.email, pwd: form.password }),
      });
      const ctx = await api<{ roles: string[]; csrf_token: string }>(
        "/method/aios_v1.setup.get_session_context"
      );
      if (typeof window !== "undefined") {
        (window as any).csrf_token = ctx.csrf_token;
      }
      const isAdmin = (ctx.roles || []).some((r) =>
        ["AIOS Admin", "System Manager", "Administrator"].includes(r)
      );
      if (!isAdmin) {
        await api("/method/logout", { method: "POST" }).catch(() => {});
        throw new Error("Akun ini bukan AIOS Admin.");
      }
      router.push("/developer/dashboard");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="page grid place-items-center px-4 py-10">
      <SpaceBackdrop />
      <div className="card card-pad w-full" style={{ maxWidth: 400 }}>
        <div className="brand" style={{ justifyContent: "center", display: "flex", gap: 10, fontWeight: 800, fontSize: 20, color: "var(--primary)" }}>
          <span className="dot" style={{ width: 10, height: 10, borderRadius: "50%", background: "linear-gradient(135deg, var(--primary), var(--accent))", display: "inline-block", boxShadow: "0 0 8px rgba(34,211,238,0.8)" }} />
          AIOS
        </div>
        <div className="page-title" style={{ textAlign: "center", marginTop: 14 }}>Ekasa Developer</div>
        <p className="page-sub" style={{ textAlign: "center" }}>Portal monitoring pemakaian — developer.aios</p>

        <form onSubmit={submit} className="mt-6" style={{ display: "grid", gap: 14 }}>
          <label className="field">
            <span className="label">Email</span>
            <input
              type="email"
              className="input"
              placeholder="developer@ekasa.id"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              required
            />
          </label>
          <label className="field">
            <span className="label">Password</span>
            <input
              type="password"
              className="input"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              required
            />
          </label>
          {error && <div className="alert alert-err">{error}</div>}
          <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
            {busy ? "Memverifikasi…" : "Masuk portal developer"}
          </button>
        </form>
      </div>
    </main>
  );
}
