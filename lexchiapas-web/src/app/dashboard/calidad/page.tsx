import { requireAdminApiKey } from "@/lib/dal";
import { getQualityMetrics, getGoldenDatasetMetrics } from "@/lib/adminApi";
import { StatTile } from "@/components/charts/StatTile";
import { ChartCard } from "@/components/charts/ChartCard";
import { BarChartHorizontal } from "@/components/charts/BarChartHorizontal";
import { LineChart } from "@/components/charts/LineChart";
import { DataTable } from "@/components/charts/DataTable";
import { EmptyState } from "@/components/charts/EmptyState";
import { RAG_ADVANCED_SNAPSHOT } from "@/lib/ragAdvancedSnapshot";

function pct(part: number, total: number): string {
  if (total === 0) return "--";
  return `${((part / total) * 100).toFixed(1)}%`;
}

// Buckets fijos de 0.1 que el backend usa (ver adminApi.ts) -- el endpoint
// omite los que no tienen datos, asi que se completan con 0 aca en vez de
// tratarlos como "sin medir" (a diferencia de EmptyState/null, un bucket
// vacio es un cero real: cero chunks grounded cayeron en ese rango).
const SIMILARITY_BUCKETS = ["0.5-0.6", "0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-1.0"];

export default async function CalidadPage() {
  const adminApiKey = await requireAdminApiKey();
  const [metrics, goldenDataset] = await Promise.all([
    getQualityMetrics(adminApiKey),
    getGoldenDatasetMetrics(adminApiKey),
  ]);

  const { not_found, total } = metrics.not_found_rate;
  const util = metrics.feedback_ratio.find((f) => f.rating === "util")?.count ?? 0;
  const noUtil = metrics.feedback_ratio.find((f) => f.rating === "no_util")?.count ?? 0;
  const totalFeedback = util + noUtil;
  const histogramByRange = new Map(metrics.similarity_histogram.map((b) => [b.range, b.count]));
  const histogramFilled = SIMILARITY_BUCKETS.map((range) => ({
    label: range,
    value: histogramByRange.get(range) ?? 0,
  }));

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatTile
          label="Tasa de respuestas fundamentadas"
          value={pct(total - not_found, total)}
          delta={{ text: `${total - not_found} de ${total} respuestas`, direction: "up", good: true }}
        />
        <StatTile
          label='Tasa de "no encontre informacion"'
          value={pct(not_found, total)}
          delta={{ text: `${not_found} de ${total} respuestas`, direction: "down", good: false }}
        />
        <StatTile
          label="Feedback util"
          value={pct(util, totalFeedback)}
          delta={{ text: `${util} de ${totalFeedback} evaluaciones`, direction: "up", good: true }}
        />
        <StatTile
          label="Similitud promedio (respuestas fundamentadas)"
          value={metrics.avg_similarity_grounded != null ? metrics.avg_similarity_grounded.toFixed(3) : "--"}
        />
      </div>

      <ChartCard
        title="Distribucion de similitud"
        subtitle="Chunks con similitud coseno real (passed_threshold=true) que llegaron a una respuesta fundamentada"
        tableColumns={[
          { key: "range", label: "Rango" },
          { key: "count", label: "Chunks" },
        ]}
        tableRows={histogramFilled.map((b) => ({ range: b.label, count: b.value }))}
      >
        <BarChartHorizontal
          data={histogramFilled}
          colorVar="--series-6"
          emptyMessage="Todavia no hay chunks grounded para graficar"
        />
      </ChartCard>

      <ChartCard
        title="Feedback de usuarios"
        subtitle='Respuestas marcadas como utiles vs. no utiles'
        tableColumns={[
          { key: "rating", label: "Calificacion" },
          { key: "count", label: "Cantidad" },
        ]}
        tableRows={[
          { rating: "Util", count: util },
          { rating: "No util", count: noUtil },
        ]}
      >
        <BarChartHorizontal
          data={[
            { label: "Util", value: util, colorVar: "--status-good" },
            { label: "No util", value: noUtil, colorVar: "--status-critical" },
          ]}
          emptyMessage="Todavia no hay feedback registrado"
        />
      </ChartCard>

      <ChartCard
        title="Articulos mas citados"
        subtitle="Top 10 en respuestas con fundamento"
        tableColumns={[
          { key: "ley", label: "Ley" },
          { key: "articulo", label: "Articulo" },
          { key: "mentions", label: "Menciones" },
        ]}
        tableRows={metrics.top_cited_articles.map((a) => ({
          ley: a.ley ?? "Sin clasificar",
          articulo: a.articulo ?? "--",
          mentions: a.mentions,
        }))}
      >
        <BarChartHorizontal
          data={metrics.top_cited_articles.map((a) => ({
            label: `${a.ley ?? "Sin clasificar"} -- Art. ${a.articulo ?? "?"}`,
            value: a.mentions,
          }))}
          colorVar="--series-2"
          emptyMessage="Todavia no hay articulos citados"
        />
      </ChartCard>

      <ChartCard
        title="Tecnicas de RAG avanzado (ai_config.json)"
        subtitle="Instantanea manual de que tecnicas estan activas -- son flags de configuracion, no un resultado medido, ver PLAN.md Fase 6/7"
        tableColumns={[
          { key: "name", label: "Tecnica" },
          { key: "active", label: "Estado" },
          { key: "detail", label: "Detalle" },
        ]}
        tableRows={RAG_ADVANCED_SNAPSHOT.techniques.map((t) => ({
          name: t.name,
          active: t.active ? "Activa" : "Evaluada, no activa",
          detail: t.detail,
        }))}
      >
        <DataTable
          columns={[
            { key: "name", label: "Tecnica" },
            { key: "active", label: "Estado" },
          ]}
          rows={RAG_ADVANCED_SNAPSHOT.techniques.map((t) => ({
            name: t.name,
            active: t.active ? "Activa" : "Evaluada, no activa",
          }))}
        />
      </ChartCard>

      <ChartCard
        title="Golden dataset"
        subtitle="Corrida real mas reciente contra las 24 preguntas (app/evaluation/golden_dataset.py) -- dato en vivo, GET /admin/metrics/golden_dataset"
      >
        {goldenDataset.latest === null ? (
          <EmptyState message="Todavia no corrio ninguna evaluacion real. Disparar con POST /admin/evaluation/run (Celery, ~35min, llamadas reales de API)." />
        ) : (
          (() => {
            const latest = goldenDataset.latest;
            // El backend manda mas reciente primero; LineChart espera orden
            // cronologico ascendente para dibujar de izquierda a derecha.
            const historyAsc = [...goldenDataset.history].reverse();
            return (
              <div className="flex flex-col gap-4">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  <StatTile
                    label={`Ultima corrida (#${latest.id})`}
                    value={pct(latest.passed, latest.total)}
                    delta={{
                      text: `${latest.passed} passed, ${latest.xfailed_known} xfailed, ${latest.failed} failed de ${latest.total}`,
                      direction: "up",
                      good: true,
                    }}
                  />
                  <StatTile
                    label="Duracion"
                    value={latest.duration_ms != null ? `${(latest.duration_ms / 60000).toFixed(1)} min` : "--"}
                  />
                  <StatTile
                    label="Fecha"
                    value={new Date(latest.started_at).toLocaleDateString("es-MX", {
                      day: "2-digit",
                      month: "2-digit",
                      year: "numeric",
                    })}
                  />
                </div>

                <LineChart
                  data={historyAsc.map((r) => ({
                    x: r.started_at,
                    values: { passed: r.passed, xfailed: r.xfailed_known, failed: r.failed },
                  }))}
                  series={[
                    { key: "passed", label: "Passed", colorVar: "--status-good" },
                    { key: "xfailed", label: "Xfailed conocido", colorVar: "--series-3" },
                    { key: "failed", label: "Failed", colorVar: "--status-critical" },
                  ]}
                  emptyMessage="Solo hay una corrida todavia, sin tendencia que graficar"
                />

                <DataTable
                  columns={[
                    { key: "pregunta", label: "Pregunta" },
                    { key: "passed", label: "Resultado" },
                    { key: "articulo_esperado", label: "Articulo esperado" },
                    { key: "posicion_encontrada", label: "Posicion", align: "right" },
                  ]}
                  rows={latest.cases.map((c) => ({
                    pregunta: c.pregunta,
                    passed: c.passed ? "Passed" : "Failed",
                    articulo_esperado: c.articulo_esperado ?? "--",
                    posicion_encontrada: c.posicion_encontrada ?? "--",
                  }))}
                  emptyMessage="Sin detalle de casos para esta corrida"
                />
              </div>
            );
          })()
        )}
      </ChartCard>
    </div>
  );
}
