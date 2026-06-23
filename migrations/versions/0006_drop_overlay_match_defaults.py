"""drop overlay match-format defaults (sets / points / points_last_set)

These per-overlay defaults duplicated what the live control board already
configures via POST /session/rules, so the management UI and the columns were
removed. A fresh session now starts from the env defaults and the board owns
the rules.

Revision ID: 0006_drop_overlay_match_defaults
Revises: 0005_drop_overlay_output_url
Create Date: 2026-06-23 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0006_drop_overlay_match_defaults'
down_revision: str | None = '0005_drop_overlay_output_url'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('user_overlays', schema=None) as batch_op:
        batch_op.drop_column('sets')
        batch_op.drop_column('points_last_set')
        batch_op.drop_column('points')


def downgrade() -> None:
    with op.batch_alter_table('user_overlays', schema=None) as batch_op:
        batch_op.add_column(sa.Column('points', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('points_last_set', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('sets', sa.Integer(), nullable=True))
