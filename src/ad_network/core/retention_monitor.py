from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters.rubika import RubikaGateway
from .campaigns import Campaign, CampaignTarget
from .models import Channel, ChannelStatus, Violation


class RetentionMonitor:
    """Detects early deletion and completes targets after retention expires."""

    def __init__(self, db: AsyncSession, gateway: RubikaGateway):
        self.db = db
        self.gateway = gateway

    async def due_targets(self, limit: int = 100) -> list[CampaignTarget]:
        result = await self.db.scalars(
            select(CampaignTarget)
            .where(
                CampaignTarget.status == "published",
                CampaignTarget.published_at.is_not(None),
            )
            .order_by(CampaignTarget.published_at)
            .limit(limit)
        )
        return list(result.all())

    @staticmethod
    def message_exists(raw: object) -> bool:
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
        if channel is None or campaign is None or not target.published_message_id or not target.published_at:
            return False

        published = target.published_at
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        raw = await self.gateway.get_message(channel.rubika_guid, target.published_message_id)
        exists = self.message_exists(raw)
        deadline = published + timedelta(hours=campaign.retention_hours)

        if exists:
            if now >= deadline:
                target.status = "retained"
                await self.db.flush()
            return True

        if now < deadline:
            self.db.add(Violation(
                channel_id=channel.id,
                violation_type="early_ad_deletion",
                severity=2,
                note=f"message {target.published_message_id} deleted before retention deadline",
            ))
            target.status = "failed"
            strikes = await self.db.scalar(select(func.count(Violation.id)).where(
                Violation.channel_id == channel.id,
                Violation.violation_type == "early_ad_deletion",
            ))
            if int(strikes or 0) >= 3:
                channel.status = ChannelStatus.REMOVED
                channel.list_id = None
            await self.db.flush()
            return False

        # The retention contract has already been fulfilled. Missing after the
        # deadline is therefore a successful terminal state, not a new violation.
        target.status = "retained"
        await self.db.flush()
        return True
