from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fast_rub.button import KeyPad


def first_attr(obj: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return default


def update_user_id(msg: Any) -> str | None:
    # Normal message updates expose the sender on the nested message object.
    # Button updates expose sender_id directly on UpdateButton.
    direct = first_attr(msg, "sender_id", "author_object_guid", "author_guid", "user_guid")
    if direct:
        return str(direct)
    event = first_attr(msg, "new_message", default=msg)
    return first_attr(event, "author_object_guid", "author_guid", "user_guid", "chat_id")


def update_text(msg: Any) -> str:
    event = first_attr(msg, "new_message", default=msg)
    return str(first_attr(event, "text", "message_text", default="") or "").strip()


def button_id(msg: Any) -> str:
    # FastRub UpdateButton has button_id directly. Older/nested update shapes
    # may expose it through aux_data or the nested message object.
    direct = first_attr(msg, "button_id", default=None)
    if direct:
        return str(direct)
    event = first_attr(msg, "new_message", default=msg)
    direct = first_attr(event, "button_id", default=None)
    if direct:
        return str(direct)
    aux = first_attr(event, "aux_data", default=None)
    return str(first_attr(aux, "button_id", default="") or "")


def inline_keyboard(*rows: tuple[tuple[str, str], ...]):
    keypad = KeyPad()
    for row in rows:
        keypad.append(*(keypad.simple(button, label) for button, label in row))
    return keypad.build()


async def reply(msg: Any, text: str, *, inline_keypad: Any = None) -> Any:
    method = getattr(msg, "reply", None)
    if method is not None:
        if inline_keypad is not None:
            return await method(text, inline_keypad=inline_keypad)
        return await method(text)
    method = getattr(msg, "send_text", None)
    if method is not None:
        if inline_keypad is not None:
            return await method(text, inline_keypad=inline_keypad)
        return await method(text)
    raise RuntimeError("FastRub update does not expose reply/send_text")


@dataclass(frozen=True)
class BotContext:
    name: str
    token: str
