"""migrate the legacy flat team roster into groups, then drop it

Groups replaced the flat roster as the unit of team selection: a group's
membership lives in ``team_group_members`` / ``user_group_teams``, and the
virtual "All" group is derived from ``teams.is_global`` /
``teams.owner_user_id``. Nothing in the current app reads ``user_team_list``.

Older installs can still hold rows in it — ``POST /teams/mine`` and
``/team-groups/{id}/copy-to-mine`` were live endpoints, and the SPA used them
before it moved to ``/my/groups*``. A roster row for a **global** team can be
the only record that the user ever picked that team: nothing else in the
schema implies it, so dropping the table outright would lose it. The upgrade
therefore copies those memberships into the user's private "My teams" group
first, creating the group when they have none. This is the copy the comments
in ``app/db/models/team.py`` and ``app/teams_service.py`` attributed to a
"0007 migration" that the migration squash lost — so until now the promise was
made but never kept anywhere in the tree.

Custom teams need no copy: ``teams.owner_user_id`` already implies them, which
is what the virtual "All" group reads.

With every roster fact now living in ``user_group_teams`` or in team
ownership, the downgrade reconstructs the table from those two sources rather
than from a shadow copy. It is a reconstruction, not a byte-exact restore: the
rebuilt ``sort_order`` is derived from team name, and a team the user added to
a group after this upgrade will also appear in the rebuilt roster.

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


# Must match ``app.teams_service.MY_TEAMS_NAME`` — the group this copies into
# is the same one ``seed_user_default_group`` gives every new account, and
# ``tests/test_db_migrations.py`` pins the two together.
MY_TEAMS_GROUP_NAME = 'My teams'

# Roster rows worth preserving: global teams only. A custom team's roster row
# carries nothing ``teams.owner_user_id`` does not already say.
_ROSTER_GLOBALS = sa.text(
    """
    SELECT utl.user_id AS user_id, utl.team_id AS team_id
      FROM user_team_list utl
      JOIN teams t ON t.id = utl.team_id
     WHERE t.is_global = :is_global
     ORDER BY utl.user_id, utl.sort_order, utl.team_id
    """
)


def upgrade() -> None:
    _copy_roster_into_my_teams_group()
    with op.batch_alter_table('user_team_list', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_team_list_user_id'))
        batch_op.drop_index(batch_op.f('ix_user_team_list_team_id'))
    op.drop_table('user_team_list')


def _copy_roster_into_my_teams_group() -> None:
    """Move every roster membership a group does not already hold into groups.

    Runs before the drop and in the same transaction, so either the copy and
    the drop both land or neither does — the table is never dropped with its
    contents unaccounted for.
    """
    bind = op.get_bind()
    rows = bind.execute(_ROSTER_GLOBALS, {"is_global": True}).fetchall()
    if not rows:
        return

    by_user: dict[int, list[int]] = {}
    for user_id, team_id in rows:
        by_user.setdefault(user_id, []).append(team_id)

    for user_id, team_ids in by_user.items():
        group_id = _my_teams_group_id(bind, user_id)
        held = set(
            bind.execute(
                sa.text(
                    "SELECT team_id FROM user_group_teams "
                    " WHERE user_id = :user_id AND group_id = :group_id"
                ),
                {"user_id": user_id, "group_id": group_id},
            ).scalars()
        )
        missing = [tid for tid in dict.fromkeys(team_ids) if tid not in held]
        if not missing:
            continue
        # Append after whatever the group already holds so an existing
        # hand-curated order is preserved.
        next_order = bind.execute(
            sa.text(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM user_group_teams "
                " WHERE user_id = :user_id AND group_id = :group_id"
            ),
            {"user_id": user_id, "group_id": group_id},
        ).scalar_one()
        bind.execute(
            sa.text(
                "INSERT INTO user_group_teams (user_id, group_id, team_id, sort_order) "
                "VALUES (:user_id, :group_id, :team_id, :sort_order)"
            ),
            [
                {
                    "user_id": user_id,
                    "group_id": group_id,
                    "team_id": team_id,
                    "sort_order": next_order + offset,
                }
                for offset, team_id in enumerate(missing)
            ],
        )


def _my_teams_group_id(bind: sa.engine.Connection, user_id: int) -> int:
    """The user's private "My teams" group id, creating the group if needed.

    Accounts created before ``seed_user_default_group`` landed have roster rows
    but no private group at all, so the group cannot be assumed to exist.
    """
    existing = bind.execute(
        sa.text(
            "SELECT id FROM team_groups "
            " WHERE owner_user_id = :user_id AND name = :name "
            " ORDER BY id LIMIT 1"
        ),
        {"user_id": user_id, "name": MY_TEAMS_GROUP_NAME},
    ).scalar()
    if existing is not None:
        return int(existing)
    bind.execute(
        sa.text(
            "INSERT INTO team_groups "
            "(name, is_active, created_by_user_id, owner_user_id) "
            "VALUES (:name, :is_active, :user_id, :user_id)"
        ),
        {"name": MY_TEAMS_GROUP_NAME, "is_active": True, "user_id": user_id},
    )
    created = bind.execute(
        sa.text(
            "SELECT id FROM team_groups "
            " WHERE owner_user_id = :user_id AND name = :name "
            " ORDER BY id DESC LIMIT 1"
        ),
        {"user_id": user_id, "name": MY_TEAMS_GROUP_NAME},
    ).scalar_one()
    return int(created)


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
    _rebuild_roster_from_groups()


# ``UNION`` (not ``UNION ALL``) so a custom team that also sits in one of the
# user's groups yields a single roster row — ``uq_user_team_list_user_id_team_id``
# would reject the duplicate. Ordering by name then id makes ``sort_order``
# deterministic across backends.
_ROSTER_SOURCE = sa.text(
    """
    SELECT ugt.user_id AS user_id, t.id AS team_id, t.name AS name
      FROM user_group_teams ugt
      JOIN teams t ON t.id = ugt.team_id
    UNION
    SELECT t.owner_user_id AS user_id, t.id AS team_id, t.name AS name
      FROM teams t
     WHERE t.owner_user_id IS NOT NULL AND t.is_global = :not_global
    """
)


def _rebuild_roster_from_groups() -> None:
    """Repopulate ``user_team_list`` from the data the app still maintains.

    Runs in the same transaction as the ``create_table`` above, so a failure
    here leaves the downgrade as a whole un-applied rather than a half-filled
    roster.
    """
    bind = op.get_bind()
    rows = bind.execute(_ROSTER_SOURCE, {"not_global": False}).fetchall()
    if not rows:
        return

    by_user: dict[int, list[tuple[str, int]]] = {}
    for user_id, team_id, name in rows:
        by_user.setdefault(user_id, []).append((name or "", team_id))

    payload = [
        {"user_id": user_id, "team_id": team_id, "sort_order": order}
        for user_id, teams in by_user.items()
        for order, (_, team_id) in enumerate(sorted(teams))
    ]
    bind.execute(
        sa.text(
            "INSERT INTO user_team_list (user_id, team_id, sort_order) "
            "VALUES (:user_id, :team_id, :sort_order)"
        ),
        payload,
    )
