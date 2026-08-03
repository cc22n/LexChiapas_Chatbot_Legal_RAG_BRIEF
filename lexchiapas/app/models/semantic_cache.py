from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.chunk import EMBEDDING_DIMENSION


class SemanticCacheEntry(Base):
    __tablename__ = "semantic_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSION), nullable=False)
    # ChatResponse completo serializado (answer, retrieved_chunks, llm_model,
    # grounded, prompt_tokens, completion_tokens, system_error) -- se
    # devuelve tal cual en un hit, sin volver a llamar retrieval ni LLM.
    response_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Firma del corpus (COUNT + MAX id de chunks activos, ver
    # app.rag.retriever.corpus_signature) al momento de generar esta
    # entrada -- un hit solo cuenta si la firma ACTUAL coincide exactamente
    # con la de cuando se guardo. Sin esto, un TTL ciego (30 dias) podria
    # devolver una respuesta CORRECTA-EN-SU-MOMENTO pero ya obsoleta si la
    # ley subyacente se re-ingirio (deactivate+insert, el patron ya
    # establecido en este proyecto) minutos despues de cachearla -- el
    # umbral de similitud (0.97) protege contra responder con la ley
    # EQUIVOCADA, pero no dice nada sobre si la ley correcta sigue vigente
    # tal cual se cacheo.
    corpus_chunk_count: Mapped[int] = mapped_column(Integer, nullable=False)
    corpus_max_chunk_id: Mapped[int] = mapped_column(Integer, nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
