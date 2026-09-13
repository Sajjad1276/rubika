from datetime import datetime, timezone
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .campaigns import Campaign, CampaignTarget
from .models import Channel, Operation, OperationStatus

logger = logging.getLogger(__name__)


class PublicationService:
    """Turns scheduled campaign targets into transport jobs without embedding Rubika logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def due_targets(self, *, limit: int = 50) -> list[CampaignTarget]:
        now = datetime.now(timezone.utc)
        result = await self.db.scalars(
            select(CampaignTarget).join(Campaign, Campaign.id == CampaignTarget.campaign_id)
            .where(
                Campaign.status.in_(["active", "scheduled"]),
                CampaignTarget.status == "planned",
                CampaignTarget.planned_at.is_not(None),
                CampaignTarget.planned_at <= now,
            )
            .order_by(CampaignTarget.planned_at)
            .limit(limit)
        )
        return list(result.all())

    async def claim(self, target: CampaignTarget) -> CampaignTarget:
        if target.status != "planned":
            raise ValueError("Target is not claimable")
        target.status = "running"
        await self.db.flush()
        return target

    async def mark_published(self, target: CampaignTarget, message_id: str) -> CampaignTarget:
        target.status = "published"
        target.published_at = datetime.now(timezone.utc)
        target.published_message_id = message_id
        await self.db.flush()
        return target

    async def mark_failed(self, target: CampaignTarget) -> CampaignTarget:
        target.status = "failed"
        await self.db.flush()
        return target


class RotationPlanner:
    """Builds a one-minute-spaced rotation for a list."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def plan(self, campaign: Campaign, list_id: str, start_at: datetime, interval_seconds: int = 60) -> int:
        from .campaigns import CampaignService
        if interval_seconds < 1:
            raise ValueError("interval_seconds must be positive")
        created = await CampaignService(self.db).target_list(campaign, list_id)
        targets = list((await self.db.scalars(
            select(CampaignTarget).where(
                CampaignTarget.campaign_id == campaign.id,
                CampaignTarget.list_id == list_id,
                CampaignTarget.status == "planned",
            ).order_by(CampaignTarget.channel_id)
        )).all())
        for index, target in enumerate(targets):
            target.planned_at = start_at + __import__("datetime").timedelta(seconds=index * interval_seconds)
        await self.db.flush()
        return created
