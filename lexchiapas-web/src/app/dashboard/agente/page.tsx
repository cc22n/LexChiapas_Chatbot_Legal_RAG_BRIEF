import { requireAdminApiKey } from "@/lib/dal";
import { AdminApiError, getAgentMetrics, type AgentMetrics } from "@/lib/adminApi";
import { StatTile } from "@/components/charts/StatTile";
import { ChartCard } from "@/components/charts/ChartCard";
import { BarChartHorizontal } from "@/components/charts/BarChartHorizontal";
import { EmptyState } from "@/components/charts/EmptyState";

function pct(part: number, total: number): string {
  if (total === 0) return "--";
  return `${((part / total) * 100).toFixed(1)}%`;
}

// GET /admin/metrics/agent no existe todavia (WEB_FRONTEND_PLAN.md Fase F,
// pedido al backend) -- esta vista atrapa el 404 real en vez de crashear,
// y se activa sola cuando el backend lo implemente sin tocar este archivo
// (salvo remover este catch cuando ya no haga falta).
export default async function AgentePage() {
  const adminApiKey = await requireAdminApiKey();

  let metrics: AgentMetrics | null = null;
  try {
    metrics = await getAgentMetrics(adminApiKey);
  } catch (err) {
    if (!(err instanceof AdminApiError)) throw err;
  }

  if (!metrics) {
    return (
      <div className="flex flex-col gap-6">
        <EmptyState message="Metricas del agente pendientes -- GET /admin/metrics/agent todavia no existe en el backend. El agente (Fase 7/8, PLAN.md) esta completo y medido, pero no expone trace por query todavia. Ver WEB_FRONTEND_PLAN.md Fase F para el pedido exacto." />
      </div>
    );
  }

  const { triggered, total } = metrics.self_reflection_trigger_rate;

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatTile
          label="Intentos promedio por pregunta"
          value={metrics.avg_intentos != null ? Number(metrics.avg_intentos).toFixed(2) : "--"}
        />
        <StatTile
          label="Tasa de reintento (self-reflection)"
          value={pct(triggered, total)}
          delta={{ text: `${triggered} de ${total} preguntas`, direction: "down", good: true }}
        />
      </div>

      <ChartCard
        title="Rutas del agente"
        subtitle="Distribucion de decisiones (busqueda general / por ley / articulo / historial de reformas)"
        tableColumns={[
          { key: "route", label: "Ruta" },
          { key: "count", label: "Cantidad" },
        ]}
        tableRows={metrics.route_distribution.map((r) => ({ route: r.route, count: r.count }))}
      >
        <BarChartHorizontal
          data={metrics.route_distribution.map((r) => ({ label: r.route, value: r.count }))}
          colorVar="--series-3"
          emptyMessage="Todavia no hay preguntas procesadas por el agente"
        />
      </ChartCard>
    </div>
  );
}
