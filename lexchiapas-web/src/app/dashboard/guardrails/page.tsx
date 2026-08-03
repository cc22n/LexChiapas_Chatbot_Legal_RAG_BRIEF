import { requireAdminApiKey } from "@/lib/dal";
import { getGuardrailsMetrics } from "@/lib/adminApi";
import { StatTile } from "@/components/charts/StatTile";
import { ChartCard } from "@/components/charts/ChartCard";
import { LineChart } from "@/components/charts/LineChart";
import { EmptyState } from "@/components/charts/EmptyState";

export default async function GuardrailsPage() {
  const adminApiKey = await requireAdminApiKey();
  const metrics = await getGuardrailsMetrics(adminApiKey);

  const outOfScopeAsc = [...metrics.out_of_scope_per_day].reverse();

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatTile label="Preguntas fuera de alcance (Capa 1)" value={metrics.total_out_of_scope.toLocaleString("es-MX")} />
      </div>

      <ChartCard
        title="Fuera de alcance por dia"
        subtitle='Preguntas que Capa 1 (clasificador de intencion) rechazo antes de llegar al LLM'
        tableColumns={[
          { key: "day", label: "Dia" },
          { key: "count", label: "Cantidad" },
        ]}
        tableRows={outOfScopeAsc.map((d) => ({ day: d.day, count: d.count }))}
      >
        <LineChart
          data={outOfScopeAsc.map((d) => ({ x: d.day, values: { fuera_de_alcance: d.count } }))}
          series={[{ key: "fuera_de_alcance", label: "Fuera de alcance", colorVar: "--status-warning" }]}
        />
      </ChartCard>

      <ChartCard title="Intentos de jailbreak">
        {metrics.jailbreak_attempts == null ? (
          <EmptyState message="No se persisten todavia -- Capa 3 solo registra estos intentos en logs (logging.warning), no en una tabla consultable. Ver PLAN.md Fase 2.5." />
        ) : (
          <StatTile label="Intentos detectados" value={metrics.jailbreak_attempts.toLocaleString("es-MX")} />
        )}
      </ChartCard>
    </div>
  );
}
