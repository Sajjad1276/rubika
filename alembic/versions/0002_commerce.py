"""Add campaigns, pricing, orders, payments and earnings tables.

Revision ID: 0002_commerce
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_commerce"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("advertiser_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("content_ref", sa.Text(), nullable=False),
        sa.Column("retention_hours", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_campaigns_status", "campaigns", ["status"])

    op.create_table(
        "campaign_targets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("campaign_id", sa.String(36), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("list_id", sa.String(36), sa.ForeignKey("lists.id"), nullable=False),
        sa.Column("channel_id", sa.String(36), sa.ForeignKey("channels.id"), nullable=False),
        sa.Column("planned_at", sa.DateTime(timezone=True)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("published_message_id", sa.String(128)),
        sa.Column("status", sa.String(32), nullable=False, server_default="planned"),
        sa.UniqueConstraint("campaign_id", "channel_id", name="uq_campaign_channel"),
    )
    for name, column in (("ix_campaign_targets_campaign_id", "campaign_id"), ("ix_campaign_targets_list_id", "list_id"), ("ix_campaign_targets_channel_id", "channel_id"), ("ix_campaign_targets_status", "status")):
        op.create_index(name, "campaign_targets", [column])

    op.create_table(
        "price_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("list_id", sa.String(36), sa.ForeignKey("lists.id")),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("min_channels", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("price_per_channel", sa.Integer(), nullable=False),
        sa.Column("retention_hours", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_price_rules_list_id", "price_rules", ["list_id"])

    op.create_table(
        "ad_orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("advertiser_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content_ref", sa.Text(), nullable=False),
        sa.Column("list_id", sa.String(36), sa.ForeignKey("lists.id"), nullable=False),
        sa.Column("channel_count", sa.Integer(), nullable=False),
        sa.Column("retention_hours", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("unit_price", sa.Integer(), nullable=False),
        sa.Column("total_price", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    for name, column in (("ix_ad_orders_advertiser_id", "advertiser_id"), ("ix_ad_orders_list_id", "list_id"), ("ix_ad_orders_status", "status")):
        op.create_index(name, "ad_orders", [column])

    op.create_table(
        "payments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("ad_orders.id"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_reference", sa.String(255)),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("order_id", "provider", name="uq_payment_order_provider"),
    )
    op.create_index("ix_payments_order_id", "payments", ["order_id"])
    op.create_index("ix_payments_status", "payments", ["status"])

    op.create_table(
        "earnings_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("ad_orders.id"), nullable=False),
        sa.Column("beneficiary_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("list_id", sa.String(36), sa.ForeignKey("lists.id"), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("entry_type", sa.String(32), nullable=False, server_default="list_share"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("order_id", "beneficiary_id", "entry_type", name="uq_earning_entry"),
    )
    for name, column in (("ix_earnings_entries_order_id", "order_id"), ("ix_earnings_entries_beneficiary_id", "beneficiary_id"), ("ix_earnings_entries_list_id", "list_id")):
        op.create_index(name, "earnings_entries", [column])


def downgrade() -> None:
    op.drop_table("earnings_entries")
    op.drop_table("payments")
    op.drop_table("ad_orders")
    op.drop_table("price_rules")
    op.drop_table("campaign_targets")
    op.drop_table("campaigns")
