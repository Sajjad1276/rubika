from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..application.ports import MessageGateway
from .campaigns import Campaign, CampaignTarget
from .clock import utc_now
from .models import Channel, ChannelStatus, Violation


class RetentionMonitor:
    """Evaluate retention guarantees and record early-deletion violations."""

    def __init__(self, db: AsyncSession, gateway: MessageGateway):
        self.db = db
        self.gateway = gateway

    async def due_targets(self, limit: int = 100) -> list[CampaignTarget]:
        if limit <= 0:
            return []
        result = await self.db.scalars(
            select(CampaignTarget)
            .where(
                CampaignTarget.status == "published",
                CampaignTarget.published_at.is_not(None),
            )
            .order_by(CampaignTarget.published_at, CampaignTarget.id)
            .limit(limit)
        )
        return list(result.all())

    @staticmethod
    def message_exists(raw: object) -> bool:
        """Interpret the common MAXRubika response envelopes safely."""
        if raw is None:
            return False
        if isinstance(raw, list):
            return bool(raw)
        if isinstance(raw, dict):
            messages = raw.get("messages")
            if isinstance(messages, list):
                return bool(messages)
            return bool(raw.get("message") or raw.get("data") or raw.get("message_update"))
        return True

    async def check(self, target: CampaignTarget) -> bool:
        channel = await self.db.get(Channel, target.channel_id)
        campaign = await self.db.get(Campaign, target.campaign_id)
        if (
            channel is None
            or campaign is None
            or not target.published_message_id
            or not target.published_at
        ):
            return False

        published = target.published_at
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        else:
            published = published.astimezone(timezone.utc)

        now = utc_now()
        deadline = published + timedelta(hours=campaign.retention_hours)
        raw = await self.gateway.get_message(channel.rubika_guid, target.published_message_id)

        if self.message_exists(raw):
            if now >= deadline:
                target.status = "retained"
                await self.db.flush()
            return True

        if now >= deadline:
            # The message was already absent when the retention window ended.
            # It cannot be proven that deletion happened before the deadline,
            # so mark the target failed without creating a false violation.
            target.status = "failed"
            await self.db.flush()
            return False

        self.db.add(
            Violation(
                channel_id=channel.id,
                violation_type="early_ad_deletion",
                severity=2,
                note=(
                    f"message {target.published_message_id} deleted before retention deadline"
                ),
            )
        )
        channel.violation_count = (channel.violation_count or 0) + 1
        target.status = "failed"

        strikes = await self.db.scalar(
            select(func.count(Violation.id)).where(
                Violation.channel_id == channel.id,
                Violation.violation_type == "early_ad_deletion",
            )
        )
        if int(strikes or 0) >= 3:
            channel.status = ChannelStatus.REMOVED
            channel.list_id = None

        await self.db.flush()
        return False
