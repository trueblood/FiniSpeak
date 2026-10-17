"""Add friends and account soft deletion.

Revision ID: 20261016_0004
Revises: 20261014_0003
"""

from alembic import op
import sqlalchemy as sa


revision = "20261016_0004"
down_revision = "20261014_0003"
branch_labels = None
depends_on = None


MYSQL_TABLE_OPTIONS = {
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def upgrade():
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("deleted_by", sa.String(128)))
    op.create_foreign_key(
        "fk_users_deleted_by_users", "users", "users", ["deleted_by"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"])
    op.create_table(
        "friends",
        sa.Column("owner_id", sa.String(128), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("friend_id", sa.String(128), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("nickname", sa.String(160)),
        sa.Column("saved_phone", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        **MYSQL_TABLE_OPTIONS,
    )
    op.create_index("ix_friends_friend_id", "friends", ["friend_id"])


def downgrade():
    op.drop_table("friends")
    op.drop_index("ix_users_deleted_at", table_name="users")
    op.drop_constraint("fk_users_deleted_by_users", "users", type_="foreignkey")
    op.drop_column("users", "deleted_by")
    op.drop_column("users", "deleted_at")
