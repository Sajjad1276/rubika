from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters.rubika import RubikaGateway
from .campaigns import Campaign, CampaignTarget
from .models import Channel

logger = logging.getLogger(__name__)


def _message_id(result: Any) -> str | None:
    if isinstance(result, dict):
        for key in ("message_id", "id"):
            if result.get(key):
                return str(result[key])
        update = result.get("message_update")
        if isinstance(update, dict) and update.get("message_id"):
            return str(update["message_id"])
    for key in ("message_id", "id"):
        value = getattr(result, key, None)
        if value:
            return str(value)
    return None


class PublicationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def due_targets(self, *, limit: int = 50) -> list[CampaignTarget]:
        now = datetime.now(timezone.utc)
        result = await self.db.scalars(
            select(CampaignTarget)
            .join(Campaign, Campaign.id == CampaignTarget.campaign_id)
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
    def __init__(self, db: AsyncSession):
        self.db = db

    async def plan(self, campaign: Campaign, list_id: str, start_at: datetime,
                   interval_seconds: int = 60) -> int:
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
            target.planned_at = start_at + timedelta(seconds=index * interval_seconds)
        await self.db.flush()
        return created


class RotationExecutor:
    def __init__(self, db: AsyncSession, gateway: RubikaGateway):
        self.db = db
        self.gateway = gateway

    async def execute(self, target: CampaignTarget, *, source_guid: str,
                      source_message_id: str) -> bool:
        if target.status != "planned":
            return False
        service = PublicationService(self.db)
        await service.claim(target)
        channel = await self.db.get(Channel, target.channel_id)
        if channel is None:
            await service.mark_failed(target)
            return False
        try:
            result = await self.gateway.forward(source_guid, channel.rubika_guid, source_message_id)
            message_id = _message_id(result)
            if not message_id:
                raise RuntimeError("Rubika forward response did not contain a message id")
            await service.mark_published(target, message_id)
            return True
        except Exception:
            logger.exception("campaign target publication failed: %s", target.id)
            await service.mark_failed(target)
            return False
