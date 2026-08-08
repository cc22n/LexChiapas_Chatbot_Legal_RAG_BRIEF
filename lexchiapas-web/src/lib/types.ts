export interface RetrievedChunk {
  chunk_id: number;
  document_nombre: string;
  articulo_numero: string | null;
  similarity: number;
  content: string;
}

// Espejo de app.schemas.chat.ChatResponse.agent_trace, que YA existe y se
// puebla en el backend (app/rag/agent_pipeline.py, persistido en
// app/bots/conversation_store.py) -- corregido, el comentario anterior decia
// que todavia no existia (auditoria de contenido visual, 2026-08-07). Solo
// viene poblado cuando el pipeline agentico corrio (ai_config.json
// agentic_rag.enabled); None/null en el pipeline lineal.
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
  agent_trace: AgentTrace | null;
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
