from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LegalRelation(Base):
    """Arista del grafo legal. Los nodos son las leyes ya existentes en
    `documents` -- esta tabla solo guarda las relaciones entre ellas
    (reforma/deroga/adiciona), extraidas de marcadores estructurados del
    Periodico Oficial dentro de los chunks ya ingeridos.
    """

    __tablename__ = "legal_relations"
    __table_args__ = (
        # Dominios reales confirmados en ingestion/extract_legal_relations.py
        # (unico productor de estos valores) y contra la DB real (auditoria
        # 2026-08-06): relation_type solo produce deroga/reforma/adiciona
        # (remite_a/deriva_de/modifica del docstring viejo nunca se generan);
        # extraction_method solo produce regex/regex_publicada/
        # regex_se_verbo (el "llm" del comentario viejo tampoco existe hoy).
        CheckConstraint(
            "relation_type IN ('deroga', 'reforma', 'adiciona')", name="ck_legal_relations_relation_type"
        ),
        CheckConstraint(
            "extraction_method IN ('regex', 'regex_publicada', 'regex_se_verbo')",
            name="ck_legal_relations_extraction_method",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    from_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"))
    from_chunk_id: Mapped[int | None] = mapped_column(ForeignKey("chunks.id"))
    from_articulo: Mapped[str | None] = mapped_column(String(50))
    relation_type: Mapped[str] = mapped_column(String(30), nullable=False)  # deroga/reforma/adiciona
    to_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"))
    to_law_name_raw: Mapped[str] = mapped_column(String(300), nullable=False)
    fecha: Mapped[date | None] = mapped_column(Date)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(20), nullable=False)  # regex/regex_publicada/regex_se_verbo
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
