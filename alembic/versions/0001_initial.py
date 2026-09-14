"""Create core network tables.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("rubika_user_id", sa.String(128), nullable=False, unique=True),
        sa.Column("username", sa.String(128)),
        sa.Column("display_name", sa.String(255)),
        sa.Column("roles_json", sa.Text(), nullable=False, server_default='["user"]'),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_rubika_user_id", "users", ["rubika_user_id"])

    op.create_table(
        "bot_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("rubika_user_id", sa.String(128), nullable=False),
        sa.Column("bot_name", sa.String(32), nullable=False),
        sa.Column("state", sa.String(64), nullable=False, server_default="idle"),
        sa.Column("data_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("rubika_user_id", "bot_name", name="uq_bot_session_user_bot"),
    )
    op.create_index("ix_bot_sessions_rubika_user_id", "bot_sessions", ["rubika_user_id"])
    op.create_index("ix_bot_sessions_bot_name", "bot_sessions", ["bot_name"])

    op.create_table(
        "lists",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("min_channels", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("next_channel_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_lists_code", "lists", ["code"])

    op.create_table(
        "list_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("list_id", sa.String(36), sa.ForeignKey("lists.id"), nullable=False),
        sa.Column("rubika_user_id", sa.String(128), nullable=False),
        sa.Column("session_ref", sa.String(255)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_list_accounts_list_id", "list_accounts", ["list_id"])
    op.create_index("ix_list_accounts_rubika_user_id", "list_accounts", ["rubika_user_id"])

    op.create_table(
        "channels",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("rubika_guid", sa.String(128), nullable=False, unique=True),
        sa.Column("username", sa.String(128)),
        sa.Column("title", sa.String(255)),
        sa.Column("member_count", sa.Integer()),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("list_id", sa.String(36), sa.ForeignKey("lists.id")),
        sa.Column("list_code", sa.String(32)),
        sa.Column("access_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_send", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_edit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_delete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("verification_notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("list_id", "list_code", name="uq_channel_list_code"),
    )
    op.create_index("ix_channels_rubika_guid", "channels", ["rubika_guid"])
    op.create_index("ix_channels_list_id", "channels", ["list_id"])
    op.create_index("ix_channels_list_code", "channels", ["list_code"])

    op.create_table(
        "registration_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(36), sa.ForeignKey("channels.id"), nullable=False),
        sa.Column("applicant_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("recruited_by_admin_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("assigned_admin_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("list_id", sa.String(36), sa.ForeignKey("lists.id")),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_registration_requests_channel_id", "registration_requests", ["channel_id"])
    op.create_index("ix_registration_requests_applicant_id", "registration_requests", ["applicant_id"])

    op.create_table(
        "tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("assignee_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("payload", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tasks_assignee_id", "tasks", ["assignee_id"])
    op.create_index("ix_tasks_task_type", "tasks", ["task_type"])

    op.create_table(
        "operations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("list_id", sa.String(36), sa.ForeignKey("lists.id"), nullable=False),
        sa.Column("operation_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="planned"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_operations_list_id", "operations", ["list_id"])
    op.create_index("ix_operations_operation_type", "operations", ["operation_type"])
    op.create_index("ix_operations_idempotency_key", "operations", ["idempotency_key"])

    op.create_table(
        "violations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(36), sa.ForeignKey("channels.id"), nullable=False),
        sa.Column("admin_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("violation_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("note", sa.Text()),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_violations_channel_id", "violations", ["channel_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("violations")
    op.drop_table("operations")
    op.drop_table("tasks")
    op.drop_table("registration_requests")
    op.drop_table("channels")
    op.drop_table("list_accounts")
    op.drop_table("lists")
    op.drop_table("bot_sessions")
    op.drop_table("users")
