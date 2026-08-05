from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.rate_limit import enforce_rate_limit
from app.bots.conversation_store import handle_turn
from app.database import get_db
from app.rag.guardrails import OUT_OF_SCOPE_MESSAGE
from app.schemas.chat import WebChatRequest, WebChatResponse

router = APIRouter(prefix="/api", tags=["chat-web"])

PLATFORM = "web"


@router.post("/chat/web", response_model=WebChatResponse)
def chat_web(payload: WebChatRequest, request: Request, db: Session = Depends(get_db)) -> WebChatResponse:
    if not payload.message.strip():
        raise HTTPException(status_code=422, detail="message no puede estar vacio")

    # Dos buckets independientes: session_id (client-supplied, spoofeable
    # mandando uno nuevo por request) y la IP real de la conexion TCP (no
    # spoofeable sin controlar la red) -- ver docstring de enforce_rate_limit.
    client_ip = request.client.host if request.client else "unknown"
    enforce_rate_limit(payload.session_id)
    enforce_rate_limit(f"ip:{client_ip}")

    response, assistant_message = handle_turn(
        db, PLATFORM, payload.session_id, payload.session_id, payload.message
    )
    # Distingue el rechazo de Capa 1 (guardrails, fuera de tema) del caso
    # "no encontre informacion" real -- ambos dan grounded=False y
    # llm_model=None, asi que el frontend no puede distinguirlos sin esta
    # comparacion explicita contra el mensaje fijo de app.rag.guardrails.
    out_of_scope = response.answer == OUT_OF_SCOPE_MESSAGE
    return WebChatResponse(
        **response.model_dump(), message_id=assistant_message.id, out_of_scope=out_of_scope
    )
