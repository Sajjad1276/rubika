"""Normalize status/source values to their public string representation.

Revision ID: 0003_normalize_enum_values
Revises: 0002_commerce
"""
from alembic import op

revision = "0003_normalize_enum_values"
down_revision = "0002_commerce"
branch_labels = None
depends_on = None


_ENUM_COLUMNS = (
    ("channels", "status", "ChannelStatus"),
    ("registration_requests", "source", "RegistrationSource"),
    ("registration_requests", "status", "RegistrationStatus"),
    ("tasks", "status", "TaskStatus"),
    ("operations", "status", "OperationStatus"),
    ("ad_orders", "status", "OrderStatus"),
    ("payments", "status", "PaymentStatus"),
)


def upgrade() -> None:
    connection = op.get_bind()
    for table, column, _ in _ENUM_COLUMNS:
        connection.exec_driver_sql(
            f"UPDATE {table} SET {column} = LOWER({column}) WHERE {column} IS NOT NULL"
        )


def downgrade() -> None:
    # Values are intentionally stored in their stable public lowercase form.
    pass
