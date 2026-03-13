"""add last_max_oid to discovered_layers

Revision ID: a3c1d8e92f01
Revises: 76b316435df2
Create Date: 2026-03-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a3c1d8e92f01'
down_revision: Union[str, Sequence[str], None] = '76b316435df2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'discovered_layers',
        sa.Column('last_max_oid', sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('discovered_layers', 'last_max_oid')
