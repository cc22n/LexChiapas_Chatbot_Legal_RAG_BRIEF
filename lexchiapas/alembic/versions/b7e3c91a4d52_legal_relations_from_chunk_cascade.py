"""legal_relations.from_chunk_id ON DELETE CASCADE (auditoria 2026-10-21, ALT-03)

Revision ID: b7e3c91a4d52
Revises: a1c4d7e92b10
Create Date: 2026-10-22 12:00:00.000000

replace_existing de la ingesta (app/workers/ingestion_tasks.py) borra los
chunks de una ley antes de reinsertarlos. Con la FK sin ON DELETE, las
relaciones legales que cuelgan de esos chunks hacian fallar el borrado con
ForeignKeyViolation, bloqueando la actualizacion de cualquier ley con
historial de reformas. Las relaciones son datos derivados (se reconstruyen
con ingestion/extract_legal_relations.py), asi que CASCADE es lo correcto.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b7e3c91a4d52'
down_revision: Union[str, Sequence[str], None] = 'a1c4d7e92b10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FK = "legal_relations_from_chunk_id_fkey"


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(_FK, "legal_relations", type_="foreignkey")
    op.create_foreign_key(_FK, "legal_relations", "chunks", ["from_chunk_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(_FK, "legal_relations", type_="foreignkey")
    op.create_foreign_key(_FK, "legal_relations", "chunks", ["from_chunk_id"], ["id"])
