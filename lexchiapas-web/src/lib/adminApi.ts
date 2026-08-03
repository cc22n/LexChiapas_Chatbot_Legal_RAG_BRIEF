import "server-only";

// Mismo backend que src/lib/api.ts -- 127.0.0.1, no "localhost" (ver ese
// archivo para el detalle del bug de IPv6 en esta maquina). Este helper
// corre solo en el servidor de Next.js (Server Components / Route
// Handlers), asi que la x-admin-api-key nunca llega al navegador.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export class AdminApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "AdminApiError";
    this.status = status;
  }
}

export async function verifyAdminApiKey(adminApiKey: string): Promise<boolean> {
  const res = await fetch(`${API_BASE_URL}/admin/metrics/usage`, {
    headers: { "x-admin-api-key": adminApiKey },
    cache: "no-store",
  });
  return res.ok;
}

async function fetchAdminJson<T>(path: string, adminApiKey: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "x-admin-api-key": adminApiKey },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new AdminApiError(`Error ${res.status} al consultar ${path}`, res.status);
  }
  return res.json();
}

export interface UsageMetrics {
  questions_per_day: { day: string; count: number }[];
  unique_users_by_platform: { platform: string; unique_users: number }[];
  top_laws: { ley: string | null; mentions: number }[];
  // Agregados por el backend 2026-07-24 (item 4/16 de LexChiapas_Dashboard_Metricas.md).
  top_questions: { content: string; count: number }[];
  conversations_by_platform: { platform: string; count: number }[];
}

export interface QualityMetrics {
  not_found_rate: { not_found: number; total: number };
  feedback_ratio: { rating: string; count: number }[];
  top_cited_articles: { ley: string | null; articulo: string | null; mentions: number }[];
  // Agregados por el backend 2026-07-24 (item 10/11) -- solo promedia/agrupa
  // chunks con passed_threshold=true (similitud coseno real, no BM25).
  // null si todavia no hay ningun mensaje grounded.
  avg_similarity_grounded: number | null;
  // Buckets fijos de 0.1 ("0.5-0.6".."0.9-1.0"); buckets sin datos vienen
  // AUSENTES del array (no en 0) -- el frontend debe tratarlos como 0.
  similarity_histogram: { range: string; count: number }[];
}

export interface PerformanceMetrics {
  // avg_ms/p95_ms: el backend los serializa a veces como string numerico
  // (AVG()/percentile_cont de Postgres via SQL crudo) -- Math.round() los
  // coacciona bien igual, no hace falta Number() explicito.
  latency: { avg_ms: number | null; p95_ms: number | null };
  // Desglose de latencia (item 3.2 de WEB_FRONTEND_PLAN.md Fase C.2) --
  // solo cubre mensajes que pasaron por el pipeline lineal real (no cache
  // hit, no pipeline agentico), por eso puede venir null aunque latency
  // arriba tenga dato.
  latency_breakdown: {
    avg_search_ms: number | null;
    p95_search_ms: number | null;
    avg_generation_ms: number | null;
    p95_generation_ms: number | null;
  };
  usage_by_model: { llm_model: string; count: number }[];
  tokens_per_day: { day: string; prompt_tokens: number | null; completion_tokens: number | null }[];
  recent_ingestion_errors: {
    id: number;
    document_id: number;
    status: string;
    error_message: string | null;
    started_at: string | null;
    completed_at: string | null;
  }[];
  // Listado navegable de errores individuales del chat (distinto del
  // conteo agregado de system_error_rate abajo) -- found_answer IS NULL
  // identifica un turno donde el pipeline exploto con una excepcion real.
  recent_chat_errors: {
    id: number;
    conversation_id: number;
    error_message: string | null;
    created_at: string;
  }[];
  // Agregado por el backend 2026-07-24 (item 3) -- found_answer IS NULL
  // (crash real del pipeline) vs total de mensajes assistant. Distinto de
  // not_found_rate en QualityMetrics, que es el "no encontre informacion"
  // legitimo.
  system_error_rate: { system_errors: number; total: number };
  // primary_vs_fallback (item 3.1 de WEB_FRONTEND_PLAN.md Fase C.2) --
  // primary_model viene de ai_config.json fallback_order[0] AHORA, no de
  // cuando se genero cada respuesta -- si el orden de fallback cambia, las
  // respuestas viejas se reclasifican solas la proxima vez que se pide este
  // endpoint.
  primary_vs_fallback: { primary_model: string; primary_count: number; fallback_count: number };
}

export interface GuardrailsMetrics {
  out_of_scope_per_day: { day: string; count: number }[];
  total_out_of_scope: number;
  jailbreak_attempts: number | null;
}

export interface AgentMetrics {
  route_distribution: { route: string; count: number }[];
  // El backend a veces lo serializa como string numerico (AVG() de
  // Postgres via SQL crudo, mismo patron que latency.avg_ms en
  // PerformanceMetrics) -- verificado con curl real: "1.00000000000000000000".
  // Usar Number(...) antes de .toFixed(), NO Math.round() (ese si coacciona
  // solo) ni asumir que ya es number pese al tipo declarado aqui.
  avg_intentos: number | null;
  self_reflection_trigger_rate: { triggered: number; total: number };
}

export interface GoldenDatasetCase {
  id: number;
  pregunta: string;
  passed: boolean;
  expects_grounded: boolean;
  actual_grounded: boolean;
  articulo_esperado: string | null;
  posicion_encontrada: number | null;
  respuesta_snippet: string | null;
}

export interface GoldenDatasetRunSummary {
  id: number;
  started_at: string;
  completed_at: string | null;
  total: number;
  passed: number;
  xfailed_known: number;
  failed: number;
  duration_ms: number | null;
}

export interface GoldenDatasetMetrics {
  // null si todavia no corrio ninguna evaluacion (tabla vacia) -- distinto
  // de un run con 0 passed, que si es un resultado real.
  latest: (GoldenDatasetRunSummary & { cases: GoldenDatasetCase[] }) | null;
  // Ultimas 10 corridas, mas reciente primero (igual que el resto del
  // backend), para graficar tendencia.
  history: GoldenDatasetRunSummary[];
}

export interface AdminDocument {
  id: number;
  nombre: string;
  tipo: string;
  fecha_publicacion: string | null;
  fecha_ultima_reforma: string | null;
  source_url: string | null;
  area_derecho: string | null;
  is_active: boolean;
  ingested_at: string | null;
}

export function getUsageMetrics(adminApiKey: string): Promise<UsageMetrics> {
  return fetchAdminJson("/admin/metrics/usage", adminApiKey);
}

export function getQualityMetrics(adminApiKey: string): Promise<QualityMetrics> {
  return fetchAdminJson("/admin/metrics/quality", adminApiKey);
}

export function getPerformanceMetrics(adminApiKey: string): Promise<PerformanceMetrics> {
  return fetchAdminJson("/admin/metrics/performance", adminApiKey);
}

export function getGuardrailsMetrics(adminApiKey: string): Promise<GuardrailsMetrics> {
  return fetchAdminJson("/admin/metrics/guardrails", adminApiKey);
}

export function getAgentMetrics(adminApiKey: string): Promise<AgentMetrics> {
  return fetchAdminJson("/admin/metrics/agent", adminApiKey);
}

export function getGoldenDatasetMetrics(adminApiKey: string): Promise<GoldenDatasetMetrics> {
  return fetchAdminJson("/admin/metrics/golden_dataset", adminApiKey);
}

// GET /admin/documents ya existia (app/api/admin.py) para el CRUD de
// documentos -- lo reusamos aqui solo para lectura, sin pedirle al backend
// un endpoint nuevo, para armar "cobertura de la base de conocimiento"
// (LexChiapas_Dashboard_Metricas.md item 15): area_derecho e is_active ya
// vienen en DocumentOut, asi que el conteo/agrupado se hace aqui.
export function getDocuments(adminApiKey: string): Promise<AdminDocument[]> {
  return fetchAdminJson("/admin/documents", adminApiKey);
}
