from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fast_rub.button import KeyPad

from ..core.roles import remember_username


def first_attr(obj: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return default


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
    return str(first_attr(event, "text", "message_text", default="") or "").strip()


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


def _build_keyboard(rows: tuple[tuple[str, str], ...], *, callback: bool) -> Any:
    keypad = KeyPad()
    for row in rows:
        keypad.append(*(keypad.simple(button, label) for button, label in row))
    return keypad.build()


def inline_keyboard(*rows: tuple[tuple[str, str], ...]):
    return _build_keyboard(rows, callback=True)


def quick_keyboard(*rows: tuple[tuple[str, str], ...]):
    """Build a normal Rubika reply/chat keyboard (not inline)."""
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
