from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base, ListNetwork, User


class OrderStatus(StrEnum):
    DRAFT = "draft"
    QUOTED = "quoted"
    AWAITING_PAYMENT = "awaiting_payment"
    PAID = "paid"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class PriceRule(Base):
    __tablename__ = "price_rules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    list_id: Mapped[str | None] = mapped_column(ForeignKey("lists.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    min_channels: Mapped[int] = mapped_column(Integer, default=1)
    price_per_channel: Mapped[int] = mapped_column(Integer)
    retention_hours: Mapped[int] = mapped_column(Integer, default=6)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdOrder(Base):
    __tablename__ = "ad_orders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    advertiser_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    content_ref: Mapped[str] = mapped_column(Text)
    list_id: Mapped[str] = mapped_column(ForeignKey("lists.id"), index=True)
    channel_count: Mapped[int] = mapped_column(Integer)
    retention_hours: Mapped[int] = mapped_column(Integer, default=6)
    unit_price: Mapped[int] = mapped_column(Integer)
    total_price: Mapped[int] = mapped_column(Integer)
    status: Mapped[OrderStatus] = mapped_column(default=OrderStatus.DRAFT, index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EarningsEntry(Base):
    __tablename__ = "earnings_entries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    order_id: Mapped[str] = mapped_column(ForeignKey("ad_orders.id"), index=True)
    beneficiary_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    list_id: Mapped[str] = mapped_column(ForeignKey("lists.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    entry_type: Mapped[str] = mapped_column(String(32), default="list_share")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("order_id", "beneficiary_id", "entry_type", name="uq_earning_entry"),)


class CommerceService:
    """Quotes orders from active pricing rules and keeps money calculations server-side."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def quote(self, *, list_id: str, channel_count: int, retention_hours: int = 6) -> tuple[int, int]:
        if channel_count <= 0 or retention_hours <= 0:
            raise ValueError("channel_count and retention_hours must be positive")
        rule = await self.db.scalar(
            select(PriceRule).where(
                PriceRule.list_id == list_id,
                PriceRule.active.is_(True),
                PriceRule.min_channels <= channel_count,
                PriceRule.retention_hours == retention_hours,
            ).order_by(PriceRule.min_channels.desc())
        )
        if rule is None:
            raise ValueError("No active price rule matches this request")
        return rule.price_per_channel, rule.price_per_channel * channel_count

    async def create_order(
        self, *, advertiser: User, title: str, content_ref: str, list_id: str,
        channel_count: int, retention_hours: int = 6, scheduled_at: datetime | None = None,
    ) -> AdOrder:
        network_list = await self.db.get(ListNetwork, list_id)
        if network_list is None or not network_list.active:
            raise ValueError("Active list not found")
        unit_price, total = await self.quote(
            list_id=list_id, channel_count=channel_count, retention_hours=retention_hours
        )
        order = AdOrder(
            advertiser_id=advertiser.id, title=title, content_ref=content_ref,
            list_id=list_id, channel_count=channel_count, retention_hours=retention_hours,
            unit_price=unit_price, total_price=total,
            status=OrderStatus.QUOTED, scheduled_at=scheduled_at,
        )
        self.db.add(order)
        await self.db.flush()
        return order

    async def mark_paid(self, order_id: str) -> AdOrder:
        order = await self.db.get(AdOrder, order_id)
        if order is None:
            raise ValueError("Order not found")
        if order.status not in {OrderStatus.QUOTED, OrderStatus.AWAITING_PAYMENT}:
            raise ValueError(f"Cannot pay order from state {order.status}")
        order.status = OrderStatus.PAID
        await self.db.flush()
        return order

    async def record_list_earning(self, order: AdOrder, beneficiary_id: str, amount: int) -> EarningsEntry:
        if amount < 0 or amount > order.total_price:
            raise ValueError("Invalid earning amount")
        existing = await self.db.scalar(select(EarningsEntry).where(
            EarningsEntry.order_id == order.id,
            EarningsEntry.beneficiary_id == beneficiary_id,
            EarningsEntry.entry_type == "list_share",
        ))
        if existing:
            return existing
        entry = EarningsEntry(order_id=order.id, beneficiary_id=beneficiary_id,
                              list_id=order.list_id, amount=amount)
        self.db.add(entry)
        await self.db.flush()
        return entry
