"""rename user_overlays.display_name to description

The overlay's ``oid`` is its name; the optional free-text field is now a
*description* shown under that name, not an alternative name. Renames the
column in place so existing values are preserved.

Revision ID: 0008_overlay_display_name_to_description
Revises: 0007_team_groups_primary
Create Date: 2026-06-24 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0008_overlay_display_name_to_description'
down_revision: str | None = '0007_team_groups_primary'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('user_overlays', schema=None) as batch_op:
        batch_op.alter_column(
            'display_name',
            new_column_name='description',
            existing_type=sa.String(length=120),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table('user_overlays', schema=None) as batch_op:
        batch_op.alter_column(
            'description',
            new_column_name='display_name',
            existing_type=sa.String(length=120),
            existing_nullable=True,
        )
