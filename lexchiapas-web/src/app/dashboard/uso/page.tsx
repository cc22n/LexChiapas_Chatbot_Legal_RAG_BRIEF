import { requireAdminApiKey } from "@/lib/dal";
import { getUsageMetrics, getDocuments } from "@/lib/adminApi";
import { StatTile } from "@/components/charts/StatTile";
import { ChartCard } from "@/components/charts/ChartCard";
import { LineChart } from "@/components/charts/LineChart";
import { BarChartHorizontal } from "@/components/charts/BarChartHorizontal";
import { DataTable } from "@/components/charts/DataTable";

export default async function UsoPage() {
  const adminApiKey = await requireAdminApiKey();
  const [metrics, documents] = await Promise.all([getUsageMetrics(adminApiKey), getDocuments(adminApiKey)]);

  const totalPreguntas = metrics.questions_per_day.reduce((sum, d) => sum + d.count, 0);
  const activeDocuments = documents.filter((d) => d.is_active);
  const areasCubiertas = new Set(activeDocuments.map((d) => d.area_derecho ?? "sin clasificar"));
  const documentsByArea = Array.from(
    activeDocuments.reduce((acc, d) => {
      const area = d.area_derecho ?? "sin clasificar";
      acc.set(area, (acc.get(area) ?? 0) + 1);
      return acc;
    }, new Map<string, number>())
  )
    .map(([area, count]) => ({ label: area, value: count }))
    .sort((a, b) => b.value - a.value);
  // El backend manda mas reciente primero (ORDER BY day DESC); la
  // LineChart espera orden cronologico ascendente para dibujar de
  // izquierda a derecha.
  const questionsAsc = [...metrics.questions_per_day].reverse();

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatTile label="Preguntas (ultimos 30 dias)" value={totalPreguntas.toLocaleString("es-MX")} />
        {metrics.unique_users_by_platform.map((p) => (
          <StatTile
            key={p.platform}
            label={`Usuarios unicos -- ${p.platform}`}
            value={p.unique_users.toLocaleString("es-MX")}
          />
        ))}
      </div>

      <ChartCard
        title="Preguntas por dia"
        subtitle="Ultimos 30 dias con actividad"
        tableColumns={[
          { key: "day", label: "Dia" },
          { key: "count", label: "Preguntas" },
        ]}
        tableRows={questionsAsc.map((d) => ({ day: d.day, count: d.count }))}
      >
        <LineChart
          data={questionsAsc.map((d) => ({ x: d.day, values: { preguntas: d.count } }))}
          series={[{ key: "preguntas", label: "Preguntas", colorVar: "--series-1" }]}
        />
      </ChartCard>

      <ChartCard
        title="Leyes mas consultadas"
        subtitle="Top 10 por menciones en respuestas fundamentadas"
        tableColumns={[
          { key: "ley", label: "Ley" },
          { key: "mentions", label: "Menciones" },
        ]}
        tableRows={metrics.top_laws.map((l) => ({ ley: l.ley ?? "Sin clasificar", mentions: l.mentions }))}
      >
        <BarChartHorizontal
          data={metrics.top_laws.map((l) => ({ label: l.ley ?? "Sin clasificar", value: l.mentions }))}
          emptyMessage="Todavia no hay leyes citadas"
        />
      </ChartCard>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <ChartCard title="Usuarios unicos por plataforma">
          <DataTable
            columns={[
              { key: "platform", label: "Plataforma" },
              { key: "unique_users", label: "Usuarios unicos", align: "right" },
            ]}
            rows={metrics.unique_users_by_platform.map((p) => ({
              platform: p.platform,
              unique_users: p.unique_users,
            }))}
          />
        </ChartCard>

        <ChartCard title="Conversaciones por plataforma" subtitle="Numero exacto de conversaciones, no de usuarios unicos">
          <DataTable
            columns={[
              { key: "platform", label: "Plataforma" },
              { key: "count", label: "Conversaciones", align: "right" },
            ]}
            rows={metrics.conversations_by_platform.map((p) => ({
              platform: p.platform,
              count: p.count,
            }))}
          />
        </ChartCard>
      </div>

      <ChartCard title="Preguntas mas frecuentes" subtitle="Top 10 por texto exacto (sin normalizar mayusculas/acentos)">
        <DataTable
          columns={[
            { key: "content", label: "Pregunta" },
            { key: "count", label: "Veces", align: "right" },
          ]}
          rows={metrics.top_questions.map((q) => ({ content: q.content, count: q.count }))}
          emptyMessage="Todavia no hay preguntas registradas"
        />
      </ChartCard>

      <div>
        <h2 className="mb-3 text-sm font-semibold text-[var(--text-primary)]">Cobertura de la base de conocimiento</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <StatTile label="Leyes activas indexadas" value={activeDocuments.length.toLocaleString("es-MX")} />
          <StatTile label="Areas del derecho cubiertas" value={areasCubiertas.size.toLocaleString("es-MX")} />
          <StatTile
            label="Leyes inactivas/dadas de baja"
            value={(documents.length - activeDocuments.length).toLocaleString("es-MX")}
          />
        </div>
        <div className="mt-4">
          <ChartCard
            title="Leyes activas por area del derecho"
            tableColumns={[
              { key: "area", label: "Area" },
              { key: "count", label: "Leyes" },
            ]}
            tableRows={documentsByArea.map((d) => ({ area: d.label, count: d.value }))}
          >
            <BarChartHorizontal data={documentsByArea} colorVar="--series-4" emptyMessage="Todavia no hay leyes indexadas" />
          </ChartCard>
        </div>
      </div>
    </div>
  );
}
