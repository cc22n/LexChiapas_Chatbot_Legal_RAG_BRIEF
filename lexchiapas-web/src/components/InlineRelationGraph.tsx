"use client";

import { useEffect, useState } from "react";
import { getLegalRelations, type LegalRelationsResponse } from "@/lib/api";
import { ChartCard } from "./charts/ChartCard";
import { RelationGraph } from "./RelationGraph";

interface InlineRelationGraphProps {
  lawName: string;
}

// Fase 2 (contenido visual, PLAN.md): se muestra SOLO cuando el agente
// resolvio por la ruta historial_ley (GraphRAG real sobre legal_relations,
// ver app/rag/agent_pipeline.py) -- a diferencia de las tablas comparativas
// de la Fase 1 (generadas por el LLM), este grafo es 100% datos reales de
// GET /api/legal-relations, el LLM nunca lo toca -- grounded por
// construccion, sin ninguna de las salvaguardas que si necesita el texto
// generado (por eso no tiene bandera en ai_config.json: no hay nada que
// medir/apagar, no puede alucinar).
//
// .viz-root: RelationGraph/ChartCard usan variables CSS (--series-N,
// --surface-1, etc.) definidas solo dentro de esa clase (dashboard y
// /explorar) -- la pagina del chat no la tiene, envolver aca la declara
// para este subarbol nomas, sin arrastrar layout ni estilos del dashboard.
export function InlineRelationGraph({ lawName }: InlineRelationGraphProps) {
  const [data, setData] = useState<LegalRelationsResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    getLegalRelations(lawName)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch(() => {
        // Silencio a proposito: un adorno que falla (red, 404) no debe
        // ensuciar una respuesta de chat que ya es correcta -- el usuario
        // ya tiene su respuesta en texto, este grafo es un plus.
      });
    return () => {
      cancelled = true;
    };
  }, [lawName]);

  if (!data || data.relations.length === 0) {
    return null;
  }

  return (
    <div className="viz-root mt-3">
      <ChartCard
        title={data.law}
        subtitle="Relaciones registradas (reforma, deroga, adiciona)"
        tableColumns={[
          { key: "relation_type", label: "Tipo" },
          { key: "to_law_name", label: "Ley relacionada" },
          { key: "articulo", label: "Articulo" },
          { key: "fecha", label: "Fecha" },
        ]}
        tableRows={data.relations.map((r) => ({
          relation_type: r.relation_type,
          to_law_name: r.to_law_name,
          articulo: r.articulo ?? "--",
          fecha: r.fecha ?? "--",
        }))}
      >
        <RelationGraph center={data.law} relations={data.relations} />
      </ChartCard>
    </div>
  );
}
