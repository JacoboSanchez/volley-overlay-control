"""drop the legacy flat team roster

Groups replaced the flat roster as the unit of team selection: a group's
membership lives in ``team_group_members`` / ``user_group_teams``, and the
virtual "All" group is derived from ``teams.is_global`` /
``teams.owner_user_id``. Nothing in the current app reads ``user_team_list``,
so the upgrade drops it.

Older installs can still hold rows in it — ``POST /teams/mine`` and
``/team-groups/{id}/copy-to-mine`` were live endpoints, and the SPA used them
before it moved to ``/my/groups*``. Those rows stopped being maintained long
before this revision, so the downgrade does not try to restore them
byte-for-byte from a shadow copy. It **reconstructs** each user's roster from
what the app has actually been keeping current: every team in one of their
``user_group_teams`` rows, plus every custom team they own (which the old
``create_user_team`` always mirrored into the roster). A downgraded install
therefore comes back with a populated, current ``GET /teams`` and
``/teams/mine`` rather than an empty one — not necessarily the same rows it
had before the upgrade, which by then reflected a list the operator had no way
to edit.

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
