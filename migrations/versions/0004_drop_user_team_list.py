"""drop the legacy flat team roster

Groups replaced the flat roster as the unit of team selection: a group's
membership lives in ``team_group_members`` / ``user_group_teams``, and the
virtual "All" group is derived from ``teams.is_global`` /
``teams.owner_user_id``. The only writer left was custom-team creation, which
mirrored a row the team's own ``owner_user_id`` already implies — so the table
holds nothing the rest of the schema cannot answer, and dropping it loses no
team.

Revision ID: 0004_drop_user_team_list
Revises: 0003_drop_overlay_session_meta
Create Date: 2026-07-28 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0004_drop_user_team_list'
down_revision: str | None = '0003_drop_overlay_session_meta'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('user_team_list', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_team_list_user_id'))
        batch_op.drop_index(batch_op.f('ix_user_team_list_team_id'))
    op.drop_table('user_team_list')


def downgrade() -> None:
    op.create_table(
        'user_team_list',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False,
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['team_id'], ['teams.id'],
            name=op.f('fk_user_team_list_team_id_teams'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name=op.f('fk_user_team_list_user_id_users'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_user_team_list')),
        sa.UniqueConstraint(
            'user_id', 'team_id', name='uq_user_team_list_user_id_team_id',
        ),
    )
    with op.batch_alter_table('user_team_list', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_user_team_list_team_id'), ['team_id'], unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_user_team_list_user_id'), ['user_id'], unique=False,
        )
