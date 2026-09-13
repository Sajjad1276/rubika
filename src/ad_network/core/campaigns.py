from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base, Channel, ChannelStatus, ListNetwork, Operation, OperationStatus


class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(255))
    advertiser_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    content_ref: Mapped[str] = mapped_column(Text)
    retention_hours: Mapped[int] = mapped_column(Integer, default=6)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CampaignTarget(Base):
    __tablename__ = "campaign_targets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    list_id: Mapped[str] = mapped_column(ForeignKey("lists.id"), index=True)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"), index=True)
    planned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_message_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="planned", index=True)

    __table_args__ = (UniqueConstraint("campaign_id", "channel_id", name="uq_campaign_channel"),)


class CampaignService:
    """Creates deterministic publish targets; transport is handled by the Rubika adapter."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_campaign(
        self,
        *,
        title: str,
        content_ref: str,
        advertiser_id: str | None = None,
        retention_hours: int = 6,
    ) -> Campaign:
        if retention_hours <= 0:
            raise ValueError("retention_hours must be positive")
        campaign = Campaign(
            title=title,
            content_ref=content_ref,
            advertiser_id=advertiser_id,
            retention_hours=retention_hours,
        )
        self.db.add(campaign)
        await self.db.flush()
        return campaign

    async def target_list(self, campaign: Campaign, list_id: str, planned_at: datetime | None = None) -> int:
        network_list = await self.db.get(ListNetwork, list_id)
        if network_list is None or not network_list.active:
            raise ValueError("Active list not found")

        channels = (
            await self.db.scalars(
                select(Channel).where(
                    Channel.list_id == list_id,
                    Channel.status == ChannelStatus.ACTIVE,
                ).order_by(Channel.list_code)
            )
        ).all()
        created = 0
        for channel in channels:
            exists = await self.db.scalar(
                select(CampaignTarget.id).where(
                    CampaignTarget.campaign_id == campaign.id,
                    CampaignTarget.channel_id == channel.id,
                )
            )
            if exists:
                continue
            self.db.add(
                CampaignTarget(
                    campaign_id=campaign.id,
                    list_id=list_id,
                    channel_id=channel.id,
                    planned_at=planned_at,
                )
            )
            created += 1
        await self.db.flush()
        return created

    async def plan_operation(
        self,
        *,
        list_id: str,
        scheduled_at: datetime,
        idempotency_key: str,
    ) -> Operation:
        existing = await self.db.scalar(
            select(Operation).where(Operation.idempotency_key == idempotency_key)
        )
        if existing:
            return existing
        operation = Operation(
            list_id=list_id,
            operation_type="campaign_publish",
            status=OperationStatus.PLANNED,
            scheduled_at=scheduled_at,
            idempotency_key=idempotency_key,
        )
        self.db.add(operation)
        await self.db.flush()
        return operation
