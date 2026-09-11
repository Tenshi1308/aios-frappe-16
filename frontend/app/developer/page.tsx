"use client";

// Root portal developer: arahkan ke dashboard (bila login) atau login.
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import SpaceBackdrop from "@/components/shared/SpaceBackdrop";

export default function DeveloperRootPage() {
  const router = useRouter();

  useEffect(() => {
    api("/auth/me")
      .then(() => router.replace("/developer/dashboard"))
      .catch(() => router.replace("/developer/login"));
  }, [router]);

  return (
    <main className="page grid place-items-center">
      <SpaceBackdrop />
      <p className="page-sub">Memuat portal developer…</p>
    </main>
  );
}
