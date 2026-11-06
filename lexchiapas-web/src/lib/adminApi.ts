import "server-only";

import type { components } from "./api-schema";

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

// Tipos GENERADOS desde el esquema OpenAPI del backend (npm run types:generate).
// No se escriben a mano: si cambia un esquema en lexchiapas/app/schemas/
// admin_metrics.py, se regenera src/lib/api-schema.d.ts y `npm run types:check`
// (o tsc) delata cualquier desajuste.
type Schemas = components["schemas"];

export type UsageMetrics = Schemas["UsageMetrics"];
export type QualityMetrics = Schemas["QualityMetrics"];
export type PerformanceMetrics = Schemas["PerformanceMetrics"];
export type GuardrailsMetrics = Schemas["GuardrailsMetrics"];
export type AgentMetrics = Schemas["AgentMetrics"];
export type GoldenDatasetCase = Schemas["GoldenCase"];
export type GoldenDatasetRunSummary = Schemas["GoldenRunSummary"];
export type GoldenDatasetMetrics = Schemas["GoldenDatasetMetrics"];

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
