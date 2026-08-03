from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

EMBEDDING_DIMENSION = 1024  # debe coincidir con app/config.py -> ai_config.json embeddings.dimension


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    articulo_numero: Mapped[str | None] = mapped_column(String(50))
    titulo: Mapped[str | None] = mapped_column(String(200))
    capitulo: Mapped[str | None] = mapped_column(String(200))
    seccion: Mapped[str | None] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_metadata: Mapped[dict | None] = mapped_column(JSONB)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSION))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document = relationship("Document", back_populates="chunks")
