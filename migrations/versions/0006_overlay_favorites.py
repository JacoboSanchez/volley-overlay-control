"""add per-user overlay favorites

Revision ID: 0006_overlay_favorites
Revises: 0005_perf_indexes
Create Date: 2026-08-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_overlay_favorites"
down_revision: str | None = "0005_perf_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("user_overlays", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_favorite",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("user_overlays", schema=None) as batch_op:
        batch_op.drop_column("is_favorite")
