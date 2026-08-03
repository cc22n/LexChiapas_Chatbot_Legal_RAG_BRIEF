"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const [adminApiKey, setAdminApiKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await fetch("/api/admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ admin_api_key: adminApiKey }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        setError(data?.error ?? "No se pudo iniciar sesion");
        return;
      }
      router.push("/dashboard");
      router.refresh();
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-4">
      <h1 className="mb-1 text-lg font-semibold text-zinc-900 dark:text-zinc-50">Panel de metricas</h1>
      <p className="mb-6 text-sm text-zinc-500 dark:text-zinc-400">Acceso restringido -- LexChiapas</p>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <label htmlFor="admin_api_key" className="text-sm text-zinc-600 dark:text-zinc-300">
          Clave de administrador
        </label>
        <input
          id="admin_api_key"
          name="admin_api_key"
          type="password"
          value={adminApiKey}
          onChange={(event) => setAdminApiKey(event.target.value)}
          autoComplete="current-password"
          required
          className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 outline-none focus:border-blue-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50"
        />
        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        <button
          type="submit"
          disabled={loading || !adminApiKey}
          className="mt-2 rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Entrando..." : "Entrar"}
        </button>
      </form>
    </main>
  );
}
