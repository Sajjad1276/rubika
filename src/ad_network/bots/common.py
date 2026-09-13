from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def first_attr(obj: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return default


def update_user_id(msg: Any) -> str | None:
    event = first_attr(msg, "new_message", default=msg)
    return first_attr(
        event,
        "author_object_guid",
        "author_guid",
        "user_guid",
        "chat_id",
    )


def update_text(msg: Any) -> str:
    event = first_attr(msg, "new_message", default=msg)
    return str(first_attr(event, "text", "message_text", default="") or "").strip()


async def reply(msg: Any, text: str) -> Any:
    method = getattr(msg, "reply", None)
    if method is not None:
        return await method(text)
    method = getattr(msg, "send_text", None)
    if method is not None:
        return await method(text)
    raise RuntimeError("FastRub update does not expose reply/send_text")


@dataclass(frozen=True)
class BotContext:
    name: str
    token: str
