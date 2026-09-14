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


class MaxRubikaGateway:
    """Gateway backed by MAXRubika Messenger."""

    def __init__(self, client: Any):
        self.client = client

    async def get_channel(self, guid: str) -> ChannelSnapshot:
        getter = getattr(self.client, "get_chat_info", None) or getattr(self.client, "get_channel_info")
        data = _raw(await getter(guid))
        chat = data.get("channel", data) if isinstance(data, dict) else getattr(data, "channel", data)
        raw_chat = _raw(chat)
        if not isinstance(raw_chat, dict):
            raw_chat = getattr(chat, "__dict__", {})
        return ChannelSnapshot(
            guid=guid,
            title=_first_value(raw_chat, "title", "name", "channel_title") or getattr(chat, "title", None),
            username=_first_value(raw_chat, "username", "user_name") or getattr(chat, "username", None),
            member_count=_first_int(raw_chat, "members_count", "member_count", "participants_count"),
        )

    async def verify_channel_access(self, guid: str, user_id: str) -> AccessSnapshot:
        getter = getattr(self.client, "get_admin_members", None) or getattr(self.client, "get_channel_admin_members")
        raw = _raw(await getter(guid))
        members = []
        if isinstance(raw, dict):
            members = raw.get("in_chat_members") or raw.get("members") or raw.get("admins") or []
        elif isinstance(raw, list):
            members = raw

        for member in members:
            item = _raw(member)
            if not isinstance(item, dict):
                item = getattr(member, "__dict__", {})
            candidate = str(_first_value(item, "member_guid", "user_guid", "user_id", "guid", "id") or "")
            if candidate != str(user_id):
                continue
            permissions = item.get("permissions") or []
            if not permissions:
                access_getter = getattr(self.client, "get_admin_access_list", None)
                if access_getter is not None:
                    access = _raw(await access_getter(guid, user_id))
                    if isinstance(access, dict):
                        permissions = access.get("access_list") or access.get("permissions") or []
                else:
                    access = None
            else:
                access = None
            if isinstance(permissions, dict):
                permissions = [key for key, value in permissions.items() if value]
            permissions = {str(permission) for permission in permissions}
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


FastRubikaGateway = MaxRubikaGateway
