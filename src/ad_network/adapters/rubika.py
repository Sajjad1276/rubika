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
    if value is None:
        return None
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return to_dict()
        except Exception:
            pass
    original_data = getattr(value, "original_data", None)
    if original_data is not None:
        return original_data
    raw_data = getattr(value, "raw_data", None)
    return raw_data if raw_data is not None else value


def _mapping(value: Any) -> dict[str, Any]:
    value = _raw(value)
    if isinstance(value, dict):
        return value
    return getattr(value, "__dict__", {}) if value is not None else {}


def _first_int(data: Any, *keys: str) -> int | None:
    data = _mapping(data)
    for key in keys:
        value = data.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _first_value(data: Any, *keys: str) -> Any:
    data = _mapping(data)
    for key in keys:
        if key in data:
            return data[key]
    return None


def _nested_mapping(data: Any, *names: str) -> dict[str, Any]:
    current = _mapping(data)
    for name in names:
        candidate = current.get(name)
        if candidate is None:
            return {}
        current = _mapping(candidate)
    return current


class MaxRubikaGateway:
    """Gateway backed by MAXRubika Messenger 1.12.x."""

    def __init__(self, client: Any):
        self.client = client

    async def get_channel(self, guid: str) -> ChannelSnapshot:
        getter = getattr(self.client, "get_channel_info", None)
        if getter is None:
            getter = getattr(self.client, "get_chat_info", None)
        if getter is None:
            raise RuntimeError("MAXRubika client does not expose channel/chat info")

        data = _raw(await getter(guid))
        chat = _nested_mapping(data, "channel")
        if not chat:
            chat = _nested_mapping(data, "data", "channel")
        if not chat:
            chat = _nested_mapping(data, "data", "chat")
        if not chat:
            chat = _mapping(data)

        return ChannelSnapshot(
            guid=guid,
            title=_first_value(chat, "channel_title", "title", "name"),
            username=_first_value(chat, "username", "user_name"),
            member_count=_first_int(chat, "count_members", "members_count", "member_count", "participants_count"),
        )

    async def verify_channel_access(self, guid: str, user_id: str) -> AccessSnapshot:
        admins_getter = getattr(self.client, "get_channel_admins", None)
        if admins_getter is None:
            admins_getter = getattr(self.client, "get_admin_members", None)
        if admins_getter is None:
            admins_getter = getattr(self.client, "get_channel_admin_members", None)
        if admins_getter is None:
            raise RuntimeError("MAXRubika client does not expose channel admin listing")

        raw = _raw(await admins_getter(guid))
        payload = _mapping(raw)
        members = payload.get("admins") or payload.get("in_chat_members") or payload.get("members") or []

        target = None
        for member in members:
            item = _mapping(member)
            candidate = str(
                _first_value(item, "member_guid", "user_guid", "user_id", "guid", "id") or ""
            )
            if candidate == str(user_id):
                target = item
                break

        if target is None:
            return AccessSnapshot(user_id=user_id, is_admin=False, can_send=False, can_edit=False, can_delete=False, raw=raw)

        permissions = target.get("permissions") or target.get("access_list") or []
        access = None
        access_getter = getattr(self.client, "get_channel_admin_access", None)
        if access_getter is None:
            access_getter = getattr(self.client, "get_admin_access_list", None)
        if access_getter is not None:
            access = _raw(await access_getter(guid, user_id))
            access_payload = _mapping(access)
            permissions = access_payload.get("access_list") or access_payload.get("permissions") or permissions

        if isinstance(permissions, dict):
            permissions = [key for key, value in permissions.items() if value]
        permissions = {str(permission).replace("_", "").replace(" ", "").lower() for permission in permissions}

        send_names = {"send", "write", "post", "sendmessages", "sendmessage"}
        edit_names = {"edit", "editmessage", "editmessages", "posteditdeletemessage"}
        delete_names = {"delete", "deletemessage", "deletemessages", "posteditdeletemessage"}
        can_send = bool(send_names & permissions)
        can_edit = bool(edit_names & permissions)
        can_delete = bool(delete_names & permissions)
        join_type = str(target.get("join_type", "")).lower()
        is_admin = join_type in {"admin", "creator"} or bool(target)

        return AccessSnapshot(
            user_id=user_id,
            is_admin=is_admin,
            can_send=can_send,
            can_edit=can_edit,
            can_delete=can_delete,
            raw={"member": target, "access": access},
        )

    async def forward(self, source_guid: str, target_guid: str, message_id: str) -> Any:
        return await self.client.forward_messages(source_guid, [message_id], target_guid)

    async def edit(self, object_guid: str, message_id: str, text: str) -> Any:
        return await self.client.edit_message(object_guid, message_id, text)

    async def delete(self, object_guid: str, message_id: str) -> Any:
        return await self.client.delete_messages(object_guid, [message_id])

    async def get_message(self, object_guid: str, message_id: str) -> Any:
        return await self.client.get_messages_by_id(object_guid, [message_id])


# Compatibility alias for internal imports from earlier versions.
FastRubikaGateway = MaxRubikaGateway
