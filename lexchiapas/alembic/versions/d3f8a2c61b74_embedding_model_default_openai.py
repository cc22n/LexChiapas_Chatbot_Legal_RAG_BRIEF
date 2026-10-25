"""server_default de embedding_model -> text-embedding-3-large (migracion de modelo 2026-10-23)

Revision ID: d3f8a2c61b74
Revises: b7e3c91a4d52
Create Date: 2026-10-23 12:00:00.000000

Los embeddings se migraron de nvidia/llama-nemotron-embed-vl-1b-v2 a OpenAI
text-embedding-3-large (ver ai_config.json "_note_migracion_2026_10_23" y
scripts/reembed_corpus.py). La ingesta siempre fija embedding_model
explicitamente, asi que el default solo es una red para inserts directos;
se alinea con app.models.chunk.CURRENT_EMBEDDING_MODEL. No toca filas.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd3f8a2c61b74'
down_revision: Union[str, Sequence[str], None] = 'b7e3c91a4d52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW = "text-embedding-3-large"
_OLD = "nvidia/llama-nemotron-embed-vl-1b-v2"


def upgrade() -> None:
    """Upgrade schema."""
    for table in ("chunks", "semantic_cache"):
        op.alter_column(table, "embedding_model", server_default=sa.text(f"'{_NEW}'"))


def downgrade() -> None:
    """Downgrade schema."""
    for table in ("chunks", "semantic_cache"):
        op.alter_column(table, "embedding_model", server_default=sa.text(f"'{_OLD}'"))
