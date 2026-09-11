import logging
import traceback
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_ai_config
from app.models import Conversation, Message
from app.rag.agent_pipeline import answer_question_agentic
from app.rag.guardrails import detect_jailbreak_attempt
from app.rag.memory import get_recent_history, invalidate_history_cache
from app.rag.rag_pipeline import answer_question
from app.schemas.chat import ChatResponse

logger = logging.getLogger(__name__)

SYSTEM_ERROR_MESSAGE = (
    "Tuve un problema tecnico procesando tu pregunta. Por favor intenta de "
    "nuevo en un momento."
)


def get_or_create_conversation(db: Session, platform: str, user_id: str, chat_id: str) -> Conversation:
    conversation = (
        db.query(Conversation)
        .filter_by(platform=platform, chat_id=chat_id)
        .one_or_none()
    )
    if conversation is None:
        conversation = Conversation(platform=platform, user_id=user_id, chat_id=chat_id)
        db.add(conversation)
        try:
            db.commit()
        except IntegrityError:
            # BUG REAL (auditoria de base de datos, 2026-08-06): read-then-
            # write sin lock -- dos requests concurrentes para el mismo
            # chat_id (reintento de webhook de Telegram, doble clic en el
            # primer mensaje web) pueden ambas ver None en el SELECT de
            # arriba y ambas intentar insertar. El UniqueConstraint
            # uq_conversations_platform_chat_id (app.models.conversation)
            # hace que la segunda falle aca en vez de crear un duplicado --
            # se descarta el insert perdedor y se relee la fila que SI gano
            # la carrera, que es la que debe usar este turno.
            db.rollback()
            conversation = (
                db.query(Conversation)
                .filter_by(platform=platform, chat_id=chat_id)
                .one()
            )
        else:
            db.refresh(conversation)
    return conversation


def handle_turn(
    db: Session, platform: str, user_id: str, chat_id: str, text: str, technical: bool = False
) -> tuple[ChatResponse, Message]:
    """Persiste el turno completo (mensaje de usuario + respuesta) para
    cualquier canal (Telegram, web, ...). Comun a todos los BaseBot y al
    endpoint de chat web para no duplicar esta logica en cada canal.

    technical: switch de registro tecnico/cotidiano (ver
    app.rag.generator._ESTILO_TECNICO), default False -- canales que no lo
    exponen (Telegram, hoy) se comportan exactamente igual que antes de
    este parametro existir.
    """
    conversation = get_or_create_conversation(db, platform, user_id, chat_id)

    # Fase 2.6: leer el historial ANTES de persistir la pregunta actual --
    # el historial son los turnos PREVIOS, no debe incluirse a si mismo.
    history = get_recent_history(db, conversation.id)

    # jailbreak_detected (sobre el INPUT del usuario, ver app.rag.guardrails.
    # detect_jailbreak_attempt): calculado y persistido aqui, antes del
    # try/except del pipeline, porque es sobre el texto que ya se tiene, no
    # sobre el resultado del RAG.
    jailbreak_detected = detect_jailbreak_attempt(text)
    db.add(
        Message(
            conversation_id=conversation.id,
            role="user",
            content=text,
            jailbreak_detected=jailbreak_detected,
        )
    )
    db.commit()

    try:
        # Fase 7 Etapa 1 (agentic RAG, ver app.rag.agent_pipeline): bandera
        # config-driven en ai_config.json "agentic_rag.enabled" (default
        # false) para elegir entre el pipeline lineal ya afinado y la ruta
        # agentica nueva sin tocar codigo. Ambas funciones comparten la misma
        # firma (db, question, conversation_history) -> (ChatResponse,
        # elapsed_ms). A5: la lectura de config va DENTRO del try -- un
        # ai_config.json malformado (AIConfigError) degrada con el mensaje de
        # error del sistema en vez de un 500 crudo, igual que cualquier otro
        # fallo del turno.
        if get_ai_config().get("agentic_rag", {}).get("enabled", False):
            pipeline_fn = answer_question_agentic
        else:
            pipeline_fn = answer_question

        response, elapsed_ms = pipeline_fn(db, text, conversation_history=history, technical=technical)
    except Exception as exc:
        # Antes de este fix, una excepcion aqui (NVIDIA caido, DB, bug de
        # codigo) tiraba un 500 sin dejar rastro -- la pregunta del usuario
        # quedaba persistida (arriba) pero SIN respuesta, indistinguible en
        # la DB de "no encontre informacion" (found_answer=False, un
        # resultado legitimo del RAG). Se distingue con found_answer=None
        # (ni True ni False -- el pipeline nunca llego a decidir) y
        # error_message con el traceback real, mismo patron que
        # ingestion_logs.status/error_message. Ver
        # WEB_FRONTEND_PLAN.md item #3 (bloqueado en backend hasta este fix).
        logger.exception("answer_question fallo para conversation_id=%s", conversation.id)
        db.rollback()

        response = ChatResponse(
            answer=SYSTEM_ERROR_MESSAGE,
            retrieved_chunks=[],
            llm_model=None,
            grounded=False,
            prompt_tokens=None,
            completion_tokens=None,
            system_error=True,
        )
        assistant_message = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=response.answer,
            found_answer=None,
            error_message="".join(traceback.format_exception(exc))[:4000],
        )
        db.add(assistant_message)
        conversation.last_message_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(assistant_message)
        # No se invalida/actualiza el cache de historial en el camino de
        # error -- este turno no tiene una respuesta real que valga la pena
        # recordar como contexto para el siguiente mensaje.
        return response, assistant_message

    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=response.answer,
        retrieved_chunks=[c.model_dump() for c in response.retrieved_chunks],
        llm_model=response.llm_model,
        response_time_ms=elapsed_ms,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
        aux_prompt_tokens=response.aux_prompt_tokens,
        aux_completion_tokens=response.aux_completion_tokens,
        found_answer=response.grounded,
        grounding_classifier_model=response.grounding_classifier_model,
        was_rewritten=response.was_rewritten,
        search_time_ms=response.search_time_ms,
        generation_time_ms=response.generation_time_ms,
        agent_trace=response.agent_trace.model_dump() if response.agent_trace else None,
    )
    db.add(assistant_message)
    conversation.last_message_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(assistant_message)

    # Invalidar el cache DESPUES de persistir el turno completo -- la
    # proxima lectura debe ver esta pregunta + respuesta como parte del
    # historial, no la version vieja sin ellas.
    invalidate_history_cache(conversation.id)

    return response, assistant_message
