from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.rate_limit import enforce_rate_limit
from app.database import get_db
from app.models import Feedback, Message
from app.schemas.chat import FeedbackCreate, FeedbackOut

router = APIRouter(prefix="/api", tags=["feedback"])

VALID_RATINGS = {"util", "no_util"}


@router.post("/feedback", response_model=FeedbackOut)
def create_feedback(payload: FeedbackCreate, request: Request, db: Session = Depends(get_db)) -> Feedback:
    # BUG REAL (auditoria de seguridad, 2026-08-04): antes de este fix, no
    # habia rate limit ni verificacion de ownership -- cualquiera podia
    # mandar rating a CUALQUIER message_id existente con solo adivinar el
    # entero (IDOR leve, impacto bajo porque solo ensucia
    # feedback_ratio/feedback_ratio_telegram del dashboard admin, no expone
    # datos). Mismo patron IP que /api/chat/web y /api/laws.
    client_ip = request.client.host if request.client else "unknown"
    enforce_rate_limit(f"ip:{client_ip}")

    if payload.rating not in VALID_RATINGS:
        raise HTTPException(status_code=422, detail=f"rating debe ser uno de {VALID_RATINGS}")

    message = db.get(Message, payload.message_id)
    # 404 generico tanto si el mensaje no existe como si existe pero no es
    # de esta sesion -- no revelar via el status code cuales message_id son
    # validos para otras sesiones.
    if message is None or message.conversation.platform != "web" or message.conversation.chat_id != payload.session_id:
        raise HTTPException(status_code=404, detail="message not found")

    feedback = Feedback(
        message_id=payload.message_id,
        rating=payload.rating,
        user_comment=payload.user_comment,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback
