from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from .campaigns import Campaign, CampaignService
from .commerce import AdOrder, CommerceService, OrderStatus
from .publisher import RotationPlanner


class OrderFlowService:
    """Application workflow from paid order to scheduled list rotation."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def schedule_paid_order(
        self, order: AdOrder, *, start_at: datetime, interval_seconds: int = 60
    ) -> Campaign:
        if order.status != OrderStatus.PAID:
            raise ValueError("Only paid orders can be scheduled")
        campaign = await CampaignService(self.db).create_campaign(
            title=order.title,
            content_ref=order.content_ref,
            advertiser_id=order.advertiser_id,
            retention_hours=order.retention_hours,
        )
        campaign.status = "scheduled"
        await RotationPlanner(self.db).plan(
            campaign, order.list_id, start_at=start_at, interval_seconds=interval_seconds
        )
        order.status = OrderStatus.SCHEDULED
        order.scheduled_at = start_at
        await self.db.flush()
        return campaign
