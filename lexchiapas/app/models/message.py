from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user/assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_chunks: Mapped[dict | None] = mapped_column(JSONB)
    llm_model: Mapped[str | None] = mapped_column(String(100))
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    # prompt_tokens/completion_tokens: solo se llenan en mensajes assistant que
    # si llamaron al LLM (ver app/llm/router.py). found_answer es el mismo
    # valor que ChatResponse.grounded al momento de persistir, para poder medir
    # la tasa de "no encontre informacion" sin parsear retrieved_chunks.
    #
    # found_answer tiene 3 estados, no 2: True (encontro y respondio), False
    # (busco de verdad y no encontro nada -- resultado LEGITIMO del RAG), y
    # None (el pipeline trueno con una excepcion real ANTES de poder decidir
    # grounded/no-grounded -- error del sistema, no del contenido). Sin esta
    # distincion, un 500 real y un "no encontre informacion" eran
    # indistinguibles en la DB porque el primero ni se guardaba (ver
    # error_message abajo, mismo patron que ingestion_logs.status/
    # error_message, pedido explicitamente por WEB_FRONTEND_PLAN.md item #3
    # para el dashboard de metricas).
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    found_answer: Mapped[bool | None] = mapped_column(Boolean)
    # Proveedor/modelo que respondio el clasificador de grounding (ver
    # app.rag.grounding), NO el mismo campo que llm_model (que es el
    # modelo de la GENERACION principal) -- pueden ser distintos si el
    # fallback aterrizo en un proveedor diferente para cada llamada. None
    # si el clasificador nunca se llamo o si todos los proveedores
    # fallaron. Se persiste para diagnosticar desacuerdos reales entre
    # corridas sin tener que re-investigar desde cero (Fase 3.7).
    grounding_classifier_model: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    # True/False solo en mensajes assistant que pasaron por
    # app.rag.rag_pipeline.answer_question (que SI hace query rewriting,
    # ver app.rag.query_rewriting.rewrite_query) -- None en mensajes user,
    # y siempre None en mensajes producidos por el pipeline agentico
    # (app.rag.agent_pipeline), que deliberadamente NO hace query rewriting
    # (alcance de Fase 7, ver docstring de ese modulo). No confundir con
    # `found_answer`, que es sobre el RESULTADO del turno, no sobre si la
    # pregunta se reescribio antes de buscar.
    was_rewritten: Mapped[bool | None] = mapped_column(Boolean)
    # Solo en mensajes role='user' (es sobre el INPUT del usuario, no la
    # respuesta) -- ver app.rag.guardrails.detect_jailbreak_attempt, funcion
    # pura ya existente que antes solo se usaba para loggear con
    # logger.warning dentro de classify_intent, nunca se persistia. Default
    # False (no True) porque la deteccion es best-effort: un mensaje sin
    # coincidencia de patron NO es evidencia de que el usuario tuvo mala fe,
    # es simplemente "no se detecto ningun patron conocido".
    jailbreak_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    # Desglose de response_time_ms (que sigue existiendo intacto, envuelve
    # el pipeline COMPLETO) en las 2 fases que WEB_FRONTEND_PLAN.md Fase C.2
    # pedia distinguir: search_time_ms cubre desde despues de Capa 1 de
    # guardrails hasta tener top_chunks (query rewriting + sinonimos + HyDE +
    # hybrid_search + rerank); generation_time_ms cubre SOLO la llamada a
    # generate_answer. El segundo gate de grounding (answer_is_grounded_in_
    # practice, otra llamada LLM aparte) queda FUERA de ambos a proposito --
    # ni es busqueda ni es la generacion principal. Solo se llenan en
    # mensajes que pasaron por app.rag.rag_pipeline.answer_question (no en
    # el pipeline agentico, ver docstring de was_rewritten arriba para el
    # mismo razonamiento de alcance).
    search_time_ms: Mapped[int | None] = mapped_column(Integer)
    generation_time_ms: Mapped[int | None] = mapped_column(Integer)
    # Solo se puebla cuando ai_config.json "agentic_rag.enabled"=true (ver
    # app.rag.agent_pipeline.answer_question_agentic) -- viene directo de
    # ChatResponse.agent_trace.model_dump(). None en el pipeline lineal.
    agent_trace: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation = relationship("Conversation", back_populates="messages")
    feedback = relationship("Feedback", back_populates="message", cascade="all, delete-orphan")
