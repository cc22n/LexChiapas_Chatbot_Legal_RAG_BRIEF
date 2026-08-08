from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IngestionLog(Base):
    __tablename__ = "ingestion_logs"
    __table_args__ = (
        # Dominio real: solo running/success/failed se setean en codigo
        # (app.workers.ingestion_tasks) -- "pending" del comentario original
        # nunca se usa, no se incluye en el CHECK.
        CheckConstraint("status IN ('running', 'success', 'failed')", name="ck_ingestion_logs_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(30), nullable=False)  # running/success/failed
    chunks_created: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
