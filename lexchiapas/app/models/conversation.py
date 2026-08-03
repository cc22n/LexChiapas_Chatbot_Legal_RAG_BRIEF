from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)  # telegram/whatsapp
    user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    chat_id: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
