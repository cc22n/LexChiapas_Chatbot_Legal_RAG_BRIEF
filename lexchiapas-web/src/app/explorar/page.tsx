"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  getLaws,
  getLegalRelations,
  type Law,
  type LegalRelationsResponse,
} from "@/lib/api";
import { ChartCard } from "@/components/charts/ChartCard";
import { EmptyState } from "@/components/charts/EmptyState";
import { RelationGraph } from "@/components/RelationGraph";

// GET /api/laws y GET /api/legal-relations no existen todavia en el backend
// (ver WEB_FRONTEND_PLAN.md Fase G) -- esta pagina esta completa y lista,
// pero hoy siempre muestra el mensaje de "pendiente backend" porque getLaws()
// siempre falla con 404. Se activa sola cuando el backend implemente esos
// endpoints, sin tocar este archivo.
export default function ExplorarPage() {
  const [laws, setLaws] = useState<Law[] | null>(null);
  const [lawsError, setLawsError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string>("");
  const [relations, setRelations] = useState<LegalRelationsResponse | null>(null);
  const [relationsError, setRelationsError] = useState<string | null>(null);

  useEffect(() => {
    getLaws()
      .then(setLaws)
      .catch((err) => {
        setLawsError(
          err instanceof ApiError
            ? `El backend todavia no expone GET /api/laws (${err.status}).`
            : "No se pudo conectar con el backend."
        );
      });
  }, []);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    getLegalRelations(selected)
      .then((data) => {
        if (!cancelled) setRelations(data);
      })
      .catch((err) => {
        if (cancelled) return;
        setRelations(null);
        setRelationsError(err instanceof ApiError ? err.message : "No se pudo consultar el grafo legal.");
      });
    return () => {
      cancelled = true;
    };
  }, [selected]);

  function handleSelect(law: string) {
    setSelected(law);
    setRelations(null);
    setRelationsError(null);
  }

  return (
    <div className="viz-root min-h-screen bg-[var(--page-plane)]">
      <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-8">
        <header>
          <h1 className="text-lg font-semibold text-[var(--text-primary)]">Explorador de relaciones legales</h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Navega reformas, derogaciones y remisiones entre leyes del corpus (GraphRAG, Fase 8 backend).
          </p>
        </header>

        {lawsError ? (
          <EmptyState message={`Explorador pendiente -- ${lawsError} El grafo legal (2004 relaciones reales, ver PLAN.md Fase 8) ya existe en la base de datos, solo falta que el backend lo exponga publicamente.`} />
        ) : !laws ? (
          <p className="text-sm text-[var(--text-muted)]">Cargando leyes...</p>
        ) : (
          <>
            <select
              value={selected}
              onChange={(e) => handleSelect(e.target.value)}
              className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 outline-none focus:border-blue-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50"
            >
              <option value="">Elige una ley...</option>
              {laws.map((law) => (
                <option key={law.id} value={law.nombre}>
                  {law.nombre}
                </option>
              ))}
            </select>

            {relationsError && <EmptyState message={relationsError} />}

            {relations && (
              <ChartCard
                title={relations.law}
                subtitle="Relaciones registradas (reforma, deroga, remite_a, deriva_de, modifica)"
                tableColumns={[
                  { key: "relation_type", label: "Tipo" },
                  { key: "to_law_name", label: "Ley relacionada" },
                  { key: "articulo", label: "Articulo" },
                  { key: "fecha", label: "Fecha" },
                ]}
                tableRows={relations.relations.map((r) => ({
                  relation_type: r.relation_type,
                  to_law_name: r.to_law_name,
                  articulo: r.articulo ?? "--",
                  fecha: r.fecha ?? "--",
                }))}
              >
                <RelationGraph center={relations.law} relations={relations.relations} />
              </ChartCard>
            )}
          </>
        )}
      </div>
    </div>
  );
}
