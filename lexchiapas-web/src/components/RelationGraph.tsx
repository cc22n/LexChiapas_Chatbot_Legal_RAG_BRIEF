import type { LegalRelation } from "@/lib/api";

interface RelationGraphProps {
  center: string;
  relations: LegalRelation[];
  emptyMessage?: string;
}

const WIDTH = 640;
const HEIGHT = 440;
const CX = WIDTH / 2;
const CY = HEIGHT / 2;
const RADIUS = 170;
const CENTER_R = 28;
const NODE_R = 8;

// relation_type es un enum chico y fijo (reforma/deroga/remite_a/deriva_de/
// modifica, ver app/models/legal_relation.py) -- mapeo deterministico a la
// paleta categorica del skill dataviz, mismo criterio que BarChartHorizontal
// con colorVar por dato.
const RELATION_COLORS: Record<string, string> = {
  reforma: "--series-1",
  deroga: "--series-4",
  remite_a: "--series-2",
  deriva_de: "--series-3",
  modifica: "--series-5",
};

function colorFor(relationType: string): string {
  return RELATION_COLORS[relationType] ?? "--series-6";
}

// Explorador "centro y satelites" de relaciones legales -- hand-rolled SVG,
// sin libreria de grafos (mismo criterio anti-sobre-ingenieria del backend:
// Postgres en vez de Neo4j, ver WEB_FRONTEND_PLAN.md Fase G). La ley
// elegida va en el centro; cada relacion real es un nodo satelite alrededor,
// conectado por una linea etiquetada con el tipo de relacion.
export function RelationGraph({ center, relations, emptyMessage = "Sin relaciones registradas" }: RelationGraphProps) {
  if (relations.length === 0) {
    return <p className="py-4 text-sm text-[var(--text-muted)]">{emptyMessage}</p>;
  }

  const n = relations.length;
  const nodes = relations.map((rel, i) => {
    const angle = (2 * Math.PI * i) / n - Math.PI / 2;
    return {
      rel,
      x: CX + RADIUS * Math.cos(angle),
      y: CY + RADIUS * Math.sin(angle),
      angle,
    };
  });

  return (
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full" role="img" aria-label={`Relaciones legales de ${center}`}>
      {nodes.map(({ rel, x, y }, i) => (
        <line
          key={`edge-${i}`}
          x1={CX}
          y1={CY}
          x2={x}
          y2={y}
          stroke={`var(${colorFor(rel.relation_type)})`}
          strokeWidth={1.5}
          opacity={0.6}
        />
      ))}

      {nodes.map(({ rel, x, y, angle }, i) => {
        const labelX = x + Math.cos(angle) * 14;
        const labelY = y + Math.sin(angle) * 14;
        const anchor = Math.cos(angle) > 0.2 ? "start" : Math.cos(angle) < -0.2 ? "end" : "middle";
        return (
          <g key={`node-${i}`}>
            <circle cx={x} cy={y} r={NODE_R} fill={`var(${colorFor(rel.relation_type)})`} stroke="var(--surface-1)" strokeWidth={2} />
            <text x={labelX} y={labelY} textAnchor={anchor} dominantBaseline="middle" fontSize={10} fill="var(--text-primary)">
              {rel.to_law_name.length > 40 ? `${rel.to_law_name.slice(0, 37)}...` : rel.to_law_name}
            </text>
            <text x={labelX} y={labelY + 12} textAnchor={anchor} dominantBaseline="middle" fontSize={9} fill="var(--text-muted)">
              {rel.relation_type}
              {rel.fecha ? ` -- ${rel.fecha}` : ""}
            </text>
          </g>
        );
      })}

      <circle cx={CX} cy={CY} r={CENTER_R} fill="var(--surface-1)" stroke="var(--border)" strokeWidth={2} />
      <text x={CX} y={CY} textAnchor="middle" dominantBaseline="middle" fontSize={10} fill="var(--text-primary)" fontWeight={600}>
        {center.length > 22 ? `${center.slice(0, 19)}...` : center}
      </text>
    </svg>
  );
}
