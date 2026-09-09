# ============================================================
#  keyboards.py — تمام کیبوردهای ربات تبادل روبیکا
#  کتابخانه: fastrub (fast_rub)
# ============================================================

from fast_rub.button import KeyPad
from database import get_text


# ════════════════════════════════════════════════════════════
#  ابزارهای کمکی داخلی
# ════════════════════════════════════════════════════════════

def _btn(text: str, bid: str) -> dict:
    kp = KeyPad()
    return kp.simple(bid, text)


def _back_btn(target: str = "main") -> dict:
    return _btn(get_text("back_btn"), f"back:{target}")


def _confirm_btn(action: str, data: str = "") -> dict:
    return _btn(get_text("confirm_btn"), f"confirm:{action}:{data}")


def _cancel_btn(action: str = "cancel") -> dict:
    return _btn(get_text("cancel_btn"), f"cancel:{action}")


def _build_inline(*rows) -> list:
    """ساخت inline keypad از لیست ردیف‌ها.
    هر ردیف یک list از dict (خروجی _btn) است.
    """
    kp = KeyPad()
    for row in rows:
        if isinstance(row, dict):
            kp.append(row)
        else:
            kp.append(*row)
    return kp.build()


def _build_reply(*rows, resize: bool = True) -> list:
    """ساخت reply keypad از لیست ردیف‌ها.
    هر ردیف یک list از رشته‌های متن است.
    """
    kp = KeyPad()
    for row in rows:
        if isinstance(row, str):
            kp.append(kp.simple(row, row))
        else:
            kp.append(*[kp.simple(t, t) for t in row])
    return kp.build()


# ════════════════════════════════════════════════════════════
#  پنل مالک — Reply Keyboard (کیبورد پایین صفحه)
# ════════════════════════════════════════════════════════════

def owner_main_keyboard() -> list:
    kp = KeyPad()
    kp.append(kp.simple("📊 آمار ربات", "📊 آمار ربات"),
              kp.simple("👥 مدیریت ادمین‌ها", "👥 مدیریت ادمین‌ها"))
    kp.append(kp.simple("🕐 برنامه کار", "🕐 برنامه کار"),
              kp.simple("⚙️ کنترل سیستم", "⚙️ کنترل سیستم"))
    kp.append(kp.simple("💰 تعرفه‌ها", "💰 تعرفه‌ها"),
              kp.simple("✏️ مدیریت متن‌ها", "✏️ مدیریت متن‌ها"))
    return kp.build()


def admin_main_keyboard() -> list:
    kp = KeyPad()
    kp.append(kp.simple("📋 صف درخواست‌ها", "📋 صف درخواست‌ها"),
              kp.simple("📊 ادمین‌های برتر", "📊 ادمین‌های برتر"))
    kp.append(kp.simple("📝 گزارش روزانه", "📝 گزارش روزانه"),
              kp.simple("📦 لیست کانال‌هایم", "📦 لیست کانال‌هایم"))
    return kp.build()


def user_main_keyboard() -> list:
    kp = KeyPad()
    kp.append(kp.simple("📦 ثبت کانال", "📦 ثبت کانال"),
              kp.simple("📊 وضعیت درخواست‌ها", "📊 وضعیت درخواست‌ها"))
    kp.append(kp.simple("👤 پروفایل من", "👤 پروفایل من"),
              kp.simple("🔗 لینک معرف", "🔗 لینک معرف"))
    return kp.build()


# ════════════════════════════════════════════════════════════
#  پنل مالک — Inline Keyboards
# ════════════════════════════════════════════════════════════

def owner_stats_keyboard() -> list:
    return _build_inline(
        _btn("📅 آمار امروز",  "stats:today"),
        _btn("📆 آمار هفته",   "stats:week"),
        _btn("🗓 آمار ماه",    "stats:month"),
        _btn("📈 آمار کل",     "stats:all"),
        _back_btn("owner_main"),
    )


def owner_admin_manage_keyboard() -> list:
    return _build_inline(
        _btn("➕ افزودن ادمین",  "admin:add"),
        _btn("📋 لیست ادمین‌ها", "admin:list"),
        _btn("📊 آمار ادمین‌ها", "admin:stats"),
        _back_btn("owner_main"),
    )


def owner_admin_list_keyboard(admins: list) -> list:
    kp = KeyPad()
    for adm in admins:
        icon = "✅" if adm["is_active"] else "⛔"
        kp.append(kp.simple(
            f"admin:manage:{adm['admin_id']}",
            f"{icon} {adm['display_name']} | {adm['min_members']}-{adm['max_members']} عضو"
        ))
    kp.append(_back_btn("admin_manage"))
    return kp.build()


def owner_admin_detail_keyboard(admin_id: str, is_active: bool) -> list:
    toggle_text = "⛔ تعلیق"    if is_active else "✅ فعال‌سازی"
    toggle_id   = f"admin:suspend:{admin_id}" if is_active else f"admin:activate:{admin_id}"
    return _build_inline(
        _btn("📊 آمار فردی",  f"admin:personal_stats:{admin_id}"),
        _btn(toggle_text,      toggle_id),
        _btn("🗑 حذف ادمین",  f"admin:remove:{admin_id}"),
        _back_btn("admin:list"),
    )


def owner_confirm_remove_admin_keyboard(admin_id: str) -> list:
    kp = KeyPad()
    kp.append(
        _btn("✅ بله، حذف شود", f"confirm:admin_remove:{admin_id}"),
        _btn("❌ خیر",           f"back:admin:manage:{admin_id}"),
    )
    return kp.build()


def owner_admin_add_confirm_keyboard() -> list:
    kp = KeyPad()
    kp.append(_btn("✅ تأیید و ثبت", "confirm:admin_add"))
    kp.append(_cancel_btn("admin_add"))
    return kp.build()


def owner_shift_keyboard(admins: list) -> list:
    kp = KeyPad()
    for adm in admins:
        kp.append(kp.simple(
            f"shift:edit:{adm['admin_id']}",
            f"🕐 {adm['display_name']} — شیفت: {adm['shift']}"
        ))
    kp.append(_back_btn("owner_main"))
    return kp.build()


def owner_shift_select_keyboard(admin_id: str) -> list:
    return _build_inline(
        _btn("🌅 صبح",      f"shift:set:morning:{admin_id}"),
        _btn("🌇 عصر",      f"shift:set:afternoon:{admin_id}"),
        _btn("🌙 شب",       f"shift:set:night:{admin_id}"),
        _btn("⏰ تمام وقت", f"shift:set:fulltime:{admin_id}"),
        _back_btn("shift"),
    )


def owner_system_keyboard() -> list:
    return _build_inline(
        _btn("🔴 خاموش/روشن ربات", "sys:toggle_bot"),
        _btn("📢 پیام همگانی",      "sys:broadcast"),
        _btn("🔒 جوین اجباری",      "sys:force_join"),
        _btn("⛔ بلاک کاربر",       "sys:block_user"),
        _btn("✅ آنبلاک کاربر",     "sys:unblock_user"),
        _btn("📋 لاگ سیستم",        "sys:logs"),
        _back_btn("owner_main"),
    )


def owner_force_join_keyboard(channels: list, is_active: bool) -> list:
    kp = KeyPad()
    status_text = "🔴 غیرفعال‌کردن" if is_active else "🟢 فعال‌کردن"
    kp.append(_btn(status_text, "fj:toggle"))
    kp.append(_btn("➕ افزودن کانال", "fj:add"))
    for ch in channels:
        title = ch.get("channel_title") or ch.get("channel_username", "")
        kp.append(_btn(f"🗑 {title}", f"fj:remove:{ch['id']}"))
    kp.append(_back_btn("sys"))
    return kp.build()


def owner_broadcast_target_keyboard() -> list:
    return _build_inline(
        _btn("👥 همه کاربران",  "bc:target:users"),
        _btn("🛡 همه ادمین‌ها", "bc:target:admins"),
        _btn("🌐 همه",          "bc:target:all"),
        _back_btn("sys"),
    )


def owner_tariff_keyboard(tariffs: list) -> list:
    kp = KeyPad()
    for t in tariffs:
        status = "✅" if t["is_active"] else "❌"
        label  = t.get("label") or t.get("name", "—")
        kp.append(kp.simple(
            f"tariff:edit:{t['id']}",
            f"{status} {label} | {t['min_members']}-{t['max_members']} عضو | {t['price']:,} تومان"
        ))
    kp.append(_btn("➕ تعرفه جدید", "tariff:add"))
    kp.append(_back_btn("owner_main"))
    return kp.build()


def owner_tariff_detail_keyboard(tariff_id: int, is_active: bool) -> list:
    toggle_text = "❌ غیرفعال" if is_active else "✅ فعال"
    return _build_inline(
        _btn("✏️ ویرایش قیمت",  f"tariff:price:{tariff_id}"),
        _btn("✏️ ویرایش بازه",  f"tariff:range:{tariff_id}"),
        _btn(toggle_text,         f"tariff:toggle:{tariff_id}"),
        _btn("🗑 حذف",           f"tariff:delete:{tariff_id}"),
        _back_btn("tariff"),
    )


def owner_texts_category_keyboard() -> list:
    return _build_inline(
        _btn("👤 متن‌های کاربر",    "texts:cat:user"),
        _btn("🛡 متن‌های ادمین",    "texts:cat:admin"),
        _btn("👑 متن‌های مالک",     "texts:cat:owner"),
        _btn("⚙️ متن‌های سیستمی",  "texts:cat:system"),
        _btn("🗂 فرمت بایگانی",     "texts:cat:archive"),
        _back_btn("owner_main"),
    )


def owner_texts_list_keyboard(texts: list, category: str) -> list:
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
    text_dict   = {t["key"]: t for t in texts}
    kp = KeyPad()
    for key in keys_in_cat:
        if key in text_dict:
            desc = text_dict[key].get("description") or key
            kp.append(kp.simple(f"texts:edit:{key}", f"✏️ {desc}"))
    kp.append(_back_btn("texts"))
    return kp.build()


def owner_text_edit_keyboard(key: str) -> list:
    return _build_inline(
        _btn("✏️ ویرایش",            f"texts:do_edit:{key}"),
        _btn("↩️ بازگشت به پیش‌فرض", f"texts:reset:{key}"),
        _back_btn("texts:cat"),
    )


def owner_confirm_text_reset_keyboard(key: str) -> list:
    kp = KeyPad()
    kp.append(
        _btn("✅ بله", f"confirm:text_reset:{key}"),
        _btn("❌ خیر", f"back:texts:edit:{key}"),
    )
    return kp.build()


def owner_report_review_keyboard(report_id: int) -> list:
    kp = KeyPad()
    kp.append(
        _btn("✅ تأیید گزارش", f"report:approve:{report_id}"),
        _btn("❌ رد گزارش",    f"report:reject:{report_id}"),
    )
    return kp.build()


# ════════════════════════════════════════════════════════════
#  پنل ادمین — Inline Keyboards
# ════════════════════════════════════════════════════════════

def admin_queue_keyboard(queue_items: list) -> list:
    kp = KeyPad()
    for i, item in enumerate(queue_items):
        prefix = "🔵 در حال بررسی" if i == 0 else f"⏳ انتظار ({i + 1})"
        link   = item.get("channel_link") or item.get("channel_username", "—")
        kp.append(kp.simple(
            f"queue:view:{item['id']}",
            f"{prefix} | {link} | {item['member_count']} عضو"
        ))
    kp.append(_back_btn("admin_main"))
    return kp.build()


def admin_request_detail_keyboard(channel_id: int,
                                   admin_joined: bool,
                                   admin_promoted: bool) -> list:
    kp = KeyPad()
    if not admin_joined:
        kp.append(_btn("✅ عضو کانال شدم", f"req:joined:{channel_id}"))
    elif not admin_promoted:
        kp.append(_btn("⏳ در انتظار ادمین شدن...", f"req:waiting_promote:{channel_id}"))
    else:
        kp.append(_btn("✅ تأیید نهایی — ارسال به بایگانی", f"req:approve:{channel_id}"))
    kp.append(_btn("❌ رد درخواست", f"req:reject:{channel_id}"))
    kp.append(_back_btn("queue"))
    return kp.build()


def admin_reject_reason_keyboard(channel_id: int) -> list:
    reasons = [
        ("آمار نادرست",  "wrong_stats"),
        ("کانال غیرفعال","inactive"),
        ("موضوع نامناسب","bad_topic"),
        ("لینک نامعتبر", "invalid_link"),
        ("سایر",         "other"),
    ]
    kp = KeyPad()
    for text, rid in reasons:
        kp.append(kp.simple(f"req:reject_reason:{channel_id}:{rid}", text))
    kp.append(_back_btn(f"queue:view:{channel_id}"))
    return kp.build()


def admin_channel_list_keyboard(channels: list) -> list:
    kp = KeyPad()
    for ch in channels:
        warn_icon = "⚠️" if ch.get("warning_count", 0) > 0 else "✅"
        code = ch.get("registration_code", "—")
        link = ch.get("channel_link", "—")
        members = ch.get("member_count", 0)
        kp.append(kp.simple(
            f"ch:manage:{ch['id']}",
            f"{warn_icon} {code} | {link} | {members} عضو"
        ))
    kp.append(_back_btn("admin_main"))
    return kp.build()


def admin_channel_detail_keyboard(channel_id: int, warning_count: int) -> list:
    kp = KeyPad()
    if warning_count == 0:
        kp.append(_btn("⚠️ اخطار سطح ۱", f"ch:warn:1:{channel_id}"))
    elif warning_count == 1:
        kp.append(_btn("🔴 اخطار سطح ۲", f"ch:warn:2:{channel_id}"))
    kp.append(_btn("🗑 حذف از لیست",     f"ch:remove:{channel_id}"))
    kp.append(_btn("📋 تاریخچه اخطارها", f"ch:warn_history:{channel_id}"))
    kp.append(_back_btn("ch:list"))
    return kp.build()


def admin_warning_reason_keyboard(channel_id: int, level: int) -> list:
    reasons = [
        ("عدم تبادل به موقع", "no_exchange"),
        ("کاهش آمار",         "stats_drop"),
        ("عدم پاسخگویی",      "no_response"),
        ("نقض قوانین",        "rule_break"),
        ("سایر",              "other"),
    ]
    kp = KeyPad()
    for text, rid in reasons:
        kp.append(kp.simple(f"ch:warn_reason:{channel_id}:{level}:{rid}", text))
    kp.append(_back_btn(f"ch:manage:{channel_id}"))
    return kp.build()


def admin_confirm_remove_channel_keyboard(channel_id: int) -> list:
    kp = KeyPad()
    kp.append(
        _btn("✅ بله، حذف شود", f"confirm:ch_remove:{channel_id}"),
        _btn("❌ خیر",           f"back:ch:manage:{channel_id}"),
    )
    return kp.build()


def admin_leaderboard_period_keyboard() -> list:
    return _build_inline(
        _btn("📅 امروز", "lb:today"),
        _btn("📆 هفته",  "lb:week"),
        _btn("🗓 ماه",   "lb:month"),
        _back_btn("admin_main"),
    )


def admin_report_confirm_keyboard() -> list:
    kp = KeyPad()
    kp.append(_confirm_btn("report"), _cancel_btn("report"))
    return kp.build()


# ════════════════════════════════════════════════════════════
#  پنل کاربر — Inline Keyboards
# ════════════════════════════════════════════════════════════

def user_topic_keyboard(topics: list) -> list:
    kp = KeyPad()
    for topic in topics:
        # topic می‌تواند dict یا رشته باشد
        if isinstance(topic, dict):
            title = topic.get("title", str(topic))
            tid   = topic.get("id", title)
        else:
            title = str(topic)
            tid   = title
        kp.append(kp.simple(f"topic:{tid}", title))
    kp.append(_cancel_btn("reg"))
    return kp.build()


def user_reg_confirm_keyboard(channel_id_temp: str) -> list:
    kp = KeyPad()
    kp.append(
        _btn("✅ تأیید و ارسال", f"reg:confirm:{channel_id_temp}"),
        _btn("❌ لغو",            "cancel:reg"),
    )
    return kp.build()


def user_requests_keyboard(channels: list) -> list:
    status_icons = {
        "pending":       "🟡",
        "admin_joined":  "🔵",
        "waiting_owner": "🔵",
        "confirmed":     "🟢",
        "archived":      "✅",
        "rejected":      "❌",
        "cancelled":     "⛔",
    }
    kp = KeyPad()
    for ch in channels:
        icon       = status_icons.get(ch.get("status", ""), "❓")
        code       = ch.get("registration_code", "—")
        link       = ch.get("channel_link", "—")
        admin_part = f" | @{ch['admin_username']}" if ch.get("admin_username") else ""
        kp.append(kp.simple(
            f"req:status:{ch['id']}",
            f"{icon} {code} — {link}{admin_part}"
        ))
    kp.append(_back_btn("user_main"))
    return kp.build()


def user_request_detail_keyboard(channel_id: int) -> list:
    return _build_inline(
        _btn("🗑 لغو درخواست", f"req:cancel:{channel_id}"),
        _back_btn("req:list"),
    )


def user_confirm_cancel_request_keyboard(channel_id: int) -> list:
    kp = KeyPad()
    kp.append(
        _btn("✅ بله، لغو شود", f"confirm:req_cancel:{channel_id}"),
        _btn("❌ خیر",           f"back:req:status:{channel_id}"),
    )
    return kp.build()


# ════════════════════════════════════════════════════════════
#  جوین اجباری
# ════════════════════════════════════════════════════════════

def force_join_keyboard(channels: list) -> list:
    kp = KeyPad()
    for ch in channels:
        title = ch.get("channel_title") or ch.get("channel_username", "کانال")
        kp.append(kp.simple(f"fj:open:{ch['channel_username']}", f"📢 {title}"))
    kp.append(_btn(get_text("force_join_btn"), "fj:check"))
    return kp.build()


# ════════════════════════════════════════════════════════════
#  تأیید ادمین شدن (مالک)
# ════════════════════════════════════════════════════════════

def owner_promote_confirm_keyboard(channel_id: int) -> list:
    return _build_inline(
        _btn("✅ ادمین کردم", f"promote:done:{channel_id}"),
    )
