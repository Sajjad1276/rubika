from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ChannelSnapshot:
    guid: str
    title: str | None = None
    username: str | None = None
    member_count: int | None = None


@dataclass(frozen=True)
class AccessSnapshot:
    user_id: str
    is_admin: bool
    can_send: bool
    can_edit: bool
    can_delete: bool
    raw: Any = None


class RubikaGateway(Protocol):
    async def get_channel(self, guid: str) -> ChannelSnapshot: ...
    async def verify_channel_access(self, guid: str, user_id: str) -> AccessSnapshot: ...
    async def forward(self, source_guid: str, target_guid: str, message_id: str) -> Any: ...
    async def edit(self, object_guid: str, message_id: str, text: str) -> Any: ...
    async def delete(self, object_guid: str, message_id: str) -> Any: ...
    async def get_message(self, object_guid: str, message_id: str) -> Any: ...


def _raw(value: Any) -> Any:
    return getattr(value, "raw_data", value)


def _first_int(data: Any, *keys: str) -> int | None:
    if not isinstance(data, dict):
        return None
    for key in keys:
        value = data.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _first_value(data: Any, *keys: str) -> Any:
    if not isinstance(data, dict):
        return None
    for key in keys:
        if key in data:
            return data[key]
    return None


class FastRubikaGateway:
    """Adapter around FastRub's bundled pyrubi user-bot client."""

    def __init__(self, client: Any):
        self.client = client

    async def get_channel(self, guid: str) -> ChannelSnapshot:
        data = _raw(await self.client.get_chat_info(guid))
        chat = data.get("channel", data) if isinstance(data, dict) else {}
        return ChannelSnapshot(
            guid=guid,
            title=_first_value(chat, "title", "name"),
            username=_first_value(chat, "username", "user_name"),
            member_count=_first_int(chat, "members_count", "member_count", "participants_count"),
        )

    async def verify_channel_access(self, guid: str, user_id: str) -> AccessSnapshot:
        admin_response = await self.client.get_admin_members(guid)
        raw = _raw(admin_response)
        members = []
        if isinstance(raw, dict):
            members = raw.get("in_chat_members") or raw.get("members") or raw.get("admins") or []
        elif isinstance(raw, list):
            members = raw

        for member in members:
            item = _raw(member)
            if not isinstance(item, dict):
                continue
            candidate = str(_first_value(item, "member_guid", "user_guid", "user_id", "guid", "id") or "")
            if candidate != str(user_id):
                continue
            access = _raw(await self.client.get_admin_access_list(guid, user_id))
            permissions = []
            if isinstance(access, dict):
                permissions = access.get("access_list") or access.get("permissions") or []
            if isinstance(permissions, dict):
                permissions = [k for k, v in permissions.items() if v]
            permissions = {str(p) for p in permissions}
            return AccessSnapshot(
                user_id=user_id,
                is_admin=True,
                can_send=bool({"send", "write", "post"} & permissions),
                can_edit=bool({"edit", "edit_message", "post_edit_delete_message"} & permissions),
                can_delete=bool({"delete", "delete_message", "post_edit_delete_message"} & permissions),
                raw={"member": item, "access": access},
            )

        return AccessSnapshot(user_id=user_id, is_admin=False, can_send=False, can_edit=False, can_delete=False, raw=raw)

    async def forward(self, source_guid: str, target_guid: str, message_id: str) -> Any:
        return await self.client.forward_messages(source_guid, [message_id], target_guid)

    async def edit(self, object_guid: str, message_id: str, text: str) -> Any:
        return await self.client.edit_message(object_guid, text, message_id)

    async def delete(self, object_guid: str, message_id: str) -> Any:
        return await self.client.delete_messages(object_guid, [message_id])

    async def get_message(self, object_guid: str, message_id: str) -> Any:
        return await self.client.get_messages_by_id(object_guid, [message_id])
