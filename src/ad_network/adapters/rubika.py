from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ChannelSnapshot:
    guid: str
    title: str | None = None
    username: str | None = None
    member_count: int | None = None


class RubikaGateway(Protocol):
    async def get_channel(self, guid: str) -> ChannelSnapshot: ...
    async def forward(self, source_guid: str, target_guid: str, message_id: str) -> Any: ...
    async def edit(self, object_guid: str, message_id: str, text: str) -> Any: ...
    async def delete(self, object_guid: str, message_id: str) -> Any: ...
    async def get_message(self, object_guid: str, message_id: str) -> Any: ...


class FastRubikaGateway:
    """Thin adapter. Domain services must not import fast_rub directly."""

    def __init__(self, client: Any):
        self.client = client

    async def get_channel(self, guid: str) -> ChannelSnapshot:
        info = await self.client.get_channel_info(guid)
        data = getattr(info, "raw_data", info)
        return ChannelSnapshot(
            guid=guid,
            title=data.get("channel", {}).get("title") if isinstance(data, dict) else None,
            username=data.get("channel", {}).get("username") if isinstance(data, dict) else None,
            member_count=data.get("channel", {}).get("members_count") if isinstance(data, dict) else None,
        )

    async def forward(self, source_guid: str, target_guid: str, message_id: str) -> Any:
        return await self.client.forward_messages(source_guid, target_guid, [message_id])

    async def edit(self, object_guid: str, message_id: str, text: str) -> Any:
        return await self.client.edit_message(object_guid, message_id, text)

    async def delete(self, object_guid: str, message_id: str) -> Any:
        return await self.client.delete_messages(object_guid, [message_id])

    async def get_message(self, object_guid: str, message_id: str) -> Any:
        return await self.client.get_messages_by_id(object_guid, [message_id])
