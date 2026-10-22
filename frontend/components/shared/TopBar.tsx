"use client";

// Topbar AIOS — port markup dari frontend/components/TopBar.tsx, kini dengan
// sesi nyata (nama perusahaan, menu pengaturan, logout — FR-28).
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, apiMethod } from "@/lib/api";

export default function TopBar() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("…");
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api<{ name: string }>("/auth/me")
      .then((d) => setName(d.name))
      .catch(() => router.replace("/login"));
  }, [router]);

  useEffect(() => {
    apiMethod<{ csrf_token: string }>("/method/aios_v1.setup.get_session_context")
      .then((ctx) => {
        if (typeof window !== "undefined") (window as any).csrf_token = ctx.csrf_token;
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const logout = async () => {
    setOpen(false);
    if (typeof window !== "undefined") {
      sessionStorage.removeItem("aios:lead_auto_shown");
    }
    await api("/method/logout", { method: "POST" }).catch(() => {});
    router.replace("/login");
  };

  const initial = name.trim().charAt(0).toUpperCase() || "A";

  return (
    <header className="topbar">
      <div className="brand">
        <span className="dot" />
        AIOS
      </div>
      <div className="nav">
        <div className="user" ref={menuRef}>
          <button
            type="button"
            className={"user-btn" + (open ? " open" : "")}
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
          >
            <span className="avatar">{initial}</span>
            <span>{name}</span>
            <span className="caret">▾</span>
          </button>
          <div className={"user-menu" + (open ? "" : " hidden")}>
            <div className="um-head">
              <div className="um-name">{name}</div>
              <div className="um-role">Client · Workspace</div>
            </div>
            <Link href="/settings" className="um-item" onClick={() => setOpen(false)}>
              ⚙ Pengaturan
            </Link>
            <button type="button" className="um-item um-logout" onClick={logout}>
              ⏻ Keluar
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
