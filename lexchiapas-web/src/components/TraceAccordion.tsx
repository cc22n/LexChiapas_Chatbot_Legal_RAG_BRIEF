import type { AgentTrace } from "@/lib/types";

interface TraceAccordionProps {
  trace: AgentTrace | null | undefined;
}

const ROUTE_LABELS: Record<AgentTrace["route"], string> = {
  busqueda_general: "Busqueda semantica general",
  busqueda_por_ley: "Busqueda dentro de una ley especifica",
  articulo_especifico: "Lectura directa de un articulo",
  historial_ley: "Consulta del historial de reformas (grafo legal)",
  ninguna: "Sin busqueda (fuera de alcance)",
};

// agent_trace no existe todavia en la respuesta real del backend (ver
// WEB_FRONTEND_PLAN.md Fase F) -- este componente no renderiza nada hasta
// que el backend lo agregue, para no fingir una funcionalidad que hoy no
// esta disponible en produccion.
export function TraceAccordion({ trace }: TraceAccordionProps) {
  if (!trace) return null;

  return (
    <details className="mt-2 rounded border border-zinc-200 bg-zinc-50 px-2 py-1 text-xs dark:border-zinc-700 dark:bg-zinc-900">
      <summary className="cursor-pointer font-medium text-zinc-700 dark:text-zinc-300">
        Ver como llegue a esta respuesta
      </summary>
      <div className="mt-1 flex flex-col gap-0.5 text-zinc-600 dark:text-zinc-400">
        <p>{ROUTE_LABELS[trace.route]}</p>
        {trace.law_name && <p>Ley: {trace.law_name}</p>}
        {trace.articulo && <p>Articulo: {trace.articulo}</p>}
        {trace.self_reflection_triggered && (
          <p>Se reformulo la busqueda una vez antes de responder ({trace.intentos} intentos).</p>
        )}
      </div>
    </details>
  );
}
