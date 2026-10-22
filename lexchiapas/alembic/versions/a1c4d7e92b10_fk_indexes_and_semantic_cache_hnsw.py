"""indexes on FKs and semantic_cache HNSW (auditoria 2026-10-21)

Revision ID: a1c4d7e92b10
Revises: 325c4ee3c6cf
Create Date: 2026-10-21 12:00:00.000000

Ninguna de estas columnas tenia indice: cada lookup por conversacion,
feedback o relacion legal hacia table scan, y el cache semantico calculaba
distancia coseno fila por fila. if_not_exists para que sea seguro aplicarla
sobre una DB creada desde schema.sql ya actualizado.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a1c4d7e92b10'
down_revision: Union[str, Sequence[str], None] = '325c4ee3c6cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_BTREE_INDEXES = [
    ("ix_messages_conversation_id", "messages", ["conversation_id"]),
    ("ix_messages_created_at", "messages", ["created_at"]),
    ("ix_feedback_message_id", "feedback", ["message_id"]),
    ("ix_legal_relations_from_document_id", "legal_relations", ["from_document_id"]),
    ("ix_legal_relations_to_document_id", "legal_relations", ["to_document_id"]),
    ("ix_legal_relations_from_chunk_id", "legal_relations", ["from_chunk_id"]),
]


def upgrade() -> None:
    """Upgrade schema."""
    for name, table, columns in _BTREE_INDEXES:
        op.create_index(name, table, columns, unique=False, if_not_exists=True)
    op.create_index(
        "ix_semantic_cache_embedding_hnsw_cosine",
        "semantic_cache",
        ["question_embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"question_embedding": "vector_cosine_ops"},
        if_not_exists=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_semantic_cache_embedding_hnsw_cosine", table_name="semantic_cache", if_exists=True)
    for name, table, _ in reversed(_BTREE_INDEXES):
        op.drop_index(name, table_name=table, if_exists=True)
