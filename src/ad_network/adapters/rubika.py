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
    """Rubika transport adapter. Business logic never depends on fast_r internals."""

    def __init__(self, client: Any):
        self.client = client

    async def get_channel(self, guid: str) -> ChannelSnapshot:
        info = await self.client.get_channel_info(guid)
        data = _raw(info)
        channel = data.get("channel", data) if isinstance(data, dict) else {}
        return ChannelSnapshot(
            guid=guid,
            title=_first_value(channel, "title", "name"),
            username=_first_value(channel, "username", "user_name"),
            member_count=_first_int(channel, "members_count", "member_count", "participants_count"),
        )

    async def verify_channel_access(self, guid: str, user_id: str) -> AccessSnapshot:
        """Read the actual admin record. Missing API support fails closed."""
        admin_response = None
        for method_name in ("get_channel_admin_members", "get_group_admin_members"):
            method = getattr(self.client, method_name, None)
            if method is not None:
                admin_response = await method(guid)
                break
        if admin_response is None:
            raise RuntimeError("FastRub client does not expose an admin-members API")

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
            permissions = item.get("permissions") or item.get("admin_permissions") or []
            if isinstance(permissions, dict):
                permissions = [key for key, enabled in permissions.items() if enabled]
            permissions = {str(p) for p in permissions}
            can_send = bool(item.get("can_send") or item.get("can_post") or {"send", "write", "post"} & permissions)
            can_edit = bool(item.get("can_edit") or {"edit", "edit_message", "post_edit_delete_message"} & permissions)
            can_delete = bool(item.get("can_delete") or {"delete", "delete_message", "post_edit_delete_message"} & permissions)
            return AccessSnapshot(
                user_id=user_id,
                is_admin=True,
                can_send=can_send,
                can_edit=can_edit,
                can_delete=can_delete,
                raw=item,
            )

        return AccessSnapshot(user_id=user_id, is_admin=False, can_send=False, can_edit=False, can_delete=False, raw=raw)

    async def forward(self, source_guid: str, target_guid: str, message_id: str) -> Any:
        return await self.client.forward_messages(source_guid, target_guid, [message_id])

    async def edit(self, object_guid: str, message_id: str, text: str) -> Any:
        return await self.client.edit_message(object_guid, message_id, text)

    async def delete(self, object_guid: str, message_id: str) -> Any:
        return await self.client.delete_messages(object_guid, [message_id])

    async def get_message(self, object_guid: str, message_id: str) -> Any:
        return await self.client.get_messages_by_id(object_guid, [message_id])
