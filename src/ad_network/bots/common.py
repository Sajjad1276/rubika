from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fast_rub.button import KeyPad

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


def update_key(msg: Any) -> str | None:
    event = first_attr(msg, "new_message", default=msg)
    update_id = first_attr(msg, "update_id", "id", default=None)
    if update_id is not None:
        return f"update:{update_id}"
    message_id = first_attr(msg, "message_id", default=None)
    if message_id is None:
        message_id = first_attr(event, "message_id", default=None)
    sender_id = first_attr(msg, "sender_id", default=None) or first_attr(
        event, "author_object_guid", "author_guid", "user_guid", default=None
    )
    if message_id is not None:
        return f"message:{sender_id or '-'}:{message_id}"
    button = first_attr(msg, "button_id", default=None)
    if button:
        chat_id = first_attr(msg, "chat_id", default=None)
        return f"button:{chat_id or sender_id or '-'}:{button}:{message_id or '-'}"
    return None


def is_duplicate_update(msg: Any) -> bool:
    """Suppress the same FastRub event when polling delivers it more than once."""
    import time

    key = update_key(msg)
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


def update_user_id(msg: Any) -> str | None:
    direct = first_attr(msg, "sender_id", "author_object_guid", "author_guid", "user_guid")
    event = first_attr(msg, "new_message", default=msg)
    user_id = direct or first_attr(event, "author_object_guid", "author_guid", "user_guid", "chat_id")
    if user_id:
        username = first_attr(
            msg,
            "sender_username", "author_username", "username",
            default=first_attr(event, "sender_username", "author_username", "username"),
        )
        if username:
            remember_username(str(user_id), str(username))
        return str(user_id)
    return None


def update_text(msg: Any) -> str:
    event = first_attr(msg, "new_message", default=msg)
    text = str(first_attr(event, "text", "message_text", default="") or "").strip()
    return "/start" if text == "↩️ بازگشت" else text


def button_id(msg: Any) -> str:
    direct = first_attr(msg, "button_id", default=None)
    if direct:
        return str(direct)
    event = first_attr(msg, "new_message", default=msg)
    direct = first_attr(event, "button_id", default=None)
    if direct:
        return str(direct)
    aux = first_attr(event, "aux_data", default=None)
    return str(first_attr(aux, "button_id", default="") or "")


def _add_back_row(rows: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    if any(button in {"home", "back"} or label == "↩️ بازگشت" for row in rows for button, label in row):
        return rows
    return (*rows, (("home", "↩️ بازگشت"),))


def _build_keyboard(rows: tuple[tuple[str, str], ...], *, callback: bool) -> Any:
    rows = _add_back_row(rows)
    keypad = KeyPad()
    for row in rows:
        keypad.append(*(keypad.simple(button, label) for button, label in row))
    return keypad.build()


def inline_keyboard(*rows: tuple[tuple[str, str], ...]):
    return _build_keyboard(rows, callback=True)


def quick_keyboard(*rows: tuple[tuple[str, str], ...]):
    return _build_keyboard(rows, callback=False)


async def reply(msg: Any, text: str, *, inline_keypad: Any = None, keypad: Any = None) -> Any:
    method = getattr(msg, "reply", None)
    if method is None:
        method = getattr(msg, "send_text", None)
    if method is None:
        raise RuntimeError("FastRub update does not expose reply/send_text")
    kwargs = {}
    if inline_keypad is not None:
        kwargs["inline_keypad"] = inline_keypad
    if keypad is not None:
        kwargs["keypad"] = keypad
    return await method(text, **kwargs)


@dataclass(frozen=True)
class BotContext:
    name: str
    token: str
