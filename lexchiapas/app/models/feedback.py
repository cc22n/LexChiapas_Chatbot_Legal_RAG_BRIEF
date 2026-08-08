from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        # Mismo dominio que app.api.feedback.VALID_RATINGS -- respaldo a
        # nivel BD por si algun dia se inserta feedback fuera de esa capa
        # (script, migracion de datos, otro endpoint).
        CheckConstraint("rating IN ('util', 'no_util')", name="ck_feedback_rating"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    rating: Mapped[str] = mapped_column(String(20), nullable=False)  # util/no_util
    user_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    message = relationship("Message", back_populates="feedback")
