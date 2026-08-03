from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Feedback, Message
from app.schemas.chat import FeedbackCreate, FeedbackOut

router = APIRouter(prefix="/api", tags=["feedback"])

VALID_RATINGS = {"util", "no_util"}


@router.post("/feedback", response_model=FeedbackOut)
def create_feedback(payload: FeedbackCreate, db: Session = Depends(get_db)) -> Feedback:
    if payload.rating not in VALID_RATINGS:
        raise HTTPException(status_code=422, detail=f"rating debe ser uno de {VALID_RATINGS}")

    message = db.get(Message, payload.message_id)
    if message is None:
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
