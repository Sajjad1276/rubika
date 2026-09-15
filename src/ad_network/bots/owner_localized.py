from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from . import owner_bot as legacy
from .common import inline_keyboard, quick_keyboard, resolve_user
from ..core.campaigns import Campaign
from ..core.db import SessionFactory
from ..core.models import Channel, ChannelStatus, ListAccount, ListNetwork, UserRole, Violation
from ..core.roles import RoleService

_TRANSLATIONS = {
    "OPEX CONTROL CENTER": "مرکز فرماندهی اوپکس",
    "OPEX LISTS": "مدیریت لیست‌ها",
    "OPEX CHANNELS": "مدیریت کانال‌ها",
    "OPEX FINANCE": "مرکز مالی اوپکس",
    "CAMPAIGNS": "کمپین‌ها",
    "CAMPAIGN": "کمپین",
    "ORDERS": "مرکز سفارش‌ها",
    "ORDER": "سفارش",
    "CHANNEL": "کانال",
    "PERFORMANCE": "عملکرد",
    "REPORT CENTER": "مرکز گزارش‌ها",
    "TASK CENTER": "مرکز وظایف",
    "SECURITY CENTER": "مرکز امنیت",
    "NOTIFICATION CENTER": "مرکز اعلان‌ها",
    "OPEX SETTINGS": "تنظیمات اوپکس",
    "EMERGENCY CENTER": "مرکز عملیات اضطراری",
    "System": "وضعیت سامانه",
    "ACTIVE": "فعال",
    "Lists": "لیست‌ها",
    "Channels": "کانال‌ها",
    "Pending Channels": "کانال‌های در انتظار",
    "Campaigns": "کمپین‌ها",
    "Running Ads": "تبلیغات در حال اجرا",
    "Pending Orders": "سفارش‌های در انتظار",
    "Violations Today": "تخلفات امروز",
    "Revenue Today": "درآمد امروز",
    "Alerts": "هشدارها",
    "PULSE": "پالس",
    "BOOST": "بوست",
    "REACH": "ریچ",
    "VIEW": "بازدید",
    "List": "لیست",
    "LISTS": "لیست‌ها",
    "Username": "نام کاربری",
    "View24h": "بازدید ۲۴ساعت",
    "Target": "هدف",
    "Targets": "هدف‌ها",
    "failed": "ناموفق",
    "scheduled": "زمان‌بندی‌شده",
    "active": "فعال",
    "paused": "متوقف",
    "completed": "تکمیل‌شده",
    "cancelled": "لغوشده",
    "draft": "پیش‌نویس",
    "awaiting_payment": "در انتظار پرداخت",
    "paid": "پرداخت‌شده",
    "running": "در حال پردازش",
    "pending": "در انتظار",
    "confirmed": "تأییدشده",
    "severity": "شدت",
    "Code": "کد",
    "Type": "نوع",
    "Threshold": "حداقل مقدار",
    "Retention": "تعهد",
    "Capacity": "ظرفیت",
    "CREATE": "ایجاد",
    "CONFIRM": "تأیید",
    "CANCEL": "لغو",
    "STOP": "توقف",
    "WORKER": "کارگر",
    "Automation": "خودکارسازی",
    "Audit Log": "ثبت رویدادها",
    "System Health": "سلامت سامانه",
    "12H": "۱۲ ساعت",
    "6H": "۶ ساعت",
    "V24": "بازدید ۲۴ساعت",
    "↩️ بازگشت": "🔙 بازگشت",
}


def _translate(value: str) -> str:
    result = value
    for source, target in _TRANSLATIONS.items():
        result = result.replace(source, target)
    return result


def _clean_keyboard(value: Any) -> Any:
    if isinstance(value, list):
        cleaned = [_clean_keyboard(item) for item in value]
        return [item for item in cleaned if item not in (None, [], {})]
    if isinstance(value, dict):
        result = {key: _clean_keyboard(item) for key, item in value.items()}
        buttons = result.get("buttons")
        if isinstance(buttons, list):
            result["buttons"] = [
                button
                for button in buttons
                if not (isinstance(button, dict) and button.get("id") == "home")
            ]
        if "button_text" in result and isinstance(result["button_text"], str):
            result["button_text"] = _translate(result["button_text"])
        if not result.get("buttons") and "buttons" in result:
            return None
        return result
    if isinstance(value, str):
        return _translate(value)
    return value


def localized_owner_keyboard() -> dict[str, Any]:
    return quick_keyboard(
        (("dashboard", "📊 داشبورد"), ("lists", "🗂 مدیریت لیست‌ها")),
        (("channels", "📺 مدیریت کانال‌ها"), ("campaigns", "📢 تبلیغات و کمپین‌ها")),
        (("orders", "💳 سفارش‌ها"), ("finance", "💰 مالی")),
        (("violations", "⚠️ تخلفات"), ("performance", "📈 عملکرد")),
        (("reports", "📋 گزارش‌ها"), ("tasks", "🧩 وظایف")),
        (("security", "🔐 امنیت و ثبت رویداد"), ("notifications", "🔔 اعلان‌ها")),
        (("settings", "⚙️ تنظیمات"), ("emergency", "🚨 عملیات اضطراری")),
    )


_ORIGINAL_REPLY = legacy.reply


async def localized_reply(
    event: Any,
    text: str,
    *,
    inline_keypad: Any = None,
    keypad: Any = None,
) -> Any:
    return await _ORIGINAL_REPLY(
        event,
        _translate(text),
        inline_keypad=_clean_keyboard(inline_keypad) if inline_keypad is not None else None,
        keypad=_clean_keyboard(keypad) if keypad is not None else None,
    )


# Compatibility boundary: the legacy owner module is still the transport/presentation
# implementation, while this module supplies its Persian presentation adapter.
legacy.reply = localized_reply
legacy.owner_keyboard = localized_owner_keyboard


async def _settings_option(
    event: Any,
    bot: Any,
    settings: Any,
    section: str,
    option: str,
) -> None:
    async with SessionFactory() as db:
        user_id = await resolve_user(bot, event)
        if not user_id:
            return

        roles = RoleService(db, settings)
        user = await roles.get_or_create_user(rubika_user_id=user_id)
        if not roles.has(user, UserRole.OWNER, UserRole.SUPERVISOR):
            await db.rollback()
            await localized_reply(event, "⛔ دسترسی ندارید.")
            return

        if section == "lists" and option == "status":
            total = await db.scalar(select(func.count(ListNetwork.id))) or 0
            active = await db.scalar(
                select(func.count(ListNetwork.id)).where(ListNetwork.active.is_(True))
            ) or 0
            paused = await db.scalar(
                select(func.count(ListNetwork.id)).where(ListNetwork.status == "paused")
            ) or 0
            archived = await db.scalar(
                select(func.count(ListNetwork.id)).where(ListNetwork.status == "archived")
            ) or 0
            text = f"📊 وضعیت لیست‌ها\n━━━━━━━━━━━━━━━━━━━━\nکل: {total}\nفعال: {active}\nمتوقف: {paused}\nآرشیو: {archived}"
        elif section == "lists" and option == "capacity":
            total_capacity = await db.scalar(
                select(func.coalesce(func.sum(ListNetwork.max_channels), 0))
            ) or 0
            active_lists = await db.scalar(
                select(func.count(ListNetwork.id)).where(ListNetwork.active.is_(True))
            ) or 0
            text = f"📦 ظرفیت لیست‌ها\n━━━━━━━━━━━━━━━━━━━━\nظرفیت کل: {total_capacity}\nلیست فعال: {active_lists}\nظرفیت از مدل لیست‌ها محاسبه می‌شود."
        elif section == "ads" and option == "status":
            total = await db.scalar(select(func.count(Campaign.id))) or 0
            running = await db.scalar(
                select(func.count(Campaign.id)).where(Campaign.status == "active")
            ) or 0
            scheduled = await db.scalar(
                select(func.count(Campaign.id)).where(Campaign.status == "scheduled")
            ) or 0
            text = f"📊 وضعیت تبلیغات\n━━━━━━━━━━━━━━━━━━━━\nکل کمپین‌ها: {total}\nدر حال اجرا: {running}\nزمان‌بندی‌شده: {scheduled}"
        elif section == "ads" and option == "execution":
            text = "⚙️ اجرای تبلیغات\n━━━━━━━━━━━━━━━━━━━━\nوضعیت کنترل اجرا: فعال\nکمپین‌های زمان‌بندی‌شده و فعال توسط موتور اجرا مدیریت می‌شوند."
        elif section == "violations" and option == "rules":
            total = await db.scalar(select(func.count(Violation.id))) or 0
            open_count = await db.scalar(
                select(func.count(Violation.id)).where(Violation.resolved.is_(False))
            ) or 0
            text = f"📚 قوانین تخلف\n━━━━━━━━━━━━━━━━━━━━\nکل رخدادها: {total}\nباز: {open_count}\nرسیدگی به تخلف‌های ثبت‌شده در بخش تخلفات انجام می‌شود."
        elif section == "violations" and option == "limits":
            high = await db.scalar(
                select(func.count(Violation.id)).where(
                    Violation.severity >= 3,
                    Violation.resolved.is_(False),
                )
            ) or 0
            text = f"🚦 محدودیت‌ها\n━━━━━━━━━━━━━━━━━━━━\nموارد پرخطر باز: {high}\nموارد با شدت ۳ یا بیشتر نیازمند بررسی هستند."
        elif section == "finance" and option == "pricing":
            from ..core.commerce import PriceRule

            active = await db.scalar(
                select(func.count(PriceRule.id)).where(PriceRule.active.is_(True))
            ) or 0
            text = f"💵 تعرفه‌ها\n━━━━━━━━━━━━━━━━━━━━\nتعرفه فعال: {active}\nمدیریت جزئیات تعرفه از مرکز مالی انجام می‌شود."
        elif section == "finance" and option == "payments":
            from ..core.commerce import Payment

            pending = await db.scalar(
                select(func.count(Payment.id)).where(Payment.status == "pending")
            ) or 0
            confirmed = await db.scalar(
                select(func.count(Payment.id)).where(Payment.status == "confirmed")
            ) or 0
            text = f"💳 پرداخت‌ها\n━━━━━━━━━━━━━━━━━━━━\nدر انتظار: {pending}\nتأییدشده: {confirmed}"
        elif section == "automation" and option == "sync":
            text = "🔄 همگام‌سازی\n━━━━━━━━━━━━━━━━━━━━\nوضعیت: فعال\nهمگام‌سازی دوره‌ای اکانت‌ها و داده‌های عملیاتی طبق تنظیمات سامانه انجام می‌شود."
        elif section == "automation" and option == "checks":
            text = "🔎 بررسی خودکار\n━━━━━━━━━━━━━━━━━━━━\nوضعیت: فعال\nبررسی شرایط لیست‌ها، کانال‌ها و تخلفات در جریان است."
        elif section == "system" and option == "health":
            active_channels = await db.scalar(
                select(func.count(Channel.id)).where(Channel.status == ChannelStatus.ACTIVE)
            ) or 0
            pending_channels = await db.scalar(
                select(func.count(Channel.id)).where(Channel.status == ChannelStatus.PENDING)
            ) or 0
            text = f"❤️ سلامت سامانه\n━━━━━━━━━━━━━━━━━━━━\nوضعیت: فعال\nکانال فعال: {active_channels}\nکانال در انتظار: {pending_channels}"
        elif section == "system" and option == "accounts":
            accounts = await db.scalar(
                select(func.count(ListAccount.id)).where(ListAccount.active.is_(True))
            ) or 0
            text = f"👤 اکانت‌ها\n━━━━━━━━━━━━━━━━━━━━\nاکانت فعال: {accounts}\nوضعیت اتصال اکانت‌ها از چرخه عملیاتی سامانه کنترل می‌شود."
        else:
            await db.rollback()
            await localized_reply(
                event,
                "❌ گزینه تنظیمات شناخته نشد.",
                inline_keypad=inline_keyboard(((f"settings:{section}", "🔙 بازگشت"),)),
            )
            return

        await db.commit()
        await localized_reply(
            event,
            text,
            inline_keypad=inline_keyboard(((f"settings:{section}", "🔙 بازگشت"),)),
        )


async def build_owner_bot(settings):
    """Compatibility factory; callback routing is owned by the composition root."""
    return await legacy.build_owner_bot(settings)
