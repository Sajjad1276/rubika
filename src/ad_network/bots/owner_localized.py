from __future__ import annotations

from typing import Any

from . import owner_bot as legacy
from .common import quick_keyboard


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
    "System": "وضعیت سیستم",
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
                button for button in buttons
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


def localized_owner_keyboard():
    return quick_keyboard(
        (("dashboard", "📊 داشبورد"), ("lists", "🗂 مدیریت لیست‌ها")),
        (("channels", "📺 مدیریت کانال‌ها"), ("campaigns", "📢 تبلیغات و کمپین‌ها")),
        (("orders", "💳 سفارش‌ها"), ("finance", "💰 مالی")),
        (("violations", "⚠️ تخلفات"), ("performance", "📈 عملکرد")),
        (("reports", "📋 گزارش‌ها"), ("tasks", "🧩 وظایف")),
        (("security", "🔐 امنیت و ثبت رویداد"), ("notifications", "🔔 اعلان‌ها")),
        (("settings", "⚙️ تنظیمات"), ("emergency", "🚨 عملیات اضطراری")),
    )


_ORIGINAL_REPLY = getattr(legacy, "reply")


async def localized_reply(event: Any, text: str, *, inline_keypad: Any = None, keypad: Any = None) -> Any:
    return await _ORIGINAL_REPLY(
        event,
        _translate(text),
        inline_keypad=_clean_keyboard(inline_keypad) if inline_keypad is not None else None,
        keypad=_clean_keyboard(keypad) if keypad is not None else None,
    )


legacy.reply = localized_reply
legacy.owner_keyboard = localized_owner_keyboard


async def build_owner_bot(settings):
    return await legacy.build_owner_bot(settings)
