from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..application.ports import MessageGateway
from .campaigns import Campaign, CampaignTarget, CampaignService
from .clock import utc_now
from .models import Channel, ChannelStatus

logger = logging.getLogger(__name__)


def _raw(result: Any) -> Any:
    """Normalize MAXRubika response objects without coupling application code to SDK types."""
    if result is None:
        return None
    to_dict = getattr(result, "to_dict", None)
    if callable(to_dict):
        try:
            return to_dict()
        except Exception:
            logger.debug("Unable to convert gateway response to dict", exc_info=True)
    original_data = getattr(result, "original_data", None)
    return original_data if original_data is not None else result


def extract_message_id(result: Any) -> str | None:
    """Extract a published message id from known Rubika response shapes."""
    result = _raw(result)
    if isinstance(result, dict):
        for key in ("message_id", "id"):
            value = result.get(key)
            if value:
                return str(value)
        for key in ("message_update", "message", "messages"):
            value = result.get(key)
            if value:
                return extract_message_id(value)
    if isinstance(result, (list, tuple)) and result:
        return extract_message_id(result[0])
    for key in ("message_id", "id"):
        value = getattr(result, key, None)
        if value:
            return str(value)
    return None


class PublicationService:
    """Persistence use cases for claim-and-publish target state transitions."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def due_targets(self, *, limit: int = 50) -> list[CampaignTarget]:
        if limit <= 0:
            return []
        result = await self.db.scalars(
            select(CampaignTarget)
            .join(Campaign, Campaign.id == CampaignTarget.campaign_id)
            .join(Channel, Channel.id == CampaignTarget.channel_id)
            .where(
                Campaign.status.in_(["active", "scheduled"]),
                CampaignTarget.status == "planned",
                CampaignTarget.planned_at.is_not(None),
                CampaignTarget.planned_at <= utc_now(),
                Channel.status == ChannelStatus.ACTIVE,
            )
            .order_by(CampaignTarget.planned_at, CampaignTarget.id)
            .limit(limit)
        )
        return list(result.all())

    async def claim(self, target: CampaignTarget) -> bool:
        """Atomically claim a planned target, making concurrent workers safe."""
        result = await self.db.execute(
            update(CampaignTarget)
            .where(CampaignTarget.id == target.id, CampaignTarget.status == "planned")
            .values(status="running")
        )
        if result.rowcount != 1:
            return False
        target.status = "running"
        await self.db.flush()
        return True

    async def mark_published(self, target: CampaignTarget, message_id: str) -> None:
        if not message_id.strip():
            raise ValueError("message_id must not be empty")
        target.status = "published"
        target.published_at = utc_now()
        target.published_message_id = message_id.strip()
        await self.db.flush()

    async def mark_failed(self, target: CampaignTarget) -> None:
        target.status = "failed"
        await self.db.flush()


class RotationPlanner:
    """Compatibility facade for callers that still use the legacy planner API."""

    def __init__(self, db: AsyncSession):
        self.service = CampaignService(db)

    async def plan(
        self,
        campaign: Campaign,
        list_id: str,
        start_at: datetime,
        interval_seconds: int = 60,
        channel_count: int | None = None,
    ) -> int:
        return await self.service.target_list(
            campaign,
            list_id,
            channel_count=channel_count,
            start_at=start_at,
            interval_seconds=interval_seconds,
        )


class RotationExecutor:
    """Orchestrates the application workflow while depending only on a gateway port."""

    def __init__(self, db: AsyncSession, gateway: MessageGateway):
        self.db = db
        self.gateway = gateway
        self.publication = PublicationService(db)

    async def execute(
        self,
        target: CampaignTarget,
        *,
        source_guid: str,
        source_message_id: str,
    ) -> bool:
        if target.status != "planned":
            return False
        if not await self.publication.claim(target):
            return False

        channel = await self.db.get(Channel, target.channel_id)
        if channel is None or channel.status != ChannelStatus.ACTIVE:
            await self.publication.mark_failed(target)
            return False

        try:
            result = await self.gateway.forward(
                source_guid,
                channel.rubika_guid,
                source_message_id,
            )
            message_id = extract_message_id(result)
            if message_id is None:
                raise RuntimeError("Rubika forward response did not contain a message id")

            await self.publication.mark_published(target, message_id)
            channel.last_ad_at = utc_now()
            await self.db.flush()
            return True
        except Exception:
            logger.exception("Campaign target publication failed: %s", target.id)
            await self.publication.mark_failed(target)
            return False
