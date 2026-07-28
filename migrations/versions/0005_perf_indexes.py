"""indexes on the columns every listing filters and orders by

Each index below backs a query that runs on a hot path and previously had
to scan its table (see #433):

* ``teams.is_global``   — the catalog listing, the "All" group, and the
  defence-in-depth filter on every group membership join.
* ``teams.name``        — the upsert key for the admin catalog import and
  the ``ORDER BY`` of four listings.
* ``team_groups.is_active`` — published-group listings.
* ``icons.is_global``   — the global icon library (deliberately uncapped).
* ``presets.scope`` + ``presets.is_active`` — the two halves of the
  ``list_for_user`` OR.
* ``auth_sessions.expires_at`` — the periodic expired-session sweeper
  added alongside this revision; without it the purge would be a
  full-table scan.

These are plain (non-concurrent) ``CREATE INDEX`` statements: migrations
run inside the startup transaction, where Postgres forbids
``CREATE INDEX CONCURRENTLY``. The tables are small enough that the brief
write lock does not matter for any normal deployment.

**Idempotent by design.** Each index is created only if an equivalent one
is not already present — matched by name *or* by indexed column, under any
name. That makes the revision safe to re-run after a partial failure, and
it makes the documented "create them concurrently first, then upgrade"
procedure actually work (see README, *Upgrading*). Without the check a
pre-created index would either collide on the name and abort the startup
migration — leaving the app unable to boot — or be silently duplicated.

Revision ID: 0005_perf_indexes
Revises: 0004_drop_user_team_list
Create Date: 2026-07-28 14:19:22.059434
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0005_perf_indexes'
down_revision: str | None = '0004_drop_user_team_list'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, column) pairs, in creation order.
_INDEXES: tuple[tuple[str, str], ...] = (
    ('auth_sessions', 'expires_at'),
    ('icons', 'is_global'),
    ('presets', 'is_active'),
    ('presets', 'scope'),
    ('team_groups', 'is_active'),
    ('teams', 'is_global'),
    ('teams', 'name'),
)


def _index_name(table: str, column: str) -> str:
    """Mirrors ``NAMING_CONVENTION['ix']`` in ``app/db/base.py``."""
    return f'ix_{table}_{column}'


def _reflected_indexes(table: str) -> list[dict]:
    return sa.inspect(op.get_bind()).get_indexes(table)


def upgrade() -> None:
    for table, column in _INDEXES:
        name = _index_name(table, column)
        existing = _reflected_indexes(table)
        # Match on either the name or the indexed column: a hand-created index
        # may carry a different name but serve exactly the same query.
        if any(
            ix['name'] == name or list(ix['column_names']) == [column]
            for ix in existing
        ):
            continue
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.create_index(batch_op.f(name), [column], unique=False)


def downgrade() -> None:
    # Only drop what this revision could have created — an index an operator
    # made by hand under a different name is theirs to keep.
    for table, column in reversed(_INDEXES):
        name = _index_name(table, column)
        if not any(ix['name'] == name for ix in _reflected_indexes(table)):
            continue
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_index(batch_op.f(name))
