import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters.rubika import RubikaGateway
from .commerce import AdOrder, EarningsEntry, Payment, PriceRule  # noqa: F401
from .models import (
    AuditLog,
    Channel,
    ChannelStatus,
    ListNetwork,
    RegistrationRequest,
    RegistrationSource,
    RegistrationStatus,
    Task,
    TaskStatus,
    User,
    Violation,
)


async def audit(
    db: AsyncSession,
    *,
    actor_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str,
    metadata: dict | None = None,
):