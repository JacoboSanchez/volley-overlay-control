"""drop the never-used overlay_session_meta table

Session-level flags are persisted per-OID as JSON files
(``app/api/session_persistence.py``); the table shipped with 0001 but no
code ever read or wrote it. Dropping it removes the dead schema instead
of finishing an unrequested migration.

Revision ID: 0003_drop_overlay_session_meta
Revises: 0002_icons
Create Date: 2026-07-06 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0003_drop_overlay_session_meta'
down_revision: str | None = '0002_icons'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table('overlay_session_meta')


def downgrade() -> None:
    op.create_table(
        'overlay_session_meta',
        sa.Column('overlay_id', sa.Integer(), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False,
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['overlay_id'], ['user_overlays.id'],
            name=op.f('fk_overlay_session_meta_overlay_id_user_overlays'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('overlay_id', name=op.f('pk_overlay_session_meta')),
    )
