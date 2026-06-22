"""overlay public_control flag (username+oid bookmark control)

Revision ID: 0004_overlay_public_control
Revises: 0003_overlay_control_token
Create Date: 2026-06-22 01:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0004_overlay_public_control'
down_revision: str | None = '0003_overlay_control_token'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('user_overlays', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'public_control', sa.Boolean(), nullable=False, server_default='0',
            )
        )


def downgrade() -> None:
    with op.batch_alter_table('user_overlays', schema=None) as batch_op:
        batch_op.drop_column('public_control')
