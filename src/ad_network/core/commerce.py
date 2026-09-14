from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text, UniqueConstraint, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .models import AuditLog, Base, ListNetwork, User


def enum_column(enum_cls):
    return SAEnum(
        enum_cls,
        native_enum=False,
        values_callable=lambda enum: [item.value for item in enum],
        validate_strings=True,
    )


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


class PaymentStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
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
    status: Mapped[OrderStatus] = mapped_column(enum_column(OrderStatus), default=OrderStatus.DRAFT, index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    order_id: Mapped[str] = mapped_column(ForeignKey("ad_orders.id"), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(32), default="manual")
    status: Mapped[PaymentStatus] = mapped_column(enum_column(PaymentStatus), default=PaymentStatus.PENDING, index=True)
    amount: Mapped[int] = mapped_column(Integer)
    provider_reference: Mapped[str | None] = mapped_column(String(255), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    confirmed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    """Server-side pricing, payment confirmation and campaign activation."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def quote(self, *, list_id: str, channel_count: int, retention_hours: int = 6) -> tuple[int, int]:
        if channel_count <= 0 or retention_hours <= 0:
            raise ValueError("channel_count and retention_hours must be positive")
        rule = await self.db.scalar(select(PriceRule).where(
            PriceRule.list_id == list_id,
            PriceRule.active.is_(True),
            PriceRule.min_channels <= channel_count,
            PriceRule.retention_hours == retention_hours,
        ).order_by(PriceRule.min_channels.desc()))
        if rule is None:
            raise ValueError("No active price rule matches this request")
        return rule.price_per_channel, rule.price_per_channel * channel_count

    async def create_order(
        self,
        *,
        advertiser: User,
        title: str,
        content_ref: str,
        list_id: str,
        channel_count: int,
        retention_hours: int = 6,
        scheduled_at: datetime | None = None,
    ) -> AdOrder:
        if not title.strip():
            raise ValueError("title cannot be empty")
        if not content_ref.strip():
            raise ValueError("content_ref cannot be empty")
        network_list = await self.db.get(ListNetwork, list_id)
        if network_list is None or not network_list.active:
            raise ValueError("Active list not found")
        unit_price, total = await self.quote(
            list_id=list_id,
            channel_count=channel_count,
            retention_hours=retention_hours,
        )
        order = AdOrder(
            advertiser_id=advertiser.id,
            title=title.strip(),
            content_ref=content_ref.strip(),
            list_id=list_id,
            channel_count=channel_count,
            retention_hours=retention_hours,
            unit_price=unit_price,
            total_price=total,
            status=OrderStatus.AWAITING_PAYMENT,
            scheduled_at=scheduled_at,
        )
        self.db.add(order)
        await self.db.flush()
        return order

    async def create_payment(self, order_id: str, *, idempotency_key: str | None = None) -> Payment:
        order = await self.db.get(AdOrder, order_id)
        if order is None:
            raise ValueError("Order not found")
        existing = await self.db.scalar(select(Payment).where(Payment.order_id == order_id))
        if existing:
            return existing
        key = idempotency_key or f"payment:{order_id}"
        key_owner = await self.db.scalar(select(Payment).where(Payment.idempotency_key == key))
        if key_owner is not None and key_owner.order_id != order_id:
            raise ValueError("idempotency_key is already associated with another order")
        payment = Payment(order_id=order.id, amount=order.total_price, idempotency_key=key)
        self.db.add(payment)
        await self.db.flush()
        return payment

    async def confirm_payment(
        self,
        payment_id: str,
        *,
        confirmer_id: str,
        provider_reference: str | None = None,
    ) -> Payment:
        payment = await self.db.get(Payment, payment_id)
        if payment is None:
            raise ValueError("Payment not found")
        if payment.status == PaymentStatus.CONFIRMED:
            return payment
        if payment.status != PaymentStatus.PENDING:
            raise ValueError(f"Cannot confirm payment from state {payment.status}")
        order = await self.db.get(AdOrder, payment.order_id)
        if order is None:
            raise ValueError("Order not found")
        if order.status not in {OrderStatus.AWAITING_PAYMENT, OrderStatus.PAID, OrderStatus.SCHEDULED, OrderStatus.RUNNING}:
            raise ValueError(f"Cannot activate order from state {order.status}")
        if provider_reference:
            duplicate = await self.db.scalar(select(Payment).where(
                Payment.provider_reference == provider_reference,
                Payment.id != payment.id,
            ))
            if duplicate is not None:
                raise ValueError("provider_reference is already associated with another payment")

        from .campaigns import CampaignService

        start_at = order.scheduled_at or datetime.now(timezone.utc)
        campaign_service = CampaignService(self.db)
        campaign = await campaign_service.create_campaign(
            order_id=order.id,
            title=order.title,
            content_ref=order.content_ref,
            advertiser_id=order.advertiser_id,
            retention_hours=order.retention_hours,
        )
        await campaign_service.target_list(
            campaign,
            order.list_id,
            channel_count=order.channel_count,
            start_at=start_at,
            interval_seconds=60,
        )

        payment.status = PaymentStatus.CONFIRMED
        payment.confirmed_by = confirmer_id
        payment.confirmed_at = datetime.now(timezone.utc)
        if provider_reference:
            payment.provider_reference = provider_reference
        now = datetime.now(timezone.utc)
        campaign.status = "scheduled" if start_at > now else "active"
        order.status = OrderStatus.SCHEDULED if campaign.status == "scheduled" else OrderStatus.RUNNING
        self.db.add(AuditLog(
            actor_id=confirmer_id,
            action="payment_confirmed",
            entity_type="payment",
            entity_id=payment.id,
            metadata_json=(
                f'{{"order_id":"{order.id}","amount":{payment.amount},'
                f'"provider_reference":{provider_reference!r}}}'
            ),
        ))
        await self.db.flush()
        return payment

    async def settle(
        self,
        order: AdOrder,
        *,
        list_beneficiary_id: str | None,
        admin_beneficiary_id: str | None,
        list_percent: int = 70,
        admin_percent: int = 20,
    ) -> list[EarningsEntry]:
        if order.status not in {OrderStatus.PAID, OrderStatus.SCHEDULED, OrderStatus.RUNNING, OrderStatus.COMPLETED}:
            raise ValueError("Only paid or executed orders can be settled")
        if list_percent < 0 or admin_percent < 0 or list_percent + admin_percent > 100:
            raise ValueError("Invalid settlement percentages")
        entries: list[EarningsEntry] = []
        for entry_type, beneficiary_id, amount in (
            ("list_share", list_beneficiary_id, order.total_price * list_percent // 100),
            ("admin_share", admin_beneficiary_id, order.total_price * admin_percent // 100),
        ):
            if not beneficiary_id or amount <= 0:
                continue
            existing = await self.db.scalar(select(EarningsEntry).where(
                EarningsEntry.order_id == order.id,
                EarningsEntry.beneficiary_id == beneficiary_id,
                EarningsEntry.entry_type == entry_type,
            ))
            if existing:
                entries.append(existing)
                continue
            entry = EarningsEntry(
                order_id=order.id,
                beneficiary_id=beneficiary_id,
                list_id=order.list_id,
                amount=amount,
                entry_type=entry_type,
            )
            self.db.add(entry)
            entries.append(entry)
        await self.db.flush()
        return entries

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
        entry = EarningsEntry(
            order_id=order.id,
            beneficiary_id=beneficiary_id,
            list_id=order.list_id,
            amount=amount,
            entry_type="list_share",
        )
        self.db.add(entry)
        await self.db.flush()
        return entry
