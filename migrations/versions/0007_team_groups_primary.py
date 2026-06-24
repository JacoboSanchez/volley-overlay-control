"""team groups as the primary unit of team selection

Adds ``team_groups.owner_user_id`` (null = shared/admin group, set = private
group owned by that user) and a ``user_group_teams`` table for per-user group
membership (a user's additions to a shared group, and every member of a user's
private group).

Data step: each user's legacy flat roster (``user_team_list``) is copied into a
new private "My teams" group so nothing is lost; ``user_team_list`` itself is
kept as a rollback safety net (a later revision drops it once proven).

Revision ID: 0007_team_groups_primary
Revises: 0006_drop_overlay_match_defaults
Create Date: 2026-06-24 12:00:00.000000
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0007_team_groups_primary'
down_revision: str | None = '0006_drop_overlay_match_defaults'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MY_TEAMS_NAME = "My teams"


def upgrade() -> None:
    # 1) team_groups.owner_user_id (nullable; null = shared/admin group).
    with op.batch_alter_table('team_groups', schema=None) as batch_op:
        batch_op.add_column(sa.Column('owner_user_id', sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_team_groups_owner_user_id'), ['owner_user_id'], unique=False,
        )
        batch_op.create_foreign_key(
            batch_op.f('fk_team_groups_owner_user_id_users'),
            'users', ['owner_user_id'], ['id'], ondelete='CASCADE',
        )

    # 2) user_group_teams — per-user membership inside a group.
    op.create_table(
        'user_group_teams',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
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
            ['group_id'], ['team_groups.id'],
            name=op.f('fk_user_group_teams_group_id_team_groups'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['team_id'], ['teams.id'],
            name=op.f('fk_user_group_teams_team_id_teams'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name=op.f('fk_user_group_teams_user_id_users'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_user_group_teams')),
        sa.UniqueConstraint(
            'user_id', 'group_id', 'team_id',
            name='uq_user_group_teams_user_id_group_id_team_id',
        ),
    )
    with op.batch_alter_table('user_group_teams', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_group_teams_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_group_teams_group_id'), ['group_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_group_teams_team_id'), ['team_id'], unique=False)

    _migrate_rosters_to_private_groups()


def _migrate_rosters_to_private_groups() -> None:
    """Copy every user's flat roster into a private "My teams" group.

    Idempotent (guards on an existing "My teams" private group per user) and
    dialect-agnostic (SELECT-back of the new id rather than ``lastrowid``).
    """
    bind = op.get_bind()
    # JOIN teams so an already-orphaned roster row (a team_id with no team — only
    # reachable if the source DB was corrupted with FK enforcement off) is
    # dropped rather than copied into the new table.
    rows = bind.execute(
        sa.text(
            "SELECT utl.user_id, utl.team_id, utl.sort_order FROM user_team_list utl "
            "JOIN teams t ON t.id = utl.team_id "
            "ORDER BY utl.user_id, utl.sort_order, utl.id"
        )
    ).fetchall()
    by_user: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for user_id, team_id, sort_order in rows:
        by_user[user_id].append((team_id, sort_order))

    for user_id, items in by_user.items():
        existing = bind.execute(
            sa.text(
                "SELECT id FROM team_groups "
                "WHERE owner_user_id = :uid AND name = :name"
            ),
            {"uid": user_id, "name": MY_TEAMS_NAME},
        ).fetchone()
        if existing is not None:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO team_groups "
                "(name, is_active, owner_user_id, created_by_user_id) "
                "VALUES (:name, 1, :uid, :uid)"
            ),
            {"name": MY_TEAMS_NAME, "uid": user_id},
        )
        group_id = bind.execute(
            sa.text(
                "SELECT id FROM team_groups "
                "WHERE owner_user_id = :uid AND name = :name"
            ),
            {"uid": user_id, "name": MY_TEAMS_NAME},
        ).scalar_one()
        for team_id, sort_order in items:
            bind.execute(
                sa.text(
                    "INSERT INTO user_group_teams "
                    "(user_id, group_id, team_id, sort_order) "
                    "VALUES (:uid, :gid, :tid, :so)"
                ),
                {"uid": user_id, "gid": group_id, "tid": team_id, "so": sort_order},
            )


def downgrade() -> None:
    with op.batch_alter_table('user_group_teams', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_group_teams_team_id'))
        batch_op.drop_index(batch_op.f('ix_user_group_teams_group_id'))
        batch_op.drop_index(batch_op.f('ix_user_group_teams_user_id'))
    op.drop_table('user_group_teams')

    # Discards any private groups (they only exist post-upgrade).
    op.execute(sa.text("DELETE FROM team_groups WHERE owner_user_id IS NOT NULL"))
    with op.batch_alter_table('team_groups', schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f('fk_team_groups_owner_user_id_users'), type_='foreignkey',
        )
        batch_op.drop_index(batch_op.f('ix_team_groups_owner_user_id'))
        batch_op.drop_column('owner_user_id')
