from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ..core.roles import remember_username

_SEEN_UPDATES: dict[str, float] = {}
_DEDUP_WINDOW_SECONDS = 30.0


def first_attr(obj: Any, *names: str, default: Any = None) -> Any:
    if obj is None:
        return default
    for name in names:
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return default


def update_key(event: Any) -> str | None:
    update_id = first_attr(event, "update_id", "id", default=None)
    if update_id is not None:
        return f"update:{update_id}"
    message_id = first_attr(event, "message_id", "message_id_string", default=None)
    author_id = first_attr(event, "author_id", "sender_id", "author_guid", default=None)
    if message_id is not None:
        return f"message:{author_id or '-'}:{message_id}"
    button = first_attr(event, "button_id", default=None)
    if button:
        chat_id = first_attr(event, "chat_id", default=None)
        return f"button:{chat_id or author_id or '-'}:{button}"
    return None


def is_duplicate_update(event: Any) -> bool:
    key = update_key(event)
    if key is None:
        return False
    now = time.monotonic()
    for item, seen_at in list(_SEEN_UPDATES.items()):
        if now - seen_at > _DEDUP_WINDOW_SECONDS:
            _SEEN_UPDATES.pop(item, None)
    if key in _SEEN_UPDATES:
        return True
    _SEEN_UPDATES[key] = now
    return False


def update_user_id(event: Any) -> str | None:
    user_id = first_attr(event, "author_id", "sender_id", "author_guid", "user_guid", default=None)
    if user_id:
        username = first_attr(event, "username", "author_username", "sender_username", default=None)
        if username:
            remember_username(str(user_id), str(username))
        return str(user_id)
    return None


async def resolve_user(bot: Any, event: Any) -> str | None:
    user_id = update_user_id(event) or first_attr(event, "chat_id", default=None)
    if not user_id:
        return None
    username = first_attr(event, "username", "author_username", "sender_username", default=None)
    if not username:
        chat_id = first_attr(event, "chat_id", default=user_id)
        try:
            info = await bot.get_chat_info(chat_id)
            data = first_attr(info, "data", default=None)
            chat = first_attr(data, "chat", default=None)
            username = first_attr(chat, "username", "user_name", default=None)
        except Exception:
            username = None
    if username:
        remember_username(str(user_id), str(username))
    return str(user_id)


def update_text(event: Any) -> str:
    return str(first_attr(event, "text", "message_text", default="") or "").strip()


def button_id(event: Any) -> str:
    return str(first_attr(event, "button_id", default="") or "")


def _add_back_row(rows: tuple[tuple[tuple[str, str], ...], ...]) -> tuple[tuple[tuple[str, str], ...], ...]:
    if any(button in {"home", "back"} or label == "↩️ بازگشت" for row in rows for button, label in row):
        return rows
    return (*rows, (("home", "↩️ بازگشت"),))


def _keyboard(rows: tuple[tuple[tuple[str, str], ...], ...]) -> dict[str, Any]:
    return {
        "rows": [
            {"buttons": [{"id": button, "type": "Simple", "button_text": label} for button, label in row]}
            for row in rows
        ]
    }


def inline_keyboard(*rows: tuple[tuple[str, str], ...]) -> dict[str, Any]:
    return _keyboard(_add_back_row(rows))


def quick_keyboard(*rows: tuple[tuple[str, str], ...]) -> dict[str, Any]:
    return _keyboard(_add_back_row(rows))


async def reply(event: Any, text: str, *, inline_keypad: Any = None, keypad: Any = None) -> Any:
    kwargs: dict[str, Any] = {}
    if inline_keypad is not None:
        kwargs["inline_keypad"] = inline_keypad
    if keypad is not None:
        kwargs["chat_keypad"] = keypad
        kwargs["resize_keyboard"] = True
    method = getattr(event, "reply", None)
    if method is None:
        raise RuntimeError("MAXRubika event does not expose reply()")
    return await method(text, **kwargs)


@dataclass(frozen=True)
class BotContext:
    name: str
    token: str
