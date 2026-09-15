"""Expand list/channel fields for the OPEX Owner control center.

Revision ID: 0004_opex_owner_domain
Revises: 0003_normalize_enum_values
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_opex_owner_domain"
down_revision = "0003_normalize_enum_values"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lists", sa.Column("list_type", sa.String(length=16), nullable=False, server_default="pulse"))
    op.add_column("lists", sa.Column("min_stat", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("lists", sa.Column("required_views", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("lists", sa.Column("retention_hours", sa.Integer(), nullable=False, server_default="12"))
    op.add_column("lists", sa.Column("max_channels", sa.Integer(), nullable=False, server_default="1000"))
    op.add_column("lists", sa.Column("status", sa.String(length=24), nullable=False, server_default="active"))
    op.create_index("ix_lists_list_type", "lists", ["list_type"], unique=False)
    op.create_index("ix_lists_status", "lists", ["status"], unique=False)

    op.add_column("channels", sa.Column("views_24h", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("channels", sa.Column("violation_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("channels", sa.Column("last_ad_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("channels", "last_ad_at")
    op.drop_column("channels", "violation_count")
    op.drop_column("channels", "views_24h")
    op.drop_index("ix_lists_status", table_name="lists")
    op.drop_index("ix_lists_list_type", table_name="lists")
    op.drop_column("lists", "status")
    op.drop_column("lists", "max_channels")
    op.drop_column("lists", "retention_hours")
    op.drop_column("lists", "required_views")
    op.drop_column("lists", "min_stat")
    op.drop_column("lists", "list_type")
