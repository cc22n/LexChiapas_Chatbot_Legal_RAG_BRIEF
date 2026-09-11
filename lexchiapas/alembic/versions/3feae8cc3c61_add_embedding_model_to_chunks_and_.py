"""add embedding_model to chunks and semantic_cache (Fase 9.8 C5)

Revision ID: 3feae8cc3c61
Revises: 80e54d617458
Create Date: 2026-09-10 09:06:44.460067

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3feae8cc3c61'
down_revision: Union[str, Sequence[str], None] = '80e54d617458'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Debe coincidir con ai_config.json embeddings.model y con
# app.models.chunk.CURRENT_EMBEDDING_MODEL al momento de escribir esta
# migracion (Fase 9.8, hallazgo C5).
CURRENT_MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2"


def upgrade() -> None:
    """Upgrade schema."""
    # chunks: todas las filas actuales son del modelo actual (el corpus se
    # re-embebio completo en la Fase 9.7), asi que el server_default las
    # cubre correctamente al agregar la columna NOT NULL.
    op.add_column(
        "chunks",
        sa.Column("embedding_model", sa.String(length=200), server_default=CURRENT_MODEL, nullable=False),
    )

    # semantic_cache: NO asumir que las entradas viejas son del modelo actual.
    # La firma de corpus (count/max_id) NO cambia al migrar de modelo con la
    # misma dimension, asi que una entrada pre-C5 podria haberse embebido con
    # otro modelo. Se marcan con un centinela que nunca coincide con un modelo
    # real -> lookup() (que exige embedding_model = modelo actual) las excluye
    # y expiran solas por TTL, en vez de arriesgar un hit sobre un espacio
    # vectorial incompatible.
    op.add_column("semantic_cache", sa.Column("embedding_model", sa.String(length=200), nullable=True))
    op.execute("UPDATE semantic_cache SET embedding_model = 'legacy-unknown' WHERE embedding_model IS NULL")
    op.alter_column("semantic_cache", "embedding_model", nullable=False, server_default=CURRENT_MODEL)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("semantic_cache", "embedding_model")
    op.drop_column("chunks", "embedding_model")
