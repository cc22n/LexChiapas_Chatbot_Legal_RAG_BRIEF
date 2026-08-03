import { requireAdminApiKey } from "@/lib/dal";
import { getPerformanceMetrics } from "@/lib/adminApi";
import { StatTile } from "@/components/charts/StatTile";
import { ChartCard } from "@/components/charts/ChartCard";
import { LineChart } from "@/components/charts/LineChart";
import { BarChartHorizontal } from "@/components/charts/BarChartHorizontal";
import { DataTable } from "@/components/charts/DataTable";

function formatMs(value: number | null): string {
  if (value == null) return "--";
  return `${Math.round(value).toLocaleString("es-MX")} ms`;
}

function pct(part: number, total: number): string {
  if (total === 0) return "--";
  return `${((part / total) * 100).toFixed(1)}%`;
}

export default async function PerformancePage() {
  const adminApiKey = await requireAdminApiKey();
  const metrics = await getPerformanceMetrics(adminApiKey);

  const tokensAsc = [...metrics.tokens_per_day].reverse();
  const { system_errors, total: totalRespuestas } = metrics.system_error_rate;
  const { primary_model, primary_count, fallback_count } = metrics.primary_vs_fallback;
  const totalModelUsage = primary_count + fallback_count;

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatTile label="Latencia promedio" value={formatMs(metrics.latency.avg_ms)} />
        <StatTile label="Latencia p95" value={formatMs(metrics.latency.p95_ms)} />
        <StatTile
          label="Tasa de errores del sistema"
          value={pct(system_errors, totalRespuestas)}
          delta={{ text: `${system_errors} de ${totalRespuestas} respuestas`, direction: "down", good: true }}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Busqueda promedio" value={formatMs(metrics.latency_breakdown.avg_search_ms)} />
        <StatTile label="Busqueda p95" value={formatMs(metrics.latency_breakdown.p95_search_ms)} />
        <StatTile label="Generacion promedio" value={formatMs(metrics.latency_breakdown.avg_generation_ms)} />
        <StatTile label="Generacion p95" value={formatMs(metrics.latency_breakdown.p95_generation_ms)} />
      </div>

      <ChartCard
        title="Modelo primario vs. fallback"
        subtitle={`Primario actual: ${primary_model} (ai_config.json)`}
        tableColumns={[
          { key: "tipo", label: "Tipo" },
          { key: "count", label: "Respuestas" },
        ]}
        tableRows={[
          { tipo: primary_model, count: primary_count },
          { tipo: "Fallback (otro modelo)", count: fallback_count },
        ]}
      >
        <BarChartHorizontal
          data={[
            { label: primary_model, value: primary_count },
            { label: "Fallback (otro modelo)", value: fallback_count },
          ]}
          colorVar="--series-2"
          emptyMessage="Todavia no hay respuestas generadas"
        />
        <p className="mt-2 text-xs text-[var(--text-muted)]">
          {pct(primary_count, totalModelUsage)} de las respuestas usaron el modelo primario
        </p>
      </ChartCard>

      <ChartCard
        title="Uso por modelo"
        subtitle="Respuestas generadas, por modelo LLM usado (fallback incluido)"
        tableColumns={[
          { key: "llm_model", label: "Modelo" },
          { key: "count", label: "Respuestas" },
        ]}
        tableRows={metrics.usage_by_model.map((m) => ({ llm_model: m.llm_model, count: m.count }))}
      >
        <BarChartHorizontal
          data={metrics.usage_by_model.map((m) => ({ label: m.llm_model, value: m.count }))}
          colorVar="--series-5"
          emptyMessage="Todavia no hay respuestas generadas"
        />
      </ChartCard>

      <ChartCard
        title="Tokens consumidos por dia"
        subtitle="Prompt vs. completion, ultimos 30 dias con actividad"
        tableColumns={[
          { key: "day", label: "Dia" },
          { key: "prompt_tokens", label: "Prompt" },
          { key: "completion_tokens", label: "Completion" },
        ]}
        tableRows={tokensAsc.map((d) => ({
          day: d.day,
          prompt_tokens: d.prompt_tokens ?? 0,
          completion_tokens: d.completion_tokens ?? 0,
        }))}
      >
        <LineChart
          data={tokensAsc.map((d) => ({
            x: d.day,
            values: { prompt: d.prompt_tokens ?? 0, completion: d.completion_tokens ?? 0 },
          }))}
          series={[
            { key: "prompt", label: "Prompt tokens", colorVar: "--series-1" },
            { key: "completion", label: "Completion tokens", colorVar: "--series-3" },
          ]}
        />
      </ChartCard>

      <ChartCard title="Errores de ingestion recientes" subtitle="Ultimos 20">
        <DataTable
          columns={[
            { key: "id", label: "ID" },
            { key: "document_id", label: "Documento" },
            { key: "status", label: "Estado" },
            { key: "error_message", label: "Error" },
            { key: "started_at", label: "Inicio" },
          ]}
          rows={metrics.recent_ingestion_errors.map((e) => ({
            id: e.id,
            document_id: e.document_id,
            status: e.status,
            error_message: e.error_message ?? "--",
            started_at: e.started_at ?? "--",
          }))}
          emptyMessage="Sin errores de ingestion recientes"
        />
      </ChartCard>

      <ChartCard title="Errores de chat recientes" subtitle="Ultimos 20 -- turnos donde el pipeline exploto con una excepcion real, distinto de 'no encontre informacion'">
        <DataTable
          columns={[
            { key: "id", label: "ID" },
            { key: "conversation_id", label: "Conversacion" },
            { key: "error_message", label: "Error" },
            { key: "created_at", label: "Fecha" },
          ]}
          rows={metrics.recent_chat_errors.map((e) => ({
            id: e.id,
            conversation_id: e.conversation_id,
            error_message: e.error_message ?? "--",
            created_at: e.created_at,
          }))}
          emptyMessage="Sin errores de chat recientes"
        />
      </ChartCard>
    </div>
  );
}
