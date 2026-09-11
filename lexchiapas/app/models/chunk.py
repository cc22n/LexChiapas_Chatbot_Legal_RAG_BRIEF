from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

EMBEDDING_DIMENSION = 1024  # debe coincidir con app/config.py -> ai_config.json embeddings.dimension
# Migrado 2026-08-27: nvidia/nv-embedqa-e5-v5 llego a su fin de vida real,
# se reemplazo por nvidia/llama-nemotron-embed-vl-1b-v2 -- ver
# ai_config.json "_note_migracion_2026_08_27". Dimension SIGUE en 1024 (el
# modelo nuevo emite 2048 nativo, truncado a 1024 via el parametro
# "dimensions" en embed_text, ver app.llm.providers) -- sin cambio de
# esquema, pero el corpus completo igual se re-embebio porque el espacio
# vectorial de un modelo distinto no es comparable aunque coincida la
# dimension.

# CURRENT_EMBEDDING_MODEL debe coincidir con ai_config.json embeddings.model.
# La fuente de verdad en runtime es ai_config.json (lo lee embed_text y la
# ingesta al poblar chunks.embedding_model); esta constante solo alimenta el
# server_default de la columna, como red para inserts directos (tests) que no
# lo especifican. pgvector solo protege contra cambio de DIMENSION, no de
# modelo con igual dimension -- registrar el modelo por fila permite detectar
# un corpus con embeddings de modelos mezclados (Fase 9.8 / hallazgo C5).
CURRENT_EMBEDDING_MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2"


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
    embedding_model: Mapped[str] = mapped_column(
        String(200), nullable=False, server_default=CURRENT_EMBEDDING_MODEL
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document = relationship("Document", back_populates="chunks")
