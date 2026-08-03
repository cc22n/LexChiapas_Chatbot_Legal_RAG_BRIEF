import type { ReactNode } from "react";
import Link from "next/link";
import { requireAdminApiKey } from "@/lib/dal";
import { LogoutButton } from "@/components/dashboard/LogoutButton";

const NAV_ITEMS = [
  { href: "/dashboard/uso", label: "Uso" },
  { href: "/dashboard/calidad", label: "Calidad" },
  { href: "/dashboard/performance", label: "Performance" },
  { href: "/dashboard/guardrails", label: "Guardrails" },
  { href: "/dashboard/agente", label: "Agente" },
];

export default async function DashboardLayout({ children }: { children: ReactNode }) {
  // Redirige a /login si no hay sesion valida -- corre en cada navegacion
  // porque es un Server Component (no un Client Component con estado
  // cacheado), asi que no sufre el problema de "layouts no se re-renderizan
  // en transiciones client-side" que menciona la guia de auth de Next.js.
  await requireAdminApiKey();

  return (
    <div className="viz-root min-h-screen bg-[var(--page-plane)]">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-6">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border)] pb-4">
          <div>
            <h1 className="text-base font-semibold text-[var(--text-primary)]">LexChiapas -- Panel de metricas</h1>
            <nav className="mt-2 flex gap-4 text-sm">
              {NAV_ITEMS.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
          <LogoutButton />
        </header>
        {children}
      </div>
    </div>
  );
}
