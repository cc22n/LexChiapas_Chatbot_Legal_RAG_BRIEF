from pydantic import BaseModel, Field

# BUG REAL (auditoria de seguridad, 2026-08-04): WebChatRequest.message no
# tenia limite de longitud. El rate limit (10/min, ver app.api.rate_limit)
# frena volumen de requests, pero no tamano por request -- un solo mensaje
# gigante puede disparar hasta 5 llamadas LLM reales en la ruta agentica (ver
# app.rag.agent_pipeline), inflando costo/latencia de un solo request.
MAX_WEB_MESSAGE_LENGTH = 2000


class ChatRequest(BaseModel):
    platform: str  # telegram/whatsapp
    user_id: str
    chat_id: str
    text: str


class RetrievedChunk(BaseModel):
    chunk_id: int
    document_nombre: str
    articulo_numero: str | None = None
    similarity: float
    content: str
    # True solo si vino de dense_search y supero similarity_threshold real
    # (ver app.rag.retriever.RetrievedChunk.passed_threshold). Sin este
    # campo no se puede saber desde la DB si un chunk paso threshold real o
    # vino solo de BM25 (que normaliza a similarity=1.0 sin ser comparable).
    passed_threshold: bool = False
    # Vigencia real por articulo (ver app.rag.vigencia.is_articulo_derogado,
    # Fase 9.1 del roadmap) -- True si el CONTENIDO REAL del articulo es
    # "Se Deroga" (derogacion total, no una fraccion parcial). El frontend
    # debe mostrar esto como una advertencia visible, no enterrarlo en el
    # texto de la cita.
    derogado: bool = False


class AgentTrace(BaseModel):
    """Traza de decisiones del pipeline agentico (app.rag.agent_pipeline) --
    solo tiene sentido cuando la ruta fue agentica, ver comentario en
    ChatResponse.agent_trace abajo."""

    route: str
    law_name: str | None = None
    articulo: str | None = None
    intentos: int
    self_reflection_triggered: bool


class ChatResponse(BaseModel):
    answer: str
    retrieved_chunks: list[RetrievedChunk]
    llm_model: str | None = None
    grounded: bool
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    # Proveedor/modelo que respondio la llamada del clasificador de
    # grounding (ver app.rag.grounding.answer_is_grounded_in_practice) --
    # None si nunca se llego a llamar (grounded ya era False por threshold)
    # o si todos los proveedores del fallback fallaron. Se persiste para
    # poder diagnosticar despues si un desacuerdo real entre corridas vino
    # de un cambio de proveedor en el fallback, sin tener que re-investigar
    # desde cero (hallazgo real de esta sesion: minimax-m3 y
    # deepseek-v4-pro dieron veredictos distintos sobre el MISMO texto).
    grounding_classifier_model: str | None = None
    # True solo cuando el pipeline trueno con una excepcion real (ver
    # app/bots/conversation_store.py handle_turn) -- distinto de
    # grounded=False, que es un resultado legitimo ("no encontre
    # informacion"). grounded siempre viene False junto con esto para no
    # romper consumidores que todavia no revisan este campo.
    system_error: bool = False
    # True/False solo cuando app.rag.rag_pipeline.answer_question corrio
    # query rewriting (ver app.rag.query_rewriting.rewrite_query) -- None
    # cuando la ruta fue el pipeline agentico (app.rag.agent_pipeline), que
    # deliberadamente no hace query rewriting (alcance de Fase 7), o cuando
    # se respondio antes de llegar a esa etapa (fuera de dominio).
    was_rewritten: bool | None = None
    # Desglose de tiempo (ver app.models.message.Message.search_time_ms para
    # el detalle completo de que cubre cada uno) -- None en el pipeline
    # agentico y en un cache hit (ver app.rag.semantic_cache/rag_pipeline,
    # un hit no busca ni genera nada de verdad, esos numeros no aplican).
    search_time_ms: int | None = None
    generation_time_ms: int | None = None
    # Solo se puebla en la ruta agentica (app.rag.agent_pipeline.
    # answer_question_agentic) -- None en el pipeline lineal
    # (app.rag.rag_pipeline.answer_question), mismo criterio explicito que
    # was_rewritten/search_time_ms arriba documentan cuando quedan None.
    agent_trace: AgentTrace | None = None


class WebChatRequest(BaseModel):
    session_id: str
    message: str = Field(max_length=MAX_WEB_MESSAGE_LENGTH)
    # Switch de registro elegido por el usuario en la UI (ver
    # app.rag.generator._ESTILO_TECNICO/_ESTILO_COTIDIANO) -- default False
    # (cotidiano) preserva el comportamiento historico para quien no lo manda.
    technical: bool = False


class WebChatResponse(ChatResponse):
    message_id: int
    out_of_scope: bool = False


class FeedbackCreate(BaseModel):
    message_id: int
    session_id: str
    rating: str  # util/no_util
    user_comment: str | None = None


class FeedbackOut(BaseModel):
    id: int
    message_id: int
    rating: str
    user_comment: str | None = None

    class Config:
        from_attributes = True
