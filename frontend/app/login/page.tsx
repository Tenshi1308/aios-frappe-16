"use client";

// C1/C2: Login & registrasi portal client memakai auth resmi Frappe.
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, apiMethod, friendlyAuthError } from "@/lib/api";
import SpaceBackdrop from "@/components/shared/SpaceBackdrop";

type SessionContext = { roles: string[]; csrf_token: string };

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState({ fullName: "", name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && window.location.hostname.startsWith("developer.")) {
      router.replace("/developer/login");
    }
  }, [router]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "register") {
        await api("/method/aios_v1.auth.register_account", {
          method: "POST",
          body: JSON.stringify({
            full_name: form.fullName,
            email: form.email,
            password: form.password,
            company_name: form.name,
          }),
        });
        setPending(true);
        return;
      }

      await api("/method/login", {
        method: "POST",
        body: JSON.stringify({ usr: form.email, pwd: form.password }),
      });
      const ctx = await apiMethod<SessionContext>("/method/aios_v1.setup.get_session_context");
      if (typeof window !== "undefined") {
        (window as any).csrf_token = ctx.csrf_token;
        sessionStorage.removeItem("aios:lead_auto_shown");
      }
      const isAdmin = (ctx.roles || []).some((r) =>
        ["AIOS Admin", "System Manager", "Administrator"].includes(r)
      );
      router.push(isAdmin ? "/developer/dashboard" : "/home");
    } catch (err) {
      setError(friendlyAuthError(err));
    } finally {
      setBusy(false);
    }
  };

  if (pending) {
    return (
      <main className="page grid place-items-center px-4 py-10">
        <SpaceBackdrop />
        <div className="card card-pad w-full" style={{ maxWidth: 400 }}>
          <div className="page-title" style={{ textAlign: "center", marginTop: 4 }}>
            Pendaftaran Diterima
          </div>
          <p className="page-sub" style={{ textAlign: "center" }}>
            Instance site perusahaan Anda sedang disiapkan. Anda akan dihubungi setelah aktivasi.
          </p>
          <button
            type="button"
            className="btn btn-primary btn-block mt-6"
            onClick={() => {
              setPending(false);
              setMode("login");
            }}
          >
            Kembali ke Login
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="page grid place-items-center px-4 py-10">
      <SpaceBackdrop />
      <div className="card card-pad w-full" style={{ maxWidth: 400 }}>
        <div className="brand" style={{ justifyContent: "center", display: "flex", gap: 10, fontWeight: 800, fontSize: 20, color: "var(--primary)" }}>
          <span className="dot" style={{ width: 10, height: 10, borderRadius: "50%", background: "linear-gradient(135deg, var(--primary), var(--accent))", display: "inline-block", boxShadow: "0 0 8px rgba(34,211,238,0.8)" }} />
          AIOS
        </div>
        <div className="page-title" style={{ textAlign: "center", marginTop: 14 }}>
          {mode === "login" ? "Masuk ke workspace" : "Daftarkan perusahaan"}
        </div>
        <p className="page-sub" style={{ textAlign: "center" }}>
          Portal client — client.aios
        </p>

        <form onSubmit={submit} className="mt-6" style={{ display: "grid", gap: 14 }}>
          {mode === "register" && (
            <label className="field">
              <span className="label">Nama lengkap</span>
              <input
                className="input"
                placeholder="Budi Santoso"
                value={form.fullName}
                onChange={(e) => setForm({ ...form, fullName: e.target.value })}
                required
              />
            </label>
          )}
          {mode === "register" && (
            <label className="field">
              <span className="label">Nama perusahaan</span>
              <input
                className="input"
                placeholder="PT Bintang Timur"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
              />
            </label>
          )}
          <label className="field">
            <span className="label">Email</span>
            <input
              type="email"
              className="input"
              placeholder="perusahaan@contoh.id"
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
              placeholder="minimal 8 karakter"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              required
              minLength={8}
            />
          </label>

          {error && <div className="alert alert-err">{error}</div>}

          <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
            {busy ? "Memproses…" : mode === "login" ? "Masuk" : "Daftar"}
          </button>
        </form>

        <p className="mt-5" style={{ textAlign: "center", fontSize: 13.5, color: "var(--text-muted)" }}>
          {mode === "login" ? "Belum punya akun? " : "Sudah terdaftar? "}
          <button
            type="button"
            style={{ color: "var(--primary)", background: "none", border: "none", cursor: "pointer", font: "inherit" }}
            onClick={() => setMode(mode === "login" ? "register" : "login")}
          >
            {mode === "login" ? "Daftar sekarang" : "Masuk"}
          </button>
        </p>
      </div>
    </main>
  );
}
