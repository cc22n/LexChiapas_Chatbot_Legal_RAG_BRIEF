export interface RetrievedChunk {
  chunk_id: number;
  document_nombre: string;
  articulo_numero: string | null;
  similarity: number;
  content: string;
}

// Espejo de un campo que todavia NO existe en el backend (pedido en
// WEB_FRONTEND_PLAN.md Fase F -- app.schemas.chat.ChatResponse.agent_trace).
// Hoy el pipeline agentico (Fase 7/8, PLAN.md) calcula esto en AgentState
// pero answer_question_agentic lo descarta -- este tipo documenta el shape
// propuesto para cuando el backend lo agregue.
export interface AgentTrace {
  route: "busqueda_general" | "busqueda_por_ley" | "articulo_especifico" | "historial_ley" | "ninguna";
  law_name: string | null;
  articulo: string | null;
  intentos: number;
  self_reflection_triggered: boolean;
}

// Espejo de app.schemas.chat.WebChatResponse (lexchiapas/app/schemas/chat.py)
export interface WebChatResponse {
  answer: string;
  retrieved_chunks: RetrievedChunk[];
  llm_model: string | null;
  grounded: boolean;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  message_id: number;
  out_of_scope: boolean;
  // No existe todavia en el backend -- ver AgentTrace arriba. Siempre
  // undefined hasta que WEB_FRONTEND_PLAN.md Fase F se implemente del lado
  // backend.
  agent_trace?: AgentTrace | null;
}

export type FeedbackRating = "util" | "no_util";

export interface ChatMessageData {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: RetrievedChunk[];
  messageId?: number;
  grounded?: boolean;
  outOfScope?: boolean;
  isError?: boolean;
  agentTrace?: AgentTrace | null;
}
