"""add non-reusable user browser-storage namespace

Revision ID: 0007_user_storage_namespace
Revises: 0006_overlay_favorites
Create Date: 2026-08-15
"""

from __future__ import annotations

import secrets
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_user_storage_namespace"
down_revision: str | None = "0006_overlay_favorites"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    sqlite = connection.dialect.name == "sqlite"
    if sqlite:
        # This migration connection comes from Alembic's dedicated NullPool.
        # Disable FK actions before any DML starts a SQLite transaction so the
        # later batch rebuild cannot cascade-delete rows that reference users.
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("storage_namespace", sa.String(length=32), nullable=True),
        )

    users = sa.table(
        "users",
        sa.column("id", sa.Integer()),
        sa.column("storage_namespace", sa.String(length=32)),
    )
    user_ids = connection.execute(sa.select(users.c.id)).scalars().all()
    for user_id in user_ids:
        connection.execute(
            users.update()
            .where(users.c.id == user_id)
            .values(storage_namespace=secrets.token_hex(16)),
        )

    # SQLite implements ALTER COLUMN / UNIQUE constraints by rebuilding the
    # table. FK actions stay disabled for that structural copy; the copied user
    # ids keep every reference valid.
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column(
            "storage_namespace",
            existing_type=sa.String(length=32),
            nullable=False,
        )
        batch_op.create_unique_constraint(
            "uq_users_storage_namespace",
            ["storage_namespace"],
        )
    if sqlite:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    connection = op.get_bind()
    sqlite = connection.dialect.name == "sqlite"
    if sqlite:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint("uq_users_storage_namespace", type_="unique")
        batch_op.drop_column("storage_namespace")
    if sqlite:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
