from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    Channel, ChannelStatus, ListNetwork, RegistrationRequest, RegistrationSource,
    RegistrationStatus, User,
)


class RegistrationService:
    """Business workflow shared by self-registration and admin recruitment."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def start(
        self,
        *,
        rubika_guid: str,
        applicant: User,
        source: RegistrationSource,
        recruited_by_admin_id: str | None = None,
        list_id: str | None = None,
    ) -> RegistrationRequest:
        channel = await self.db.scalar(select(Channel).where(Channel.rubika_guid == rubika_guid))
        if channel is None:
            channel = Channel(rubika_guid=rubika_guid, status=ChannelStatus.PENDING, list_id=list_id)
            self.db.add(channel)
            await self.db.flush()

        request = RegistrationRequest(
            channel_id=channel.id,
            applicant_id=applicant.id,
            source=source,
            recruited_by_admin_id=recruited_by_admin_id,
            assigned_admin_id=recruited_by_admin_id,
            list_id=list_id,
            status=RegistrationStatus.DRAFT,
        )
        self.db.add(request)
        await self.db.flush()
        return request

    async def submit_for_verification(self, request: RegistrationRequest) -> RegistrationRequest:
        if request.status not in {RegistrationStatus.DRAFT, RegistrationStatus.REJECTED}:
            raise ValueError(f"Cannot submit request from state {request.status}")
        request.status = RegistrationStatus.PENDING_VERIFICATION
        await self.db.flush()
        return request

    async def verify(self, request: RegistrationRequest, approved: bool) -> RegistrationRequest:
        if request.status != RegistrationStatus.PENDING_VERIFICATION:
            raise ValueError(f"Cannot verify request from state {request.status}")
        request.status = RegistrationStatus.VERIFIED if approved else RegistrationStatus.REJECTED
        await self.db.flush()
        return request


class ListService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def allocate_channel_code(self, list_id: str) -> str:
        network_list = await self.db.get(ListNetwork, list_id)
        if network_list is None:
            raise ValueError("List not found")
        rows = (await self.db.scalars(
            select(Channel.list_code)
            .where(Channel.list_id == list_id, Channel.list_code.is_not(None))
        )).all()
        used = {int(code[1:]) for code in rows if code and code[1:].isdigit()}
        number = 1
        while number in used:
            number += 1
        return f"#{number:03d}"
