from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        # BUG REAL (auditoria de base de datos, 2026-08-06): get_or_create_
        # conversation (app.bots.conversation_store) hace SELECT y despues
        # INSERT sin select_for_update ni constraint de respaldo -- dos
        # requests concurrentes para el mismo chat_id (reintento de webhook
        # de Telegram, doble clic en el primer mensaje de una sesion web
        # nueva) podian ambas ver None en el SELECT e insertar dos
        # Conversation duplicadas, fragmentando el historial. Este
        # constraint es el respaldo a nivel BD; get_or_create_conversation
        # atrapa el IntegrityError y vuelve a leer.
        UniqueConstraint("platform", "chat_id", name="uq_conversations_platform_chat_id"),
        CheckConstraint("platform IN ('telegram', 'whatsapp', 'web')", name="ck_conversations_platform"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)  # telegram/whatsapp/web
    user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    chat_id: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
