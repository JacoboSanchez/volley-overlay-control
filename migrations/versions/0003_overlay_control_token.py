"""overlay control token (shareable board link)

Revision ID: 0003_overlay_control_token
Revises: 0002_overlay_settings
Create Date: 2026-06-22 00:00:00.000000
"""
from __future__ import annotations

import secrets
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0003_overlay_control_token'
down_revision: str | None = '0002_overlay_settings'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table('user_overlays', schema=None) as batch_op:
        batch_op.add_column(sa.Column('control_token', sa.String(length=64), nullable=True))

    # Backfill an unguessable token for every existing overlay so each one is
    # immediately shareable. Tokens mirror the public-token shape (24-char
    # url-safe from 18 random bytes).
    rows = bind.execute(
        sa.text("SELECT id FROM user_overlays WHERE control_token IS NULL")
    ).fetchall()
    for (row_id,) in rows:
        bind.execute(
            sa.text("UPDATE user_overlays SET control_token = :t WHERE id = :i"),
            {"t": secrets.token_urlsafe(18), "i": row_id},
        )

    with op.batch_alter_table('user_overlays', schema=None) as batch_op:
        batch_op.create_index(
            'ix_user_overlays_control_token', ['control_token'], unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table('user_overlays', schema=None) as batch_op:
        batch_op.drop_index('ix_user_overlays_control_token')
        batch_op.drop_column('control_token')
