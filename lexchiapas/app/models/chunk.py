from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

EMBEDDING_DIMENSION = 1024  # debe coincidir con app/config.py -> ai_config.json embeddings.dimension


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        # BUG REAL (auditoria de base de datos, 2026-08-06): sin este
        # indice, dense_search (app.rag.retriever) hace sequential scan +
        # distancia coseno sobre TODA la tabla chunks (13000+ filas y
        # creciendo con cada ley nueva) en cada busqueda. vector_cosine_ops
        # porque retriever.py usa el operador <=> (distancia coseno) --
        # tiene que coincidir el opclass del indice con el operador real de
        # la query o Postgres no lo usa.
        Index(
            "ix_chunks_embedding_hnsw_cosine",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    articulo_numero: Mapped[str | None] = mapped_column(String(50))
    titulo: Mapped[str | None] = mapped_column(String(200))
    capitulo: Mapped[str | None] = mapped_column(String(200))
    seccion: Mapped[str | None] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_metadata: Mapped[dict | None] = mapped_column(JSONB)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSION))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document = relationship("Document", back_populates="chunks")
