"""drop overlay output_url (custom/cloud output removed)

Revision ID: 0005_drop_overlay_output_url
Revises: 0004_overlay_public_control
Create Date: 2026-06-22 02:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0005_drop_overlay_output_url'
down_revision: str | None = '0004_overlay_public_control'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('user_overlays', schema=None) as batch_op:
        batch_op.drop_column('output_url')


def downgrade() -> None:
    with op.batch_alter_table('user_overlays', schema=None) as batch_op:
        batch_op.add_column(sa.Column('output_url', sa.String(length=2048), nullable=True))
