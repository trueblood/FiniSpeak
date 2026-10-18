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


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "deleted_at" not in columns:
        op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    if "deleted_by" not in columns:
        op.add_column("users", sa.Column("deleted_by", sa.String(128)))
    foreign_keys = {item.get("name") for item in inspector.get_foreign_keys("users")}
    if "fk_users_deleted_by_users" not in foreign_keys:
        op.create_foreign_key(
            "fk_users_deleted_by_users", "users", "users", ["deleted_by"], ["id"], ondelete="SET NULL"
        )
    indexes = {item["name"] for item in inspector.get_indexes("users")}
    if "ix_users_deleted_at" not in indexes:
        op.create_index("ix_users_deleted_at", "users", ["deleted_at"])
    if "friends" not in inspector.get_table_names():
        charset, collation = "utf8mb4", "utf8mb4_0900_ai_ci"
        if bind.dialect.name == "mysql":
            row = bind.execute(sa.text("""
                SELECT CHARACTER_SET_NAME AS charset_name, COLLATION_NAME AS collation_name
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'id'
            """)).mappings().one()
            charset, collation = row["charset_name"], row["collation_name"]
        string_id = sa.String(128, collation=collation)
        op.create_table(
            "friends",
            sa.Column("owner_id", string_id, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("friend_id", string_id, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("nickname", sa.String(160, collation=collation)),
            sa.Column("saved_phone", sa.String(64, collation=collation)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            mysql_charset=charset,
            mysql_collate=collation,
        )
        op.create_index("ix_friends_friend_id", "friends", ["friend_id"])


def downgrade():
    op.drop_table("friends")
    op.drop_index("ix_users_deleted_at", table_name="users")
    op.drop_constraint("fk_users_deleted_by_users", "users", type_="foreignkey")
    op.drop_column("users", "deleted_by")
    op.drop_column("users", "deleted_at")
