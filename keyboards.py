# ============================================================
#  keyboards.py — تمام کیبوردهای ربات تبادل روبیکا
#
#  دو نوع کیبورد:
#  • ChatKeyboard  → کیبورد پایین صفحه (reply keyboard)
#  • InlineKeypad  → دکمه‌های زیر پیام (inline keyboard)
#
#  قوانین طراحی:
#  - پنل‌های اصلی → ChatKeyboard
#  - زیرمنوها، تأییدها، لیست‌ها → InlineKeypad
#  - هر بخش یک دکمه بازگشت دارد
#  - button_id ها یکتا و معنادار هستند
# ============================================================

from rubika_bot_api.keyboards import ChatKeyboardBuilder, InlineKeyboardBuilder
from database import get_text


# ════════════════════════════════════════════════════════════
#  ابزارهای کمکی
# ════════════════════════════════════════════════════════════

def _back_btn(target: str = "main") -> dict:
    """دکمه بازگشت استاندارد."""
    return InlineKeyboardBuilder.button(
        text=get_text("back_btn"),
        button_id=f"back:{target}"
    )


def _confirm_btn(action: str, data: str = "") -> dict:
    return InlineKeyboardBuilder.button(
        text=get_text("confirm_btn"),
        button_id=f"confirm:{action}:{data}"
    )


def _cancel_btn(action: str = "cancel") -> dict:
    return InlineKeyboardBuilder.button(
        text=get_text("cancel_btn"),
        button_id=f"cancel:{action}"
    )


# ════════════════════════════════════════════════════════════
#  پنل مالک — ChatKeyboard (کیبورد پایین)
# ════════════════════════════════════════════════════════════

def owner_main_keyboard() -> dict:
    """کیبورد اصلی پنل مالک."""
    return (
        ChatKeyboardBuilder(resize=True, on_time=False)
        .row("📊 آمار ربات", "👥 مدیریت ادمین‌ها")
        .row("🕐 برنامه کار", "⚙️ کنترل سیستم")
        .row("💰 تعرفه‌ها", "✏️ مدیریت متن‌ها")
        .build()
    )


# ════════════════════════════════════════════════════════════
#  پنل مالک — زیرمنوهای Inline
# ════════════════════════════════════════════════════════════

def owner_stats_keyboard() -> dict:
    """زیرمنوی آمار ربات."""
    return (
        InlineKeyboardBuilder()
        .row(InlineKeyboardBuilder.button(text="📅 آمار امروز",    button_id="stats:today"))
        .row(InlineKeyboardBuilder.button(text="📆 آمار هفته",     button_id="stats:week"))
        .row(InlineKeyboardBuilder.button(text="🗓 آمار ماه",      button_id="stats:month"))
        .row(InlineKeyboardBuilder.button(text="📈 آمار کل",       button_id="stats:all"))
        .row(_back_btn("owner_main"))
        .build()
    )


def owner_admin_manage_keyboard() -> dict:
    """زیرمنوی مدیریت ادمین‌ها."""
    return (
        InlineKeyboardBuilder()
        .row(InlineKeyboardBuilder.button(text="➕ افزودن ادمین",   button_id="admin:add"))
        .row(InlineKeyboardBuilder.button(text="📋 لیست ادمین‌ها",  button_id="admin:list"))
        .row(InlineKeyboardBuilder.button(text="📊 آمار ادمین‌ها",  button_id="admin:stats"))
        .row(_back_btn("owner_main"))
        .build()
    )


def owner_admin_list_keyboard(admins: list) -> dict:
    """
    لیست ادمین‌ها با دکمه مدیریت هر کدام.
    admins: لیست رکوردهای جدول admins
    """
    builder = InlineKeyboardBuilder()
    for adm in admins:
        status_icon = "✅" if adm["is_active"] else "⛔"
        builder.row(
            InlineKeyboardBuilder.button(
                text=f"{status_icon} {adm['display_name']} | {adm['min_members']}-{adm['max_members']} عضو",
                button_id=f"admin:manage:{adm['admin_id']}"
            )
        )
    builder.row(_back_btn("admin_manage"))
    return builder.build()


def owner_admin_detail_keyboard(admin_id: str, is_active: bool) -> dict:
    """دکمه‌های مدیریت یک ادمین خاص."""
    toggle_text = "⛔ تعلیق"   if is_active else "✅ فعال‌سازی"
    toggle_id   = "admin:suspend" if is_active else "admin:activate"
    return (
        InlineKeyboardBuilder()
        .row(InlineKeyboardBuilder.button(text="📊 آمار فردی",     button_id=f"admin:personal_stats:{admin_id}"))
        .row(InlineKeyboardBuilder.button(text=toggle_text,          button_id=f"{toggle_id}:{admin_id}"))
        .row(InlineKeyboardBuilder.button(text="🗑 حذف ادمین",      button_id=f"admin:remove:{admin_id}"))
        .row(_back_btn("admin:list"))
        .build()
    )


def owner_confirm_remove_admin_keyboard(admin_id: str) -> dict:
    """تأیید حذف ادمین."""
    return (
        InlineKeyboardBuilder()
        .row(
            InlineKeyboardBuilder.button(text="✅ بله، حذف شود", button_id=f"confirm:admin_remove:{admin_id}"),
            InlineKeyboardBuilder.button(text="❌ خیر",           button_id=f"back:admin:manage:{admin_id}")
        )
        .build()
    )


def owner_shift_keyboard(admins: list) -> dict:
    """مدیریت شیفت کاری ادمین‌ها."""
    builder = InlineKeyboardBuilder()
    for adm in admins:
        builder.row(
            InlineKeyboardBuilder.button(
                text=f"🕐 {adm['display_name']} — شیفت: {adm['shift']}",
                button_id=f"shift:edit:{adm['admin_id']}"
            )
        )
    builder.row(_back_btn("owner_main"))
    return builder.build()


def owner_shift_select_keyboard(admin_id: str) -> dict:
    """انتخاب شیفت برای یک ادمین."""
    return (
        InlineKeyboardBuilder()
        .row(InlineKeyboardBuilder.button(text="🌅 صبح",      button_id=f"shift:set:morning:{admin_id}"))
        .row(InlineKeyboardBuilder.button(text="🌇 عصر",      button_id=f"shift:set:afternoon:{admin_id}"))
        .row(InlineKeyboardBuilder.button(text="🌙 شب",       button_id=f"shift:set:night:{admin_id}"))
        .row(InlineKeyboardBuilder.button(text="⏰ تمام وقت", button_id=f"shift:set:fulltime:{admin_id}"))
        .row(_back_btn("shift"))
        .build()
    )


def owner_system_keyboard() -> dict:
    """زیرمنوی کنترل سیستم."""
    return (
        InlineKeyboardBuilder()
        .row(InlineKeyboardBuilder.button(text="🔴 خاموش کردن ربات",  button_id="sys:toggle_bot"))
        .row(InlineKeyboardBuilder.button(text="📢 پیام همگانی",       button_id="sys:broadcast"))
        .row(InlineKeyboardBuilder.button(text="🔒 جوین اجباری",       button_id="sys:force_join"))
        .row(InlineKeyboardBuilder.button(text="⛔ بلاک کاربر",        button_id="sys:block_user"))
        .row(InlineKeyboardBuilder.button(text="✅ آنبلاک کاربر",      button_id="sys:unblock_user"))
        .row(InlineKeyboardBuilder.button(text="📋 لاگ سیستم",         button_id="sys:logs"))
        .row(_back_btn("owner_main"))
        .build()
    )


def owner_force_join_keyboard(channels: list, is_active: bool) -> dict:
    """مدیریت جوین اجباری."""
    builder = InlineKeyboardBuilder()
    status_text = "🔴 غیرفعال‌کردن" if is_active else "🟢 فعال‌کردن"
    builder.row(
        InlineKeyboardBuilder.button(text=status_text, button_id="fj:toggle")
    )
    builder.row(
        InlineKeyboardBuilder.button(text="➕ افزودن کانال", button_id="fj:add")
    )
    for ch in channels:
        builder.row(
            InlineKeyboardBuilder.button(
                text=f"🗑 {ch['channel_title'] or ch['channel_username']}",
                button_id=f"fj:remove:{ch['id']}"
            )
        )
    builder.row(_back_btn("sys"))
    return builder.build()


def owner_broadcast_target_keyboard() -> dict:
    """هدف پیام همگانی."""
    return (
        InlineKeyboardBuilder()
        .row(InlineKeyboardBuilder.button(text="👥 همه کاربران",  button_id="bc:target:users"))
        .row(InlineKeyboardBuilder.button(text="🛡 همه ادمین‌ها", button_id="bc:target:admins"))
        .row(InlineKeyboardBuilder.button(text="🌐 همه",          button_id="bc:target:all"))
        .row(_back_btn("sys"))
        .build()
    )


def owner_tariff_keyboard(tariffs: list) -> dict:
    """لیست تعرفه‌ها."""
    builder = InlineKeyboardBuilder()
    for t in tariffs:
        status = "✅" if t["is_active"] else "❌"
        builder.row(
            InlineKeyboardBuilder.button(
                text=f"{status} {t['label']} | {t['min_members']}-{t['max_members']} عضو | {t['price']:,} تومان",
                button_id=f"tariff:edit:{t['id']}"
            )
        )
    builder.row(InlineKeyboardBuilder.button(text="➕ تعرفه جدید", button_id="tariff:add"))
    builder.row(_back_btn("owner_main"))
    return builder.build()


def owner_tariff_detail_keyboard(tariff_id: int, is_active: bool) -> dict:
    toggle_text = "❌ غیرفعال" if is_active else "✅ فعال"
    return (
        InlineKeyboardBuilder()
        .row(InlineKeyboardBuilder.button(text="✏️ ویرایش قیمت",  button_id=f"tariff:price:{tariff_id}"))
        .row(InlineKeyboardBuilder.button(text="✏️ ویرایش بازه",  button_id=f"tariff:range:{tariff_id}"))
        .row(InlineKeyboardBuilder.button(text=toggle_text,         button_id=f"tariff:toggle:{tariff_id}"))
        .row(InlineKeyboardBuilder.button(text="🗑 حذف",           button_id=f"tariff:delete:{tariff_id}"))
        .row(_back_btn("tariff"))
        .build()
    )


def owner_texts_category_keyboard() -> dict:
    """دسته‌بندی متن‌ها برای ویرایش."""
    return (
        InlineKeyboardBuilder()
        .row(InlineKeyboardBuilder.button(text="👤 متن‌های کاربر",    button_id="texts:cat:user"))
        .row(InlineKeyboardBuilder.button(text="🛡 متن‌های ادمین",    button_id="texts:cat:admin"))
        .row(InlineKeyboardBuilder.button(text="👑 متن‌های مالک",     button_id="texts:cat:owner"))
        .row(InlineKeyboardBuilder.button(text="⚙️ متن‌های سیستمی",  button_id="texts:cat:system"))
        .row(InlineKeyboardBuilder.button(text="🗂 فرمت بایگانی",     button_id="texts:cat:archive"))
        .row(_back_btn("owner_main"))
        .build()
    )


def owner_texts_list_keyboard(texts: list, category: str) -> dict:
    """لیست متن‌های یک دسته."""
    # نگاشت کلیدها به دسته‌ها
    cat_map = {
        "user":    ["welcome", "user_menu", "reg_ask_link", "reg_ask_members",
                    "reg_ask_views", "reg_ask_topic", "reg_ask_banner",
                    "reg_confirm", "reg_queued", "reg_success", "reg_rejected",
                    "status_check", "no_requests", "profile_text",
                    "referral_link_text", "warning_level1", "warning_level2",
                    "channel_removed"],
        "admin":   ["admin_welcome", "admin_new_request", "admin_join_reminder",
                    "admin_promote_request", "admin_confirmed_notify",
                    "admin_report_prompt", "admin_report_sent",
                    "admin_timeout_warning"],
        "owner":   ["owner_welcome", "owner_promote_msg", "owner_report_received"],
        "system":  ["maintenance_msg", "force_join_msg", "force_join_btn",
                    "blocked_msg", "invalid_input", "back_btn",
                    "confirm_btn", "cancel_btn"],
        "archive": ["archive_caption"],
    }
    keys_in_cat = cat_map.get(category, [])
    text_dict = {t["key"]: t for t in texts}

    builder = InlineKeyboardBuilder()
    for key in keys_in_cat:
        if key in text_dict:
            builder.row(
                InlineKeyboardBuilder.button(
                    text=f"✏️ {text_dict[key]['description'] or key}",
                    button_id=f"texts:edit:{key}"
                )
            )
    builder.row(_back_btn("texts"))
    return builder.build()


def owner_text_edit_keyboard(key: str) -> dict:
    """دکمه‌های ویرایش یک متن خاص."""
    return (
        InlineKeyboardBuilder()
        .row(InlineKeyboardBuilder.button(text="✏️ ویرایش",            button_id=f"texts:do_edit:{key}"))
        .row(InlineKeyboardBuilder.button(text="↩️ بازگشت به پیش‌فرض", button_id=f"texts:reset:{key}"))
        .row(_back_btn("texts:cat"))
        .build()
    )


def owner_confirm_text_reset_keyboard(key: str) -> dict:
    return (
        InlineKeyboardBuilder()
        .row(
            InlineKeyboardBuilder.button(text="✅ بله", button_id=f"confirm:text_reset:{key}"),
            InlineKeyboardBuilder.button(text="❌ خیر", button_id=f"back:texts:edit:{key}")
        )
        .build()
    )


# ════════════════════════════════════════════════════════════
#  پنل ادمین — ChatKeyboard
# ════════════════════════════════════════════════════════════

def owner_admin_add_confirm_keyboard() -> dict:
    """تأیید نهایی افزودن ادمین جدید."""
    return (
        InlineKeyboardBuilder()
        .row(InlineKeyboardBuilder.button(
            text="✅ تأیید و ثبت",
            button_id="confirm:admin_add"
        ))
        .row(_cancel_btn("admin_add"))
        .build()
    )


def admin_main_keyboard() -> dict:
    """کیبورد اصلی پنل ادمین."""
    return (
        ChatKeyboardBuilder(resize=True, on_time=False)
        .row("📋 صف درخواست‌ها", "📊 ادمین‌های برتر")
        .row("📝 گزارش روزانه", "📦 لیست کانال‌هایم")
        .build()
    )


# ════════════════════════════════════════════════════════════
#  پنل ادمین — زیرمنوهای Inline
# ════════════════════════════════════════════════════════════

def admin_queue_keyboard(queue_items: list) -> dict:
    """
    نمایش صف درخواست‌های ادمین.
    اولین آیتم = در حال بررسی، بقیه = در انتظار.
    """
    builder = InlineKeyboardBuilder()
    for i, item in enumerate(queue_items):
        if i == 0:
            prefix = "🔵 در حال بررسی"
        else:
            prefix = f"⏳ انتظار ({i + 1})"
        builder.row(
            InlineKeyboardBuilder.button(
                text=f"{prefix} | {item['channel_link']} | {item['member_count']} عضو",
                button_id=f"queue:view:{item['id']}"
            )
        )
    builder.row(_back_btn("admin_main"))
    return builder.build()


def admin_request_detail_keyboard(channel_id: int, admin_joined: bool,
                                   admin_promoted: bool) -> dict:
    """
    دکمه‌های مدیریت یک درخواست در صف.
    مراحل به ترتیب نمایش داده می‌شوند.
    """
    builder = InlineKeyboardBuilder()

    if not admin_joined:
        builder.row(
            InlineKeyboardBuilder.button(
                text="✅ عضو کانال شدم",
                button_id=f"req:joined:{channel_id}"
            )
        )
    elif not admin_promoted:
        builder.row(
            InlineKeyboardBuilder.button(
                text="⏳ در انتظار ادمین شدن توسط مالک...",
                button_id=f"req:waiting_promote:{channel_id}"
            )
        )
    else:
        builder.row(
            InlineKeyboardBuilder.button(
                text="✅ تأیید نهایی — ارسال به بایگانی",
                button_id=f"req:approve:{channel_id}"
            )
        )

    builder.row(
        InlineKeyboardBuilder.button(
            text="❌ رد درخواست",
            button_id=f"req:reject:{channel_id}"
        )
    )
    builder.row(_back_btn("queue"))
    return builder.build()


def admin_reject_reason_keyboard(channel_id: int) -> dict:
    """انتخاب دلیل رد درخواست."""
    reasons = [
        ("آمار نادرست",        "wrong_stats"),
        ("کانال غیرفعال",      "inactive"),
        ("موضوع نامناسب",      "bad_topic"),
        ("لینک نامعتبر",       "invalid_link"),
        ("سایر",               "other"),
    ]
    builder = InlineKeyboardBuilder()
    for text, reason_id in reasons:
        builder.row(
            InlineKeyboardBuilder.button(
                text=text,
                button_id=f"req:reject_reason:{channel_id}:{reason_id}"
            )
        )
    builder.row(_back_btn(f"queue:view:{channel_id}"))
    return builder.build()


def admin_channel_list_keyboard(channels: list) -> dict:
    """لیست کانال‌های ثبت‌شده توسط ادمین."""
    builder = InlineKeyboardBuilder()
    for ch in channels:
        warn_icon = "⚠️" if ch["warning_count"] > 0 else "✅"
        builder.row(
            InlineKeyboardBuilder.button(
                text=f"{warn_icon} {ch['registration_code']} | {ch['channel_link']} | {ch['member_count']} عضو",
                button_id=f"ch:manage:{ch['id']}"
            )
        )
    builder.row(_back_btn("admin_main"))
    return builder.build()


def admin_channel_detail_keyboard(channel_id: int, warning_count: int) -> dict:
    """مدیریت یک کانال از لیست ادمین."""
    builder = InlineKeyboardBuilder()
    if warning_count == 0:
        builder.row(
            InlineKeyboardBuilder.button(
                text="⚠️ اخطار سطح ۱",
                button_id=f"ch:warn:1:{channel_id}"
            )
        )
    elif warning_count == 1:
        builder.row(
            InlineKeyboardBuilder.button(
                text="🔴 اخطار سطح ۲",
                button_id=f"ch:warn:2:{channel_id}"
            )
        )
    builder.row(
        InlineKeyboardBuilder.button(
            text="🗑 حذف از لیست",
            button_id=f"ch:remove:{channel_id}"
        )
    )
    builder.row(
        InlineKeyboardBuilder.button(
            text="📋 تاریخچه اخطارها",
            button_id=f"ch:warn_history:{channel_id}"
        )
    )
    builder.row(_back_btn("ch:list"))
    return builder.build()


def admin_warning_reason_keyboard(channel_id: int, level: int) -> dict:
    """انتخاب دلیل اخطار."""
    reasons = [
        ("عدم تبادل به موقع",  "no_exchange"),
        ("کاهش آمار",          "stats_drop"),
        ("عدم پاسخگویی",       "no_response"),
        ("نقض قوانین",         "rule_break"),
        ("سایر",               "other"),
    ]
    builder = InlineKeyboardBuilder()
    for text, reason_id in reasons:
        builder.row(
            InlineKeyboardBuilder.button(
                text=text,
                button_id=f"ch:warn_reason:{channel_id}:{level}:{reason_id}"
            )
        )
    builder.row(_back_btn(f"ch:manage:{channel_id}"))
    return builder.build()


def admin_confirm_remove_channel_keyboard(channel_id: int) -> dict:
    """تأیید حذف کانال از لیست."""
    return (
        InlineKeyboardBuilder()
        .row(
            InlineKeyboardBuilder.button(
                text="✅ بله، حذف شود",
                button_id=f"confirm:ch_remove:{channel_id}"
            ),
            InlineKeyboardBuilder.button(
                text="❌ خیر",
                button_id=f"back:ch:manage:{channel_id}"
            )
        )
        .build()
    )


def admin_leaderboard_period_keyboard() -> dict:
    """انتخاب بازه زمانی رنکینگ."""
    return (
        InlineKeyboardBuilder()
        .row(InlineKeyboardBuilder.button(text="📅 امروز",  button_id="lb:today"))
        .row(InlineKeyboardBuilder.button(text="📆 هفته",   button_id="lb:week"))
        .row(InlineKeyboardBuilder.button(text="🗓 ماه",    button_id="lb:month"))
        .row(_back_btn("admin_main"))
        .build()
    )


def admin_report_confirm_keyboard() -> dict:
    """تأیید ارسال گزارش روزانه."""
    return (
        InlineKeyboardBuilder()
        .row(
            _confirm_btn("report"),
            _cancel_btn("report")
        )
        .build()
    )


def owner_report_review_keyboard(report_id: int) -> dict:
    """بررسی گزارش ادمین توسط مالک."""
    return (
        InlineKeyboardBuilder()
        .row(
            InlineKeyboardBuilder.button(
                text="✅ تأیید گزارش",
                button_id=f"report:approve:{report_id}"
            ),
            InlineKeyboardBuilder.button(
                text="❌ رد گزارش",
                button_id=f"report:reject:{report_id}"
            )
        )
        .build()
    )


# ════════════════════════════════════════════════════════════
#  پنل کاربر — ChatKeyboard
# ════════════════════════════════════════════════════════════

def user_main_keyboard() -> dict:
    """کیبورد اصلی پنل کاربر."""
    return (
        ChatKeyboardBuilder(resize=True, on_time=False)
        .row("📦 ثبت کانال", "📊 وضعیت درخواست‌ها")
        .row("👤 پروفایل من", "🔗 لینک معرف")
        .build()
    )


# ════════════════════════════════════════════════════════════
#  پنل کاربر — زیرمنوهای Inline
# ════════════════════════════════════════════════════════════

def user_topic_keyboard(topics: list) -> dict:
    """انتخاب موضوع کانال."""
    builder = InlineKeyboardBuilder()
    for topic in topics:
        builder.row(
            InlineKeyboardBuilder.button(
                text=topic["title"],
                button_id=f"topic:{topic['id']}"
            )
        )
    builder.row(_cancel_btn("reg"))
    return builder.build()


def user_reg_confirm_keyboard(channel_id_temp: str) -> dict:
    """تأیید نهایی ثبت کانال."""
    return (
        InlineKeyboardBuilder()
        .row(
            InlineKeyboardBuilder.button(
                text="✅ تأیید و ارسال",
                button_id=f"reg:confirm:{channel_id_temp}"
            ),
            InlineKeyboardBuilder.button(
                text="❌ لغو",
                button_id="cancel:reg"
            )
        )
        .build()
    )


def user_requests_keyboard(channels: list) -> dict:
    """وضعیت درخواست‌های کاربر."""
    status_icons = {
        "pending":       "🟡",
        "admin_joined":  "🔵",
        "waiting_owner": "🔵",
        "confirmed":     "🟢",
        "archived":      "✅",
        "rejected":      "❌",
        "cancelled":     "⛔",
    }
    builder = InlineKeyboardBuilder()
    for ch in channels:
        icon = status_icons.get(ch["status"], "❓")
        # نام ادمین مسئول در دکمه نمایش داده می‌شود
        admin_part = f" | @{ch['admin_username']}" if ch.get("admin_username") else ""
        builder.row(
            InlineKeyboardBuilder.button(
                text=f"{icon} {ch['registration_code']} — {ch['channel_link']}{admin_part}",
                button_id=f"req:status:{ch['id']}"
            )
        )
    builder.row(_back_btn("user_main"))
    return builder.build()


def user_request_detail_keyboard(channel_id: int) -> dict:
    """جزئیات یک درخواست از دید کاربر."""
    return (
        InlineKeyboardBuilder()
        .row(
            InlineKeyboardBuilder.button(
                text="🗑 لغو درخواست",
                button_id=f"req:cancel:{channel_id}"
            )
        )
        .row(_back_btn("req:list"))
        .build()
    )


def user_confirm_cancel_request_keyboard(channel_id: int) -> dict:
    """تأیید لغو درخواست."""
    return (
        InlineKeyboardBuilder()
        .row(
            InlineKeyboardBuilder.button(
                text="✅ بله، لغو شود",
                button_id=f"confirm:req_cancel:{channel_id}"
            ),
            InlineKeyboardBuilder.button(
                text="❌ خیر",
                button_id=f"back:req:status:{channel_id}"
            )
        )
        .build()
    )


# ════════════════════════════════════════════════════════════
#  جوین اجباری
# ════════════════════════════════════════════════════════════

def force_join_keyboard(channels: list) -> dict:
    """
    نمایش کانال‌های اجباری با لینک.
    channels: لیست رکوردهای forced_joins
    """
    builder = InlineKeyboardBuilder()
    for ch in channels:
        builder.row(
            InlineKeyboardBuilder.button(
                text=f"📢 {ch['channel_title'] or ch['channel_username']}",
                button_id=f"fj:open:{ch['channel_username']}"
            )
        )
    builder.row(
        InlineKeyboardBuilder.button(
            text=get_text("force_join_btn"),
            button_id="fj:check"
        )
    )
    return builder.build()


# ════════════════════════════════════════════════════════════
#  ابزار: ساخت پیام تأیید ادمین شدن برای مالک
# ════════════════════════════════════════════════════════════

def owner_promote_confirm_keyboard(channel_id: int) -> dict:
    """دکمه تأیید ادمین شدن توسط مالک."""
    return (
        InlineKeyboardBuilder()
        .row(
            InlineKeyboardBuilder.button(
                text="✅ ادمین کردم",
                button_id=f"promote:done:{channel_id}"
            )
        )
        .build()
    )
