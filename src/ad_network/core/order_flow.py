from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .campaigns import Campaign, CampaignService
from .commerce import AdOrder, CommerceService, OrderStatus
from .publisher import RotationPlanner


class OrderFlowService:
    """Application workflow from paid order to scheduled list rotation."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def schedule_paid_order(
        self,
        order: AdOrder,
        *,
        start_at: datetime,
        interval_seconds: int = 60,
        list_beneficiary_id: str | None = None,
        admin_beneficiary_id: str | None = None,
    ) -> Campaign:
        existing = await self.db.scalar(select(Campaign).where(Campaign.order_id == order.id))
        if existing:
            return existing
        if order.status != OrderStatus.PAID:
            raise ValueError("Only paid orders can be scheduled")
        campaign = await CampaignService(self.db).create_campaign(
            title=order.title,
            content_ref=order.content_ref,
            advertiser_id=order.advertiser_id,
            retention_hours=order.retention_hours,
            order_id=order.id,
        )
        campaign.status = "scheduled"
        await RotationPlanner(self.db).plan(
            campaign,
            order.list_id,
            start_at=start_at,
            interval_seconds=interval_seconds,
            channel_count=order.channel_count,
        )
        await CampaignService(self.db).plan_operation(
            list_id=order.list_id,
            scheduled_at=start_at,
            idempotency_key=f"order:{order.id}:publish",
        )
        await CommerceService(self.db).settle(
            order,
            list_beneficiary_id=list_beneficiary_id,
            admin_beneficiary_id=admin_beneficiary_id,
        )
        order.status = OrderStatus.SCHEDULED
        order.scheduled_at = start_at
        await self.db.flush()
        return campaign
