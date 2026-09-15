from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from ..core.db import SessionFactory
from ..core.models import Channel, ChannelStatus, ListNetwork, UserRole
from ..core.roles import RoleService
from .common import inline_keyboard, reply, resolve_user


LIST_GRID = {
    "12h": ("pulse", (100, 300, 500, 700)),
    "6h": ("boost", (1000, 2000, 3000, 4000, 5000)),
    "view": ("reach", (50, 100, 200, 300, 500, 600)),
}


async def _authorized(bot: Any, event: Any, settings: Any, db: Any) -> bool:
    user_id = await resolve_user(bot, event)
    if not user_id:
        return False
    roles = RoleService(db, settings)
    user = await roles.get_or_create_user(rubika_user_id=user_id)
    return roles.has(user, UserRole.OWNER, UserRole.SUPERVISOR)


def _back() -> tuple[tuple[str, str], ...]:
    return (("lists", "🔙 بازگشت"),)


def _header(text: str, callback: str) -> tuple[tuple[str, str], ...]:
    return ((callback, text),)


def list_management_keyboard() -> dict[str, Any]:
    rows: list[tuple[tuple[str, str], ...]] = []
    for family, callback in (("12H", "lists:header:12h"), ("6H", "lists:header:6h"), ("VIEW", "lists:header:view")):
        rows.append(_header(family, callback)[0])
        kind_key = callback.rsplit(":", 1)[1]
        _, thresholds = LIST_GRID[kind_key]
        buttons = [
            (f"lists:{kind_key}:{threshold}", _label(kind_key, threshold))
            for threshold in thresholds
        ]
        rows.extend(tuple(buttons[i : i + 2]) for i in range(0, len(buttons), 2))
    rows.append(_back())
    return inline_keyboard(*rows)


def _label(kind: str, threshold: int) -> str:
    if kind == "6h":
        return f"{threshold // 1000}K"
    return f"{threshold}V" if kind == "view" else str(threshold)


async def handle_owner_list_grid(event: Any, bot: Any, settings: Any, value: str) -> bool:
    if value == "lists":
        async with SessionFactory() as db:
            if not await _authorized(bot, event, settings, db):
                await db.rollback()
                await reply(event, "⛔ دسترسی ندارید.")
                return True
            await db.commit()
            await reply(
                event,
                "🗂 مدیریت لیست‌ها\n━━━━━━━━━━━━━━━━━━━━\nنوع لیست را انتخاب کنید:",
                inline_keypad=list_management_keyboard(),
            )
        return True

    if value.startswith("lists:header:"):
        return True

    parts = value.split(":")
    if len(parts) != 3 or parts[0] != "lists" or parts[1] not in LIST_GRID:
        return False
    try:
        threshold = int(parts[2])
    except ValueError:
        return False

    kind, thresholds = LIST_GRID[parts[1]]
    if threshold not in thresholds:
        return False

    async with SessionFactory() as db:
        if not await _authorized(bot, event, settings, db):
            await db.rollback()
            await reply(event, "⛔ دسترسی ندارید.")
            return True

        if kind == "reach":
            condition = ListNetwork.required_views == threshold
        else:
            condition = ListNetwork.min_stat == threshold

        items = (
            await db.scalars(
                select(ListNetwork)
                .where(ListNetwork.list_type == kind, condition)
                .order_by(ListNetwork.code)
                .limit(50)
            )
        ).all()

        lines = []
        buttons = []
        for item in items:
            channel_count = await db.scalar(
                select(func.count(Channel.id)).where(
                    Channel.list_id == item.id,
                    Channel.status == ChannelStatus.ACTIVE,
                )
            )
            lines.append(
                f"{item.code} | {item.name} | {channel_count or 0}/{item.max_channels}"
            )
            buttons.append((f"list:{item.id}", item.code))

        title = _label(parts[1], threshold)
        await db.commit()
        await reply(
            event,
            f"🗂 لیست‌های {title}\n━━━━━━━━━━━━━━━━━━━━\n"
            + ("\n".join(lines) or "لیستی برای این ظرفیت وجود ندارد."),
            inline_keypad=inline_keyboard(
                *[tuple(buttons[i : i + 2]) for i in range(0, len(buttons), 2)],
                _back(),
            ),
        )
    return True
