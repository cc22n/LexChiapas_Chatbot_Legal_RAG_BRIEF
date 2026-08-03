import type { FeedbackRating, WebChatResponse } from "./types";

// "127.0.0.1", no "localhost": en esta maquina (Windows) Chrome resuelve
// "localhost" a ::1 (IPv6) primero, pero uvicorn en dev solo escucha en
// 127.0.0.1 (IPv4) salvo que se le pase --host explicito -- con "localhost"
// el fetch tira "TypeError: Failed to fetch" aunque el backend si responda
// por curl (curl si prefiere IPv4 por default).
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function errorDetail(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") return data.detail;
  } catch {
    // respuesta sin JSON valido, se usa el mensaje generico de abajo
  }
  return `Error ${res.status}`;
}

export async function sendChatMessage(sessionId: string, message: string): Promise<WebChatResponse> {
  const res = await fetch(`${API_BASE_URL}/api/chat/web`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }),
  });

  if (!res.ok) {
    throw new ApiError(await errorDetail(res), res.status);
  }

  return res.json();
}

export async function sendFeedback(messageId: number, rating: FeedbackRating): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message_id: messageId, rating }),
  });

  if (!res.ok) {
    throw new ApiError(await errorDetail(res), res.status);
  }
}

export interface Law {
  id: number;
  nombre: string;
}

export interface LegalRelation {
  relation_type: string;
  to_law_name: string;
  to_document_id: number | null;
  articulo: string | null;
  fecha: string | null;
  source_text: string;
}

export interface LegalRelationsResponse {
  law: string;
  relations: LegalRelation[];
}

// GET /api/laws y GET /api/legal-relations NO existen todavia en el backend
// -- ver WEB_FRONTEND_PLAN.md Fase G para el pedido exacto. Estas funciones
// quedan listas para cuando se implementen; hasta entonces siempre tiran
// ApiError (404) y /explorar lo atrapa mostrando un mensaje explicito.
export async function getLaws(): Promise<Law[]> {
  const res = await fetch(`${API_BASE_URL}/api/laws`);
  if (!res.ok) {
    throw new ApiError(await errorDetail(res), res.status);
  }
  return res.json();
}

export async function getLegalRelations(law: string): Promise<LegalRelationsResponse> {
  const res = await fetch(`${API_BASE_URL}/api/legal-relations?law=${encodeURIComponent(law)}`);
  if (!res.ok) {
    throw new ApiError(await errorDetail(res), res.status);
  }
  return res.json();
}
