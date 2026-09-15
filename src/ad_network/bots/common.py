from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ..core.roles import remember_username

_SEEN_UPDATES: dict[str, float] = {}
_DEDUP_WINDOW_SECONDS = 30.0


def first_attr(obj: Any, *names: str, default: Any = None) -> Any:
    """Read the first available attribute from SDK objects."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        for name in names:
            value = obj.get(name)
            if value is not None:
                return value
        return default
    for name in names:
        try:
            value = getattr(obj, name, None)
        except Exception:
            value = None
        if value is not None:
            return value
    return default


def _aux_attr(event: Any, *names: str, default: Any = None) -> Any:
    aux = first_attr(event, "aux_data", default=None)
    if aux is None:
        raw = first_attr(event, "raw_data", default=None)
        aux = first_attr(raw, "aux_data", "auxData", default=None)
    return first_attr(aux, *names, default=default)


def button_id(event: Any) -> str:
    value = first_attr(event, "button_id", "callback_button_id", default=None)
    if value is None:
        value = _aux_attr(event, "button_id", "callback_button_id", default=None)
    return str(value or "")


def update_key(event: Any) -> str | None:
    """Return a stable update identity without treating repeated button clicks as duplicates."""
    update_id = first_attr(event, "update_id", "id", default=None)
    if update_id is not None:
        return f"update:{update_id}"

    message_id = first_attr(event, "message_id", "msg_id", "message_id_string", default=None)
    author_id = first_attr(event, "author_id", "user_guid", "sender_id", "author_guid", default=None)
    if message_id is not None:
        return f"message:{author_id or '-'}:{message_id}"

    # A callback without an update/message id has no safe idempotency key.
    # Never deduplicate it solely by button id because two legitimate clicks
    # on the same button must remain independent.
    return None


def is_duplicate_update(event: Any) -> bool:
    key = update_key(event)
    if key is None:
        return False
    now = time.monotonic()
    expired = [item for item, seen_at in _SEEN_UPDATES.items() if now - seen_at > _DEDUP_WINDOW_SECONDS]
    for item in expired:
        _SEEN_UPDATES.pop(item, None)
    if key in _SEEN_UPDATES:
        return True
    _SEEN_UPDATES[key] = now
    return False


def update_user_id(event: Any) -> str | None:
    user_id = first_attr(event, "author_id", "user_guid", "sender_id", "author_guid", default=None)
    if user_id:
        username = first_attr(event, "username", "author_username", "sender_username", default=None)
        if username:
            remember_username(str(user_id), str(username))
        return str(user_id)
    return None


async def resolve_user(bot: Any, event: Any) -> str | None:
    user_id = update_user_id(event) or first_attr(
        event, "chat_id", "chat_guid", "object_guid", default=None
    )
    if not user_id:
        return None

    username = first_attr(event, "username", "author_username", "sender_username", default=None)
    if not username and str(user_id).startswith("u0"):
        get_user_info = getattr(bot, "get_user_info", None)
        if callable(get_user_info):
            try:
                info = await get_user_info(str(user_id))
                data = first_attr(info, "data", default=None)
                user = first_attr(data, "user", default=None)
                username = first_attr(user, "username", "user_name", default=None)
                username = username or first_attr(info, "username", "user_name", default=None)
            except Exception:
                username = None

    if not username:
        get_chat_info = getattr(bot, "get_chat_info", None)
        if callable(get_chat_info):
            try:
                chat_id = first_attr(event, "chat_id", "chat_guid", "object_guid", default=user_id)
                info = await get_chat_info(chat_id)
                data = first_attr(info, "data", default=None)
                chat = first_attr(data, "chat", default=None)
                username = first_attr(chat, "username", "user_name", default=None)
            except Exception:
                username = None

    if username:
        remember_username(str(user_id), str(username))
    return str(user_id)


def update_type(event: Any) -> str:
    return str(first_attr(event, "update_type", "type", default="") or "")


def update_text(event: Any) -> str:
    return str(first_attr(event, "text", "message_text", default="") or "").strip()


def _add_back_row(
    rows: tuple[tuple[tuple[str, str], ...], ...],
) -> tuple[tuple[tuple[str, str], ...], ...]:
    has_navigation = any(
        button in {"back", "home"} or label in {"↩️ بازگشت", "🔙 بازگشت"}
        for row in rows
        for button, label in row
    )
    return rows if has_navigation else (*rows, (("back", "🔙 بازگشت"),))


def _keyboard(
    rows: tuple[tuple[tuple[str, str], ...], ...],
    *,
    add_back: bool,
) -> dict[str, Any]:
    final_rows = _add_back_row(rows) if add_back else rows
    return {
        "rows": [
            {
                "buttons": [
                    {"id": button, "type": "Simple", "button_text": label}
                    for button, label in row
                ]
            }
            for row in final_rows
        ]
    }


def inline_keyboard(*rows: tuple[tuple[str, str], ...]) -> dict[str, Any]:
    return _keyboard(rows, add_back=True)


def quick_keyboard(*rows: tuple[tuple[str, str], ...]) -> dict[str, Any]:
    return _keyboard(rows, add_back=False)


async def reply(event: Any, text: str, *, inline_keypad: Any = None, keypad: Any = None) -> Any:
    method = getattr(event, "reply", None)
    if not callable(method):
        raise RuntimeError("MAXRubika event does not expose reply()")

    kwargs: dict[str, Any] = {}
    if inline_keypad is not None:
        kwargs["inline_keypad"] = inline_keypad
    if keypad is not None:
        kwargs["chat_keypad"] = keypad
        kwargs["resize_keyboard"] = True
    return await method(text, **kwargs)


@dataclass(frozen=True)
class BotContext:
    name: str
    bot: Any
