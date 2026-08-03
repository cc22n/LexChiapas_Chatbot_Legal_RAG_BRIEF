"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function LogoutButton() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  async function handleLogout() {
    setLoading(true);
    try {
      await fetch("/api/admin/logout", { method: "POST" });
      router.push("/login");
      router.refresh();
    } finally {
      setLoading(false);
    }
  }

  return (
    <button
      type="button"
      onClick={handleLogout}
      disabled={loading}
      className="rounded-md border border-[var(--border)] px-3 py-1.5 text-xs text-[var(--text-secondary)] transition hover:text-[var(--text-primary)] disabled:opacity-50"
    >
      {loading ? "Saliendo..." : "Cerrar sesion"}
    </button>
  );
}
