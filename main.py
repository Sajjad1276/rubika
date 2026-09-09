# ============================================================
#  main.py — هسته اصلی ربات تبادل روبیکا
#  کتابخانه: fastrub (fast_rub)
#  pip install fastrub
# ============================================================

import asyncio
import json
import logging
import os
from datetime import datetime

from fast_rub import Client, filters
from fast_rub.types import Update, UpdateButton

import config
from config import (
    BOT_TOKEN, OWNER_USERNAME, OWNER_ID,
    ConvState, ChannelStatus, UserRole,
    AdminAddStep, LOG_LEVEL, LOG_TO_FILE, LOG_FILE
)
import database as db
import keyboards as kb

# ════════════════════════════════════════════════════════════
#  راه‌اندازی لاگ
# ════════════════════════════════════════════════════════════

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        *(
            [logging.FileHandler(LOG_FILE, encoding="utf-8")]
            if LOG_TO_FILE else []
        ),
    ],
)
logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════
#  راه‌اندازی ربات و دیتابیس
# ════════════════════════════════════════════════════════════

# توکن از environment variable خوانده می‌شود (برای Railway)
token = os.environ.get("BOT_TOKEN", BOT_TOKEN)
owner_username = os.environ.get("OWNER_USERNAME", OWNER_USERNAME)

bot = Client(name_session="rubika_exchange_bot", token=token)
db.init_db()
logger.info("دیتابیس آماده شد.")


# ════════════════════════════════════════════════════════════
#  ابزارهای کمکی داخلی
# ════════════════════════════════════════════════════════════

def _is_owner(username: str, user_id: str = "") -> bool:
    """بررسی اینکه آیا کاربر مالک ربات است.
    اگر OWNER_ID تنظیم شده باشد، user_id اولویت دارد (امن‌تر).
    در غیر این‌صورت از OWNER_USERNAME استفاده می‌شود.
    """
    _env_owner_id = os.environ.get("OWNER_ID", OWNER_ID).strip()
    if _env_owner_id and user_id:
        return str(user_id) == str(_env_owner_id)
    if not username:
        return False
    return username.strip().lower().lstrip("@") == owner_username.lower()


def _get_role(user_id: str, username: str) -> str:
    if _is_owner(username, user_id):
        return UserRole.OWNER
    user = db.get_user(user_id)
    if user and user["role"] == UserRole.ADMIN:
        return UserRole.ADMIN
    return UserRole.USER


def _state(user_id: str) -> tuple[str, dict]:
    state, data_str = db.get_user_state(user_id)
    try:
        data = json.loads(data_str)
    except Exception:
        data = {}
    return state, data


def _set_state(user_id: str, state: str, data: dict = None) -> None:
    db.set_user_state(user_id, state, json.dumps(data or {}, ensure_ascii=False))


def _reset_state(user_id: str) -> None:
    # ابتدا بررسی می‌کنیم آیا owner_id در settings ست شده است
    owner_id_in_db = db.get_setting("owner_id")
    if owner_id_in_db and user_id == owner_id_in_db:
        _set_state(user_id, ConvState.OWNER_IDLE)
        return
    role = db.get_user_role(user_id)
    if role == UserRole.ADMIN:
        _set_state(user_id, ConvState.ADMIN_IDLE)
    elif role == UserRole.OWNER:
        _set_state(user_id, ConvState.OWNER_IDLE)
    else:
        _set_state(user_id, ConvState.IDLE)


def _persian_date() -> str:
    try:
        import jdatetime
        return jdatetime.datetime.now().strftime("%Y/%m/%d")
    except ImportError:
        return datetime.now().strftime("%Y-%m-%d")


async def _send(chat_id: str, text: str,
                keypad=None, inline_keypad=None) -> None:
    """ارسال پیام — wrapper یکپارچه."""
    kwargs = {}
    if keypad is not None:
        kwargs["keypad"] = keypad
    if inline_keypad is not None:
        kwargs["inline_keypad"] = inline_keypad
    await bot.send_text(chat_id=chat_id, text=text, **kwargs)


async def _check_bot_active(chat_id: str) -> bool:
    if db.get_setting("bot_active") == "0":
        await _send(chat_id, db.get_text("maintenance_msg"))
        return False
    return True


async def _check_force_join(chat_id: str, user_id: str) -> bool:
    if db.get_setting("force_join_active") != "1":
        return True
    channels = db.get_active_forced_joins()
    if not channels:
        return True
    user = db.get_user(user_id)
    if user and user.get("state") == "fj_passed":
        return True
    await _send(chat_id, db.get_text("force_join_msg"),
                inline_keypad=kb.force_join_keyboard(channels))
    return False


# ════════════════════════════════════════════════════════════
#  هندلر استارت (/start)
# ════════════════════════════════════════════════════════════

@bot.on_message(filters.commands("start"))
async def on_start(msg: Update):
    user_id      = msg.chat_id
    username     = msg.new_message.raw_data.get("author_object", {}).get("username", "")
    display_name = msg.new_message.raw_data.get("author_object", {}).get("first_name", "کاربر")

    # ── parse پارامتر referral از دستور /start ──────────────
    # فرمت: /start ref_XXXXXXXX
    referral_by: str | None = None
    raw_text: str = msg.new_message.text or ""
    parts_cmd = raw_text.strip().split(maxsplit=1)
    if len(parts_cmd) > 1:
        start_param = parts_cmd[1].strip()
        if start_param.startswith("ref_"):
            ref_code = start_param[4:]
            ref_user = db.get_user_by_referral_code(ref_code)
            if ref_user and ref_user["user_id"] != user_id:
                referral_by = ref_user["user_id"]

    state, data = _state(user_id)
    # referral_by از پارامتر اولویت دارد؛ در غیر این‌صورت از state قبلی استفاده می‌شود
    if not referral_by:
        referral_by = data.get("referral_by")

    db.get_or_create_user(user_id, username, display_name, referral_by)

    role = _get_role(user_id, username)

    if role == UserRole.OWNER:
        db.set_setting("owner_id", user_id)
        _set_state(user_id, ConvState.OWNER_IDLE)
        await _send(user_id,
                    db.get_text("owner_welcome", name=display_name),
                    keypad=kb.owner_main_keyboard())

    elif role == UserRole.ADMIN:
        _set_state(user_id, ConvState.ADMIN_IDLE)
        await _send(user_id,
                    db.get_text("admin_welcome", name=display_name),
                    keypad=kb.admin_main_keyboard())

    else:
        if not await _check_bot_active(user_id):
            return
        if not await _check_force_join(user_id, user_id):
            return
        _set_state(user_id, ConvState.IDLE)
        await _send(user_id,
                    db.get_text("welcome", name=display_name),
                    keypad=kb.user_main_keyboard())


# ════════════════════════════════════════════════════════════
#  هندلر دکمه‌های Inline
# ════════════════════════════════════════════════════════════

@bot.on_button()
async def on_button(msg: UpdateButton):
    user_id   = msg.sender_id
    button_id = msg.button_id

    if db.is_user_blocked(user_id):
        await msg.send_text(db.get_text("blocked_msg"))
        return

    username = msg.raw_data.get("inline_message", {}).get(
        "author_object", {}
    ).get("username", "")

    role        = _get_role(user_id, username)
    state, data = _state(user_id)

    await _handle_callback(user_id, role, button_id, state, data, msg)


# ════════════════════════════════════════════════════════════
#  هندلر اصلی پیام‌ها
# ════════════════════════════════════════════════════════════

@bot.on_message(filters.is_user)
async def on_message(msg: Update):
    user_id = msg.chat_id
    text    = msg.new_message.text or ""

    # دستور /start را on_start هندل می‌کند
    if text.startswith("/start"):
        return

    if db.is_user_blocked(user_id):
        await _send(user_id, db.get_text("blocked_msg"))
        return

    username = msg.new_message.raw_data.get("author_object", {}).get("username", "")
    role        = _get_role(user_id, username)
    state, data = _state(user_id)

    if role == UserRole.OWNER:
        await _handle_owner(user_id, msg, text, state, data)
    elif role == UserRole.ADMIN:
        await _handle_admin(user_id, msg, text, state, data)
    else:
        if not await _check_bot_active(user_id):
            return
        if not await _check_force_join(user_id, user_id):
            return
        await _handle_user(user_id, msg, text, state, data)


# ════════════════════════════════════════════════════════════
#  هندلر مالک
# ════════════════════════════════════════════════════════════

async def _handle_owner(user_id: str, msg: Update,
                         text: str, state: str, data: dict):

    if text == "📊 آمار ربات":
        await _send(user_id, "بازه زمانی را انتخاب کنید:",
                    inline_keypad=kb.owner_stats_keyboard())
        return

    if text == "👥 مدیریت ادمین‌ها":
        await _send(user_id, "مدیریت ادمین‌ها:",
                    inline_keypad=kb.owner_admin_manage_keyboard())
        return

    if text == "🕐 برنامه کار":
        admins = db.get_all_admins()
        if not admins:
            await _send(user_id, "هیچ ادمینی ثبت نشده است.")
            return
        await _send(user_id, "برنامه کار ادمین‌ها:",
                    inline_keypad=kb.owner_shift_keyboard(admins))
        return

    if text == "⚙️ کنترل سیستم":
        await _send(user_id, "کنترل سیستم:",
                    inline_keypad=kb.owner_system_keyboard())
        return

    if text == "💰 تعرفه‌ها":
        conn = db.get_conn()
        tariffs = conn.execute("SELECT * FROM tariffs ORDER BY min_members").fetchall()
        conn.close()
        await _send(user_id, "تعرفه‌ها:", inline_keypad=kb.owner_tariff_keyboard(tariffs))
        return

    if text == "✏️ مدیریت متن‌ها":
        await _send(user_id, "دسته‌بندی متن‌ها را انتخاب کنید:",
                    inline_keypad=kb.owner_texts_category_keyboard())
        return

    if state.startswith(ConvState.OWNER_ADD_ADMIN):
        await _handle_owner_add_admin_state(user_id, text, state, data)
        return

    if state == ConvState.OWNER_EDIT_TEXT_WAITING:
        key = data.get("editing_key")
        if key and text:
            db.update_text(key, text, user_id)
            txt = db.get_text(key)
            await _send(user_id,
                        f"✅ متن با موفقیت به‌روز شد.\n\nمتن جدید:\n{txt}",
                        inline_keypad=kb.owner_text_edit_keyboard(key))
            _reset_state(user_id)
        return

    if state == ConvState.OWNER_BROADCAST_WRITING:
        target = data.get("bc_target", "all")
        await _do_broadcast(user_id, text, target)
        _reset_state(user_id)
        return

    # ── هندل block/unblock و add_fj کاربر ──────────────────
    if state == ConvState.OWNER_IDLE and data.get("pending_action") in (
        "block", "unblock", "add_fj"
    ):
        action = data["pending_action"]
        target_val = text.strip()
        if not target_val:
            await _send(user_id, db.get_text("invalid_input"))
            return
        if action == "block":
            db.block_user(target_val, user_id)
            await _send(user_id, f"✅ کاربر {target_val} بلاک شد.",
                        inline_keypad=kb.owner_system_keyboard())
        elif action == "unblock":
            db.unblock_user(target_val, user_id)
            await _send(user_id, f"✅ کاربر {target_val} آنبلاک شد.",
                        inline_keypad=kb.owner_system_keyboard())
        elif action == "add_fj":
            username = target_val.lstrip("@").strip()
            db.add_forced_join(channel_id=username, username=username, title=username)
            channels  = db.get_active_forced_joins()
            is_active = db.get_setting("force_join_active") == "1"
            await _send(user_id, f"✅ کانال @{username} به لیست جوین اجباری اضافه شد.",
                        inline_keypad=kb.owner_force_join_keyboard(channels, is_active))
        _reset_state(user_id)
        return

    if state == ConvState.OWNER_SET_TARIFF:
        await _handle_owner_tariff_state(user_id, text, state, data)
        return

    # پیش‌فرض
    display_name = msg.new_message.raw_data.get("author_object", {}).get("first_name", "مالک")
    await _send(user_id,
                db.get_text("owner_welcome", name=display_name),
                keypad=kb.owner_main_keyboard())


async def _handle_owner_add_admin_state(user_id: str, text: str,
                                         state: str, data: dict):
    step = data.get("step", AdminAddStep.USERNAME)

    if step == AdminAddStep.USERNAME:
        data["username"] = text.lstrip("@").strip()
        data["step"] = AdminAddStep.ADMIN_ID
        _set_state(user_id, ConvState.OWNER_ADD_ADMIN, data)
        await _send(user_id,
                    "آیدی عددی ادمین را وارد کنید:\n"
                    "(آیدی عددی روبیکا — مثلاً: u1234567890)\n\n"
                    "💡 ادمین باید یک بار /start را در ربات زده باشد.")

    elif step == AdminAddStep.ADMIN_ID:
        admin_id_val = text.strip()
        if not admin_id_val:
            await _send(user_id, db.get_text("invalid_input"))
            return
        data["admin_id"] = admin_id_val
        data["step"] = AdminAddStep.DISPLAY_NAME
        _set_state(user_id, ConvState.OWNER_ADD_ADMIN, data)
        await _send(user_id, "مرحله ۳ از ۹\nنام نمایشی ادمین را وارد کنید:")

    elif step == AdminAddStep.DISPLAY_NAME:
        data["display_name"] = text.strip()
        data["step"] = AdminAddStep.MIN_MEMBERS
        _set_state(user_id, ConvState.OWNER_ADD_ADMIN, data)
        await _send(user_id, "مرحله ۴ از ۹\nحداقل تعداد عضو کانال‌های این ادمین را وارد کنید:\n(مثلاً: 0)")

    elif step == AdminAddStep.MIN_MEMBERS:
        if not text.isdigit():
            await _send(user_id, db.get_text("invalid_input"))
            return
        data["min_members"] = int(text)
        data["step"] = AdminAddStep.MAX_MEMBERS
        _set_state(user_id, ConvState.OWNER_ADD_ADMIN, data)
        await _send(user_id, "حداکثر تعداد عضو کانال‌های این ادمین را وارد کنید:\n(مثلاً: 5000)")

    elif step == AdminAddStep.MAX_MEMBERS:
        if not text.isdigit():
            await _send(user_id, db.get_text("invalid_input"))
            return
        data["max_members"] = int(text)
        data["step"] = AdminAddStep.ARCHIVE_CHANNEL
        _set_state(user_id, ConvState.OWNER_ADD_ADMIN, data)
        await _send(user_id,
                    "آیدی عددی کانال بایگانی اختصاصی این ادمین را وارد کنید:\n"
                    "(مثلاً: -1001234567890)\n\n"
                    "⚠️ ربات باید ادمین این کانال باشد.")

    elif step == AdminAddStep.ARCHIVE_CHANNEL:
        data["archive_channel_id"] = text.strip()
        data["step"] = AdminAddStep.SHIFT
        _set_state(user_id, ConvState.OWNER_ADD_ADMIN, data)
        await _send(user_id, "شیفت کاری این ادمین را انتخاب کنید:",
                    inline_keypad=kb.owner_shift_select_keyboard("new_admin"))


async def _handle_owner_tariff_state(user_id: str, text: str,
                                      state: str, data: dict):
    step = data.get("tariff_step", "label")

    if step == "label":
        data["label"] = text.strip()
        data["tariff_step"] = "min"
        _set_state(user_id, ConvState.OWNER_SET_TARIFF, data)
        await _send(user_id, "حداقل عضو این بازه را وارد کنید:")

    elif step == "min":
        if not text.isdigit():
            await _send(user_id, db.get_text("invalid_input"))
            return
        data["min_members"] = int(text)
        data["tariff_step"] = "max"
        _set_state(user_id, ConvState.OWNER_SET_TARIFF, data)
        await _send(user_id, "حداکثر عضو این بازه را وارد کنید:")

    elif step == "max":
        if not text.isdigit():
            await _send(user_id, db.get_text("invalid_input"))
            return
        data["max_members"] = int(text)
        data["tariff_step"] = "price"
        _set_state(user_id, ConvState.OWNER_SET_TARIFF, data)
        await _send(user_id, "قیمت (تومان) را وارد کنید:")

    elif step == "price":
        if not text.isdigit():
            await _send(user_id, db.get_text("invalid_input"))
            return
        conn = db.get_conn()
        conn.execute(
            "INSERT INTO tariffs (label, min_members, max_members, price) VALUES (?,?,?,?)",
            (data["label"], data["min_members"], data["max_members"], int(text))
        )
        conn.commit()
        tariffs = conn.execute("SELECT * FROM tariffs ORDER BY min_members").fetchall()
        conn.close()
        await _send(user_id, "✅ تعرفه با موفقیت افزوده شد.",
                    inline_keypad=kb.owner_tariff_keyboard(tariffs))
        _reset_state(user_id)

    # ── ویرایش قیمت تعرفه موجود ─────────────────────────────
    elif step == "edit_price":
        if not text.isdigit():
            await _send(user_id, db.get_text("invalid_input"))
            return
        tariff_id = data.get("tariff_id")
        ok = db.update_tariff_price(tariff_id, int(text))
        conn = db.get_conn()
        tariffs = conn.execute("SELECT * FROM tariffs ORDER BY min_members").fetchall()
        conn.close()
        msg_text = "✅ قیمت تعرفه به‌روز شد." if ok else "❌ خطا در به‌روزرسانی."
        await _send(user_id, msg_text,
                    inline_keypad=kb.owner_tariff_keyboard(tariffs))
        _reset_state(user_id)

    # ── ویرایش بازه عضو تعرفه موجود ────────────────────────
    elif step == "edit_range_min":
        if not text.isdigit():
            await _send(user_id, db.get_text("invalid_input"))
            return
        data["new_min"] = int(text)
        data["tariff_step"] = "edit_range_max"
        _set_state(user_id, ConvState.OWNER_SET_TARIFF, data)
        await _send(user_id, "حداکثر عضو جدید را وارد کنید:")

    elif step == "edit_range_max":
        if not text.isdigit():
            await _send(user_id, db.get_text("invalid_input"))
            return
        tariff_id = data.get("tariff_id")
        ok = db.update_tariff_range(tariff_id, data["new_min"], int(text))
        conn = db.get_conn()
        tariffs = conn.execute("SELECT * FROM tariffs ORDER BY min_members").fetchall()
        conn.close()
        if ok:
            await _send(user_id, "✅ بازه تعرفه به‌روز شد.",
                        inline_keypad=kb.owner_tariff_keyboard(tariffs))
        else:
            await _send(user_id, "❌ خطا: حداقل باید کمتر از حداکثر باشد.")
        _reset_state(user_id)


# ════════════════════════════════════════════════════════════
#  هندلر ادمین
# ════════════════════════════════════════════════════════════

async def _handle_admin(user_id: str, msg: Update,
                         text: str, state: str, data: dict):

    if text == "📋 صف درخواست‌ها":
        queue = db.get_admin_queue(user_id)
        if not queue:
            await _send(user_id, "صف شما خالی است.")
            return
        await _send(user_id, "صف درخواست‌های شما:",
                    inline_keypad=kb.admin_queue_keyboard(queue))
        return

    if text == "📊 ادمین‌های برتر":
        await _send(user_id, "بازه زمانی را انتخاب کنید:",
                    inline_keypad=kb.admin_leaderboard_period_keyboard())
        return

    if text == "📝 گزارش روزانه":
        _set_state(user_id, ConvState.ADMIN_REPORT_WRITING)
        await _send(user_id, db.get_text("admin_report_prompt"),
                    inline_keypad=kb.admin_report_confirm_keyboard())
        return

    if text == "📦 لیست کانال‌هایم":
        conn = db.get_conn()
        channels = conn.execute(
            "SELECT * FROM channels WHERE assigned_admin_id=? AND status='archived' ORDER BY registered_at DESC",
            (user_id,)
        ).fetchall()
        conn.close()
        if not channels:
            await _send(user_id, "هنوز کانالی ثبت نکرده‌اید.")
            return
        await _send(user_id, "لیست کانال‌های شما:",
                    inline_keypad=kb.admin_channel_list_keyboard(channels))
        return

    if state == ConvState.ADMIN_REPORT_WRITING and text:
        report_id = db.save_daily_report(user_id, text)
        adm       = db.get_admin(user_id)
        owner_id  = db.get_setting("owner_id")
        if owner_id and adm:
            await _send(
                owner_id,
                db.get_text("owner_report_received",
                            admin_username=adm["username"],
                            report_text=text,
                            date=_persian_date()),
                inline_keypad=kb.owner_report_review_keyboard(report_id)
            )
        await _send(user_id, db.get_text("admin_report_sent"),
                    keypad=kb.admin_main_keyboard())
        _reset_state(user_id)
        return

    if state == ConvState.ADMIN_REJECT_REASON:
        channel_id = data.get("channel_id")
        if channel_id and text:
            ch = db.get_channel(channel_id)
            if ch:
                db.update_channel_status(channel_id, ChannelStatus.REJECTED, user_id, text)
                adm = db.get_admin(user_id)
                await _send(
                    ch["owner_user_id"],
                    db.get_text("reg_rejected",
                                channel=ch["channel_link"],
                                admin_username=adm["username"] if adm else "ادمین",
                                reason=text)
                )
            await _send(user_id, "❌ درخواست رد شد.",
                        keypad=kb.admin_main_keyboard())
            _reset_state(user_id)
        return

    if state == ConvState.ADMIN_WARNING_REASON:
        channel_id = data.get("channel_id")
        level      = data.get("level", 1)
        reason_id  = data.get("reason_id", "other")
        if channel_id:
            ch         = db.get_channel(channel_id)
            adm        = db.get_admin(user_id)
            expire_days = int(db.get_setting("warning_expire_days") or 7)
            db.issue_warning(channel_id, user_id, level, text or reason_id, expire_days)
            if ch and adm:
                warn_key = f"warning_level{level}"
                await _send(
                    ch["owner_user_id"],
                    db.get_text(warn_key,
                                channel=ch["channel_link"],
                                code=ch["registration_code"],
                                admin_username=adm["username"],
                                reason=text or reason_id,
                                days=expire_days)
                )
            await _send(user_id, "⚠️ اخطار صادر شد.",
                        keypad=kb.admin_main_keyboard())
            _reset_state(user_id)
        return

    # پیش‌فرض
    display_name = msg.new_message.raw_data.get("author_object", {}).get("first_name", "ادمین")
    await _send(user_id,
                db.get_text("admin_welcome", name=display_name),
                keypad=kb.admin_main_keyboard())


# ════════════════════════════════════════════════════════════
#  هندلر کاربر عادی
# ════════════════════════════════════════════════════════════

async def _handle_user(user_id: str, msg: Update,
                        text: str, state: str, data: dict):

    if text == "📦 ثبت کانال":
        _set_state(user_id, ConvState.REG_WAITING_LINK)
        await _send(user_id, db.get_text("reg_ask_link"))
        return

    if text == "📊 وضعیت درخواست‌ها":
        channels = db.get_user_channels(user_id)
        if not channels:
            await _send(user_id, db.get_text("no_requests"))
            return
        await _send(user_id, db.get_text("status_check"),
                    inline_keypad=kb.user_requests_keyboard(channels))
        return

    if text == "👤 پروفایل من":
        user     = db.get_user(user_id)
        channels = db.get_user_channels(user_id)
        warn_count = sum(ch["warning_count"] for ch in channels)
        ref_link   = f"https://rubika.ir/bot/{token.split(':')[0]}?start=ref_{user['referral_code']}"
        await _send(user_id,
                    db.get_text("profile_text",
                                join_date=user["joined_at"],
                                channel_count=len(channels),
                                warning_count=warn_count,
                                referral_link=ref_link))
        return

    if text == "🔗 لینک معرف":
        user     = db.get_user(user_id)
        ref_link = f"https://rubika.ir/bot/{token.split(':')[0]}?start=ref_{user['referral_code']}"
        await _send(user_id, db.get_text("referral_link_text", referral_link=ref_link))
        return

    # ── جریان ثبت کانال ─────────────────────────────────────
    if state == ConvState.REG_WAITING_LINK:
        if not text or not (text.startswith("@") or "rubika.ir" in text):
            await _send(user_id, "⚠️ لطفاً یک لینک معتبر ارسال کنید. (مثال: @mychannel)")
            return
        data["channel_link"] = text.strip()
        _set_state(user_id, ConvState.REG_WAITING_MEMBERS, data)
        await _send(user_id, db.get_text("reg_ask_members"))
        return

    if state == ConvState.REG_WAITING_MEMBERS:
        if not text.isdigit():
            await _send(user_id, db.get_text("invalid_input"))
            return
        data["member_count"] = int(text)
        _set_state(user_id, ConvState.REG_WAITING_VIEWS, data)
        await _send(user_id, db.get_text("reg_ask_views"))
        return

    if state == ConvState.REG_WAITING_VIEWS:
        if not text.isdigit():
            await _send(user_id, db.get_text("invalid_input"))
            return
        data["avg_view"] = int(text)
        _set_state(user_id, ConvState.REG_WAITING_TOPIC, data)
        conn   = db.get_conn()
        topics = conn.execute(
            "SELECT * FROM topics WHERE is_active=1 ORDER BY sort_order"
        ).fetchall()
        conn.close()
        await _send(user_id, db.get_text("reg_ask_topic"),
                    inline_keypad=kb.user_topic_keyboard(topics))
        return

    if state == ConvState.REG_WAITING_BANNER:
        # بنر — عکس با کپشن
        file_obj = msg.new_message.file
        if file_obj and file_obj.file_id:
            data["banner_file_id"] = file_obj.file_id
            data["banner_caption"] = ""
            _set_state(user_id, ConvState.REG_CONFIRM, data)
            await _send(
                user_id,
                db.get_text("reg_confirm",
                            channel=data["channel_link"],
                            members=f"{data['member_count']:,}",
                            views=f"{data['avg_view']:,}"),
                inline_keypad=kb.user_reg_confirm_keyboard("pending")
            )
        else:
            await _send(user_id, "⚠️ لطفاً یک تصویر (بنر) ارسال کنید.")
        return

    # پیش‌فرض
    display_name = msg.new_message.raw_data.get("author_object", {}).get("first_name", "کاربر")
    await _send(user_id,
                db.get_text("welcome", name=display_name),
                keypad=kb.user_main_keyboard())


# ════════════════════════════════════════════════════════════
#  هندلر مرکزی Callback (دکمه‌های Inline)
# ════════════════════════════════════════════════════════════

async def _handle_callback(user_id: str, role: str, button_id: str,
                            state: str, data: dict, msg: UpdateButton):
    parts  = button_id.split(":")
    action = parts[0] if parts else ""

    if action == "back":
        await _handle_back(user_id, role, parts[1:])
        return

    if action == "cancel":
        _reset_state(user_id)
        await _handle_back(user_id, role, ["main"])
        return

    if action == "fj":
        await _cb_force_join(user_id, parts)
        return

    if action == "stats" and role == UserRole.OWNER:
        period = parts[1] if len(parts) > 1 else "all"
        stats  = db.get_bot_stats()
        text   = (
            f"📊 آمار ربات ({period})\n\n"
            f"👥 کاربران: {stats['total_users']:,}\n"
            f"🛡 ادمین‌های فعال: {stats['total_admins']}\n"
            f"📦 ثبتی امروز: {stats['channels_today']}\n"
            f"📦 ثبتی هفته: {stats['channels_week']}\n"
            f"📦 ثبتی ماه: {stats['channels_month']}\n"
            f"📦 کل ثبتی‌ها: {stats['channels_total']}\n"
            f"⏳ در انتظار: {stats['pending_count']}\n"
            f"⚠️ اخطارهای فعال: {stats['active_warnings']}"
        )
        await _send(user_id, text, inline_keypad=kb.owner_stats_keyboard())
        return

    if action == "admin" and role == UserRole.OWNER:
        await _cb_admin_manage(user_id, parts)
        return

    if action == "shift" and role == UserRole.OWNER:
        await _cb_shift(user_id, parts)
        return

    if action == "sys" and role == UserRole.OWNER:
        await _cb_system(user_id, parts, data)
        return

    if action == "bc" and role == UserRole.OWNER:
        target = parts[2] if len(parts) > 2 else "all"
        _set_state(user_id, ConvState.OWNER_BROADCAST_WRITING, {"bc_target": target})
        await _send(user_id, "پیام همگانی را بنویسید و ارسال کنید:")
        return

    if action == "tariff" and role == UserRole.OWNER:
        await _cb_tariff(user_id, parts)
        return

    if action == "texts" and role == UserRole.OWNER:
        await _cb_texts(user_id, parts)
        return

    if action == "report" and role == UserRole.OWNER:
        await _cb_report_review(user_id, parts)
        return

    if action == "promote" and role == UserRole.OWNER:
        await _cb_promote(user_id, parts)
        return

    if action == "queue" and role == UserRole.ADMIN:
        await _cb_queue(user_id, parts)
        return

    if action == "req":
        if role == UserRole.ADMIN:
            await _cb_request_admin(user_id, parts, data)
        else:
            await _cb_request_user(user_id, parts, state, data)
        return

    if action == "topic":
        topic_id = parts[1] if len(parts) > 1 else None
        if topic_id and state == ConvState.REG_WAITING_TOPIC:
            conn = db.get_conn()
            t = conn.execute("SELECT title FROM topics WHERE id=?", (topic_id,)).fetchone()
            conn.close()
            if t:
                data["topic"] = t["title"]
                _set_state(user_id, ConvState.REG_WAITING_BANNER, data)
                await _send(user_id, db.get_text("reg_ask_banner"))
        return

    if action == "reg" and len(parts) > 1 and parts[1] == "confirm":
        await _cb_reg_confirm(user_id, state, data)
        return

    if action == "lb":
        period = parts[1] if len(parts) > 1 else "month"
        rows   = db.get_admin_leaderboard(period)
        medals = ["🥇", "🥈", "🥉"]
        lines  = [f"🏆 رنکینگ ادمین‌ها ({period})\n"]
        for i, r in enumerate(rows):
            medal = medals[i] if i < 3 else f"{i+1}."
            lines.append(f"{medal} {r['display_name']}: {r['reg_count']} ثبتی | {r['total_referrals']} جذب")
        await _send(user_id, "\n".join(lines),
                    inline_keypad=kb.admin_leaderboard_period_keyboard())
        return

    if action == "ch" and role == UserRole.ADMIN:
        await _cb_channel_manage(user_id, parts, data)
        return

    if action == "confirm":
        await _cb_confirm(user_id, role, parts, data)
        return


# ════════════════════════════════════════════════════════════
#  پردازنده‌های Callback جزئی
# ════════════════════════════════════════════════════════════

async def _handle_back(user_id: str, role: str, path: list):
    dest = path[0] if path else "main"

    if dest in ("main", "owner_main"):
        _reset_state(user_id)
        if role == UserRole.OWNER:
            await _send(user_id, db.get_text("owner_welcome", name="مالک"),
                        keypad=kb.owner_main_keyboard())
        elif role == UserRole.ADMIN:
            await _send(user_id, db.get_text("admin_welcome", name="ادمین"),
                        keypad=kb.admin_main_keyboard())
        else:
            await _send(user_id, db.get_text("welcome", name="کاربر"),
                        keypad=kb.user_main_keyboard())

    elif dest == "admin_manage":
        await _send(user_id, "مدیریت ادمین‌ها:",
                    inline_keypad=kb.owner_admin_manage_keyboard())

    elif dest == "admin:list":
        admins = db.get_all_admins()
        await _send(user_id, "لیست ادمین‌ها:",
                    inline_keypad=kb.owner_admin_list_keyboard(admins))

    elif dest == "queue":
        queue = db.get_admin_queue(user_id)
        await _send(user_id, "صف درخواست‌های شما:",
                    inline_keypad=kb.admin_queue_keyboard(queue))

    elif dest == "ch:list":
        conn = db.get_conn()
        channels = conn.execute(
            "SELECT * FROM channels WHERE assigned_admin_id=? AND status='archived'",
            (user_id,)
        ).fetchall()
        conn.close()
        await _send(user_id, "لیست کانال‌های شما:",
                    inline_keypad=kb.admin_channel_list_keyboard(channels))

    elif dest == "texts":
        await _send(user_id, "دسته‌بندی متن‌ها:",
                    inline_keypad=kb.owner_texts_category_keyboard())

    elif dest == "sys":
        await _send(user_id, "کنترل سیستم:",
                    inline_keypad=kb.owner_system_keyboard())

    elif dest == "tariff":
        conn = db.get_conn()
        tariffs = conn.execute("SELECT * FROM tariffs ORDER BY min_members").fetchall()
        conn.close()
        await _send(user_id, "تعرفه‌ها:", inline_keypad=kb.owner_tariff_keyboard(tariffs))

    elif dest == "req:list":
        channels = db.get_user_channels(user_id)
        await _send(user_id, db.get_text("status_check"),
                    inline_keypad=kb.user_requests_keyboard(channels))


async def _cb_force_join(user_id: str, parts: list):
    sub = parts[1] if len(parts) > 1 else ""

    if sub == "check":
        # کاربر ادعا می‌کند که عضو شده — state را تغییر می‌دهیم
        db.set_user_state(user_id, ConvState.IDLE)
        user = db.get_user(user_id)
        display_name = user["display_name"] if user else "کاربر"
        await _send(user_id, db.get_text("welcome", name=display_name),
                    keypad=kb.user_main_keyboard())

    elif sub == "open":
        # دکمه لینک کانال — کاربر را به کانال هدایت می‌کند (فقط نمایش)
        pass

    elif sub == "toggle":
        # فعال/غیرفعال کردن force join توسط مالک
        current = db.get_setting("force_join_active")
        new_val = "0" if current == "1" else "1"
        db.set_setting("force_join_active", new_val)
        channels  = db.get_active_forced_joins()
        is_active = new_val == "1"
        status    = "فعال ✅" if is_active else "غیرفعال 🔴"
        await _send(user_id, f"جوین اجباری: {status}",
                    inline_keypad=kb.owner_force_join_keyboard(channels, is_active))

    elif sub == "add":
        # افزودن کانال جدید به لیست force join
        _set_state(user_id, ConvState.OWNER_IDLE, {"pending_action": "add_fj"})
        await _send(user_id,
                    "لینک یا یوزرنیم کانال را ارسال کنید:\n"
                    "(مثال: @mychannel)")

    elif sub == "remove" and len(parts) > 2:
        # حذف کانال از لیست force join
        fj_id = int(parts[2])
        db.remove_forced_join(fj_id)
        channels  = db.get_active_forced_joins()
        is_active = db.get_setting("force_join_active") == "1"
        await _send(user_id, "✅ کانال از لیست جوین اجباری حذف شد.",
                    inline_keypad=kb.owner_force_join_keyboard(channels, is_active))


async def _cb_admin_manage(user_id: str, parts: list):
    sub = parts[1] if len(parts) > 1 else ""

    if sub == "add":
        _set_state(user_id, ConvState.OWNER_ADD_ADMIN, {"step": AdminAddStep.USERNAME})
        await _send(user_id,
                    "➕ افزودن ادمین جدید\n\nمرحله ۱ از ۹\nیوزرنیم ادمین را وارد کنید (بدون @):")

    elif sub == "list":
        admins = db.get_all_admins(only_active=False)
        await _send(user_id, "لیست ادمین‌ها:",
                    inline_keypad=kb.owner_admin_list_keyboard(admins))

    elif sub == "stats":
        rows  = db.get_admin_leaderboard("month")
        lines = ["📊 آمار ادمین‌ها (ماه جاری)\n"]
        for r in rows:
            lines.append(f"• {r['display_name']}: {r['reg_count']} ثبتی")
        await _send(user_id, "\n".join(lines),
                    inline_keypad=kb.owner_admin_manage_keyboard())

    elif sub == "manage" and len(parts) > 2:
        adm = db.get_admin(parts[2])
        if adm:
            text = (
                f"👤 {adm['display_name']} (@{adm['username']})\n\n"
                f"📊 بازه: {adm['min_members']:,} - {adm['max_members']:,} عضو\n"
                f"🕐 شیفت: {adm['shift']}\n"
                f"📦 سقف کانال: {adm['max_channels']}\n"
                f"✅ ثبتی‌ها: {adm['total_registered']}\n"
                f"🔗 جذب‌ها: {adm['total_referrals']}\n"
                f"وضعیت: {'فعال ✅' if adm['is_active'] else 'تعلیق ⛔'}"
            )
            await _send(user_id, text,
                        inline_keypad=kb.owner_admin_detail_keyboard(
                            adm["admin_id"], bool(adm["is_active"])
                        ))

    elif sub == "suspend" and len(parts) > 2:
        db.suspend_admin(parts[2], user_id)
        await _send(user_id, "⛔ ادمین تعلیق شد.")

    elif sub == "activate" and len(parts) > 2:
        db.activate_admin(parts[2], user_id)
        await _send(user_id, "✅ ادمین فعال شد.")

    elif sub == "remove" and len(parts) > 2:
        await _send(user_id, "آیا مطمئن هستید؟",
                    inline_keypad=kb.owner_confirm_remove_admin_keyboard(parts[2]))


async def _cb_shift(user_id: str, parts: list):
    sub = parts[1] if len(parts) > 1 else ""

    if sub == "edit" and len(parts) > 2:
        await _send(user_id, "شیفت را انتخاب کنید:",
                    inline_keypad=kb.owner_shift_select_keyboard(parts[2]))

    elif sub == "set" and len(parts) > 3:
        shift_val = parts[2]
        admin_id  = parts[3]
        if admin_id != "new_admin":
            conn = db.get_conn()
            conn.execute("UPDATE admins SET shift=? WHERE admin_id=?", (shift_val, admin_id))
            conn.commit()
            conn.close()
            await _send(user_id, f"✅ شیفت به‌روز شد: {shift_val}")
        else:
            _, data = _state(user_id)
            data["shift"] = shift_val
            data["step"]  = AdminAddStep.CONFIRM
            _set_state(user_id, ConvState.OWNER_ADD_ADMIN, data)
            summary = (
                f"✅ خلاصه اطلاعات ادمین جدید:\n\n"
                f"👤 یوزرنیم: @{data.get('username')}\n"
                f"📛 نام: {data.get('display_name')}\n"
                f"📊 بازه: {data.get('min_members', 0):,} - {data.get('max_members', 0):,}\n"
                f"📢 کانال بایگانی: {data.get('archive_channel_id')}\n"
                f"🕐 شیفت: {shift_val}"
            )
            await _send(user_id, summary,
                        inline_keypad=kb.owner_admin_add_confirm_keyboard())


async def _cb_system(user_id: str, parts: list, data: dict):
    sub = parts[1] if len(parts) > 1 else ""

    if sub == "toggle_bot":
        current = db.get_setting("bot_active")
        new_val = "0" if current == "1" else "1"
        db.set_setting("bot_active", new_val)
        status = "روشن ✅" if new_val == "1" else "خاموش 🔴"
        await _send(user_id, f"وضعیت ربات: {status}",
                    inline_keypad=kb.owner_system_keyboard())

    elif sub == "broadcast":
        await _send(user_id, "هدف پیام را انتخاب کنید:",
                    inline_keypad=kb.owner_broadcast_target_keyboard())

    elif sub == "force_join":
        channels  = db.get_active_forced_joins()
        is_active = db.get_setting("force_join_active") == "1"
        await _send(user_id, "مدیریت جوین اجباری:",
                    inline_keypad=kb.owner_force_join_keyboard(channels, is_active))

    elif sub == "block_user":
        _set_state(user_id, ConvState.OWNER_IDLE, {"pending_action": "block"})
        await _send(user_id, "آیدی عددی کاربر را برای بلاک وارد کنید:")

    elif sub == "unblock_user":
        _set_state(user_id, ConvState.OWNER_IDLE, {"pending_action": "unblock"})
        await _send(user_id, "آیدی عددی کاربر را برای آنبلاک وارد کنید:")

    elif sub == "logs":
        conn = db.get_conn()
        logs = conn.execute(
            "SELECT * FROM system_logs ORDER BY created_at DESC LIMIT 20"
        ).fetchall()
        conn.close()
        lines = ["📋 آخرین ۲۰ رویداد:\n"]
        for l in logs:
            lines.append(
                f"• {l['event_type']} | {l['actor_id']} → {l['target_id']} | {l['created_at'][:16]}"
            )
        await _send(user_id, "\n".join(lines) or "لاگی یافت نشد.",
                    inline_keypad=kb.owner_system_keyboard())


async def _cb_tariff(user_id: str, parts: list):
    sub = parts[1] if len(parts) > 1 else ""

    if sub == "add":
        _set_state(user_id, ConvState.OWNER_SET_TARIFF, {"tariff_step": "label"})
        await _send(user_id, "نام پلن را وارد کنید (مثلاً: پایه):")

    elif sub == "toggle" and len(parts) > 2:
        tariff_id = int(parts[2])
        conn = db.get_conn()
        t = conn.execute("SELECT is_active FROM tariffs WHERE id=?", (tariff_id,)).fetchone()
        if t:
            new_val = 0 if t["is_active"] else 1
            conn.execute("UPDATE tariffs SET is_active=? WHERE id=?", (new_val, tariff_id))
            conn.commit()
        tariffs = conn.execute("SELECT * FROM tariffs ORDER BY min_members").fetchall()
        conn.close()
        await _send(user_id, "✅ وضعیت تعرفه تغییر کرد.",
                    inline_keypad=kb.owner_tariff_keyboard(tariffs))

    elif sub == "edit" and len(parts) > 2:
        tariff_id = int(parts[2])
        conn = db.get_conn()
        t = conn.execute("SELECT * FROM tariffs WHERE id=?", (tariff_id,)).fetchone()
        conn.close()
        if t:
            is_active = bool(t["is_active"])
            text = (
                f"تعرفه: {t.get('label', '—')}\n"
                f"بازه: {t['min_members']:,} - {t['max_members']:,}\n"
                f"قیمت: {t['price']:,} تومان\n"
                f"وضعیت: {'فعال ✅' if is_active else 'غیرفعال ❌'}"
            )
            await _send(user_id, text,
                        inline_keypad=kb.owner_tariff_detail_keyboard(tariff_id, is_active))

    elif sub == "price" and len(parts) > 2:
        # ویرایش قیمت تعرفه
        tariff_id = int(parts[2])
        _set_state(user_id, ConvState.OWNER_SET_TARIFF,
                   {"tariff_step": "edit_price", "tariff_id": tariff_id})
        await _send(user_id, "قیمت جدید (تومان) را وارد کنید:")

    elif sub == "range" and len(parts) > 2:
        # ویرایش بازه عضو تعرفه
        tariff_id = int(parts[2])
        _set_state(user_id, ConvState.OWNER_SET_TARIFF,
                   {"tariff_step": "edit_range_min", "tariff_id": tariff_id})
        await _send(user_id, "حداقل عضو جدید را وارد کنید:")

    elif sub == "delete" and len(parts) > 2:
        tariff_id = int(parts[2])
        ok = db.delete_tariff(tariff_id)
        conn = db.get_conn()
        tariffs = conn.execute("SELECT * FROM tariffs ORDER BY min_members").fetchall()
        conn.close()
        msg_text = "✅ تعرفه حذف شد." if ok else "❌ خطا در حذف تعرفه."
        await _send(user_id, msg_text,
                    inline_keypad=kb.owner_tariff_keyboard(tariffs))


async def _cb_texts(user_id: str, parts: list):
    sub = parts[1] if len(parts) > 1 else ""

    if sub == "cat":
        category = parts[2] if len(parts) > 2 else "user"
        texts    = db.get_all_texts()
        await _send(user_id, f"متن‌های دسته {category}:",
                    inline_keypad=kb.owner_texts_list_keyboard(texts, category))

    elif sub == "edit":
        key = parts[2] if len(parts) > 2 else ""
        conn = db.get_conn()
        t = conn.execute("SELECT * FROM texts WHERE key=?", (key,)).fetchone()
        conn.close()
        if t:
            var_hint = f"\nمتغیرهای قابل استفاده: {t['variables']}" if t["variables"] else ""
            await _send(user_id,
                        f"📝 {t['description'] or key}\n\nمتن فعلی:\n{t['value']}{var_hint}",
                        inline_keypad=kb.owner_text_edit_keyboard(key))

    elif sub == "do_edit":
        key = parts[2] if len(parts) > 2 else ""
        _set_state(user_id, ConvState.OWNER_EDIT_TEXT_WAITING, {"editing_key": key})
        await _send(user_id, "متن جدید را ارسال کنید:")

    elif sub == "reset":
        key = parts[2] if len(parts) > 2 else ""
        await _send(user_id, f"آیا مطمئنید که می‌خواهید «{key}» را به پیش‌فرض برگردانید؟",
                    inline_keypad=kb.owner_confirm_text_reset_keyboard(key))


async def _cb_report_review(user_id: str, parts: list):
    sub       = parts[1] if len(parts) > 1 else ""
    report_id = int(parts[2]) if len(parts) > 2 else 0
    if sub == "approve":
        db.owner_review_report(report_id, True)
        await _send(user_id, "✅ گزارش تأیید شد.")
    elif sub == "reject":
        db.owner_review_report(report_id, False)
        await _send(user_id, "❌ گزارش رد شد.")


async def _cb_promote(user_id: str, parts: list):
    sub = parts[1] if len(parts) > 1 else ""
    if sub == "done" and len(parts) > 2:
        channel_id = int(parts[2])
        ch  = db.get_channel(channel_id)
        if ch:
            db.update_channel_status(channel_id, ChannelStatus.CONFIRMED, user_id)
            adm = db.get_admin(ch["assigned_admin_id"])
            await _send_to_archive(ch, adm)
            db.update_channel_status(channel_id, ChannelStatus.ARCHIVED, user_id)
            if adm:
                await _send(
                    ch["assigned_admin_id"],
                    db.get_text("admin_confirmed_notify",
                                channel=ch["channel_link"],
                                code=ch["registration_code"])
                )
            await _send(
                ch["owner_user_id"],
                db.get_text("reg_success",
                            channel=ch["channel_link"],
                            code=ch["registration_code"],
                            admin_username=adm["username"] if adm else "ادمین",
                            date=_persian_date())
            )
            await _send(user_id, "✅ ثبت کامل شد. بنر به کانال بایگانی ارسال شد.")


async def _send_to_archive(ch, adm) -> None:
    if not adm:
        return
    archive_channel = adm["archive_channel_id"]
    try:
        # ارسال بنر (عکس)
        if ch.get("banner_file_id"):
            await bot.send_file_by_file_id(
                chat_id=archive_channel,
                file_id=ch["banner_file_id"],
                caption=ch.get("banner_caption") or ""
            )
        # ارسال مشخصات
        await bot.send_text(
            chat_id=archive_channel,
            text=db.get_text("archive_caption",
                             channel_name=ch.get("channel_name") or ch["channel_link"],
                             channel_link=ch["channel_link"],
                             members=f"{ch['member_count']:,}",
                             views=f"{ch['avg_view']:,}",
                             topic=ch.get("topic") or "—",
                             code=ch["registration_code"],
                             user_id=ch["owner_user_id"],
                             date=_persian_date())
        )
    except Exception as e:
        logger.error(f"خطا در ارسال به بایگانی {archive_channel}: {e}")


async def _cb_queue(user_id: str, parts: list):
    sub = parts[1] if len(parts) > 1 else ""
    if sub == "view" and len(parts) > 2:
        channel_id = int(parts[2])
        ch = db.get_channel(channel_id)
        if ch:
            text = (
                f"📋 جزئیات درخواست\n\n"
                f"📌 کانال: {ch['channel_link']}\n"
                f"👥 عضو: {ch['member_count']:,}\n"
                f"👁 ویو: {ch['avg_view']:,}\n"
                f"📂 موضوع: {ch['topic']}\n"
                f"🔑 کد: {ch['registration_code']}\n"
                f"📅 تاریخ ثبت: {ch['registered_at'][:10]}"
            )
            await _send(user_id, text,
                        inline_keypad=kb.admin_request_detail_keyboard(
                            channel_id,
                            bool(ch["admin_joined"]),
                            bool(ch["admin_promoted"])
                        ))


async def _cb_request_admin(user_id: str, parts: list, data: dict):
    sub        = parts[1] if len(parts) > 1 else ""
    channel_id = int(parts[2]) if len(parts) > 2 else 0

    if sub == "joined":
        db.update_channel_status(channel_id, ChannelStatus.ADMIN_JOINED, user_id)
        ch  = db.get_channel(channel_id)
        adm = db.get_admin(user_id)
        owner_id = db.get_setting("owner_id")
        if owner_id and ch and adm:
            await _send(
                owner_id,
                db.get_text("owner_promote_msg",
                            admin_username=adm["username"],
                            channel=ch["channel_link"],
                            admin_id=user_id),
                inline_keypad=kb.owner_promote_confirm_keyboard(channel_id)
            )
        db.update_channel_status(channel_id, ChannelStatus.WAITING_OWNER, user_id)
        await _send(user_id, db.get_text("admin_promote_request"))

    elif sub == "approve":
        ch = db.get_channel(channel_id)
        if ch and ch.get("owner_confirmed"):
            adm = db.get_admin(user_id)
            await _send_to_archive(ch, adm)
            db.update_channel_status(channel_id, ChannelStatus.ARCHIVED, user_id)
            await _send(
                ch["owner_user_id"],
                db.get_text("reg_success",
                            channel=ch["channel_link"],
                            code=ch["registration_code"],
                            admin_username=adm["username"] if adm else "ادمین",
                            date=_persian_date())
            )
            await _send(user_id, "✅ کانال تأیید و به بایگانی ارسال شد.")
        else:
            await _send(user_id, "⚠️ هنوز مالک تأیید نکرده است. منتظر بمانید.")

    elif sub == "reject":
        await _send(user_id, "دلیل رد را انتخاب کنید:",
                    inline_keypad=kb.admin_reject_reason_keyboard(channel_id))

    elif sub == "reject_reason" and len(parts) > 3:
        reason_id = parts[3]
        reason_map = {
            "wrong_stats":  "آمار نادرست",
            "inactive":     "کانال غیرفعال",
            "bad_topic":    "موضوع نامناسب",
            "invalid_link": "لینک نامعتبر",
            "other":        "سایر",
        }
        reason_text = reason_map.get(reason_id, reason_id)
        ch  = db.get_channel(channel_id)
        adm = db.get_admin(user_id)
        if ch:
            db.update_channel_status(channel_id, ChannelStatus.REJECTED,
                                     user_id, reason_text)
            await _send(
                ch["owner_user_id"],
                db.get_text("reg_rejected",
                            channel=ch["channel_link"],
                            admin_username=adm["username"] if adm else "ادمین",
                            reason=reason_text)
            )
        await _send(user_id, "❌ درخواست رد شد.", keypad=kb.admin_main_keyboard())


async def _cb_request_user(user_id: str, parts: list, state: str, data: dict):
    sub        = parts[1] if len(parts) > 1 else ""
    channel_id = int(parts[2]) if len(parts) > 2 else 0

    if sub == "status":
        ch = db.get_channel(channel_id)
        if ch:
            conn = db.get_conn()
            adm = conn.execute(
                "SELECT username FROM admins WHERE admin_id=?",
                (ch["assigned_admin_id"],)
            ).fetchone()
            conn.close()
            status_fa = {
                "pending":       "🟡 در انتظار بررسی",
                "admin_joined":  "🔵 ادمین در حال اقدام",
                "waiting_owner": "🔵 در انتظار تأیید مالک",
                "confirmed":     "🟢 تأیید شده",
                "archived":      "✅ ثبت کامل",
                "rejected":      "❌ رد شده",
                "cancelled":     "⛔ لغو شده",
            }.get(ch["status"], ch["status"])
            text = (
                f"📋 وضعیت کانال\n\n"
                f"📌 {ch['channel_link']}\n"
                f"🔑 کد: {ch['registration_code']}\n"
                f"👤 ادمین مسئول: @{adm['username'] if adm else '—'}\n"
                f"📊 وضعیت: {status_fa}"
            )
            if ch.get("rejection_reason"):
                text += f"\n📋 دلیل رد: {ch['rejection_reason']}"
            await _send(user_id, text,
                        inline_keypad=kb.user_request_detail_keyboard(channel_id))

    elif sub == "cancel":
        await _send(user_id, "آیا مطمئنید؟",
                    inline_keypad=kb.user_confirm_cancel_request_keyboard(channel_id))


async def _cb_channel_manage(user_id: str, parts: list, data: dict):
    sub        = parts[1] if len(parts) > 1 else ""
    channel_id = int(parts[2]) if len(parts) > 2 else 0

    if sub == "manage":
        ch = db.get_channel(channel_id)
        if ch:
            await _send(user_id,
                        f"📦 {ch['registration_code']} | {ch['channel_link']}\n"
                        f"👥 {ch['member_count']:,} عضو | ⚠️ {ch['warning_count']} اخطار",
                        inline_keypad=kb.admin_channel_detail_keyboard(
                            channel_id, ch["warning_count"]
                        ))

    elif sub == "warn":
        level = int(parts[2]) if len(parts) > 2 else 1
        ch_id = int(parts[3]) if len(parts) > 3 else 0
        await _send(user_id, f"دلیل اخطار سطح {level} را انتخاب کنید:",
                    inline_keypad=kb.admin_warning_reason_keyboard(ch_id, level))

    elif sub == "warn_reason" and len(parts) > 4:
        ch_id     = int(parts[2])
        level     = int(parts[3])
        reason_id = parts[4]
        reason_map = {
            "no_exchange": "عدم تبادل به موقع",
            "stats_drop":  "کاهش آمار",
            "no_response": "عدم پاسخگویی",
            "rule_break":  "نقض قوانین",
            "other":       "سایر",
        }
        reason_text = reason_map.get(reason_id, reason_id)
        _set_state(user_id, ConvState.ADMIN_WARNING_REASON,
                   {"channel_id": ch_id, "level": level, "reason_id": reason_text})
        await _send(user_id, "توضیح بیشتری بنویسید (یا دکمه ارسال را بزنید):")

    elif sub == "warn_history":
        warnings = db.get_channel_warnings(channel_id)
        if not warnings:
            await _send(user_id, "اخطاری ثبت نشده است.")
            return
        lines = ["📋 تاریخچه اخطارها:\n"]
        for w in warnings:
            status = "✅ حل شده" if w["is_resolved"] else "⚠️ فعال"
            lines.append(f"• سطح {w['level']} | {w['reason']} | {w['issued_at'][:10]} | {status}")
        await _send(user_id, "\n".join(lines))

    elif sub == "remove":
        await _send(user_id, "آیا مطمئنید که این کانال را از لیست حذف کنید؟",
                    inline_keypad=kb.admin_confirm_remove_channel_keyboard(channel_id))


async def _cb_confirm(user_id: str, role: str, parts: list, data: dict):
    sub    = parts[1] if len(parts) > 1 else ""
    obj_id = parts[2] if len(parts) > 2 else ""

    if sub == "admin_remove" and role == UserRole.OWNER:
        db.remove_admin(obj_id, user_id)
        await _send(user_id, "✅ ادمین با موفقیت حذف شد.",
                    inline_keypad=kb.owner_admin_manage_keyboard())

    elif sub == "admin_add" and role == UserRole.OWNER:
        _, d = _state(user_id)
        success = db.add_admin(
            admin_id=d.get("admin_id", ""),
            username=d.get("username", ""),
            display_name=d.get("display_name", ""),
            level=1,
            min_members=d.get("min_members", 0),
            max_members=d.get("max_members", 0),
            archive_channel_id=d.get("archive_channel_id", ""),
            shift=d.get("shift", "fulltime"),
            max_channels=int(db.get_setting("max_channels_per_admin") or 40),
            added_by=user_id
        )
        if success:
            await _send(user_id, f"✅ ادمین @{d.get('username')} با موفقیت اضافه شد.",
                        inline_keypad=kb.owner_admin_manage_keyboard())
        else:
            await _send(user_id, "❌ خطا در افزودن ادمین. لطفاً مجدداً تلاش کنید.")
        _reset_state(user_id)

    elif sub == "text_reset" and role == UserRole.OWNER:
        db.reset_text(obj_id)
        await _send(user_id, f"✅ متن «{obj_id}» به پیش‌فرض برگشت.")

    elif sub == "req_cancel":
        channel_id = int(obj_id)
        ch = db.get_channel(channel_id)
        if ch and ch["owner_user_id"] == user_id:
            db.update_channel_status(channel_id, ChannelStatus.CANCELLED, user_id)
            await _send(user_id, "✅ درخواست لغو شد.", keypad=kb.user_main_keyboard())

    elif sub == "ch_remove":
        channel_id = int(obj_id)
        ch  = db.get_channel(channel_id)
        adm = db.get_admin(user_id)
        if ch:
            db.update_channel_status(channel_id, ChannelStatus.REJECTED,
                                     user_id, "حذف از لیست توسط ادمین")
            await _send(
                ch["owner_user_id"],
                db.get_text("channel_removed",
                            channel=ch["channel_link"],
                            code=ch["registration_code"],
                            admin_username=adm["username"] if adm else "ادمین",
                            reason="حذف از لیست")
            )
        await _send(user_id, "✅ کانال از لیست حذف شد.",
                    keypad=kb.admin_main_keyboard())


async def _cb_reg_confirm(user_id: str, state: str, data: dict):
    if state != ConvState.REG_CONFIRM:
        return

    member_count = data.get("member_count", 0)
    admin        = db.find_admin_for_members(member_count)

    if not admin:
        await _send(
            user_id,
            "⚠️ در حال حاضر ادمین مناسب برای آمار شما در دسترس نیست.\n"
            "درخواست شما ثبت شد و به زودی بررسی خواهد شد."
        )
        _reset_state(user_id)
        return

    channel_id = db.create_channel_request(
        channel_link=data.get("channel_link", ""),
        channel_name=data.get("channel_link", ""),
        member_count=member_count,
        avg_view=data.get("avg_view", 0),
        topic=data.get("topic", "سایر"),
        banner_file_id=data.get("banner_file_id", ""),
        banner_caption=data.get("banner_caption", ""),
        owner_user_id=user_id,
        assigned_admin_id=admin["admin_id"]
    )

    if not channel_id:
        await _send(user_id, "❌ خطا در ثبت درخواست. لطفاً مجدداً تلاش کنید.")
        return

    position  = db.get_queue_position(channel_id)
    wait_time = db.estimate_wait_time(admin["admin_id"], position)

    await _send(
        user_id,
        db.get_text("reg_queued",
                    channel=data.get("channel_link", ""),
                    admin_username=admin["username"],
                    position=position,
                    wait_time=wait_time),
        keypad=kb.user_main_keyboard()
    )

    ch = db.get_channel(channel_id)
    if ch:
        await _send(
            admin["admin_id"],
            db.get_text("admin_new_request",
                        channel=ch["channel_link"],
                        members=f"{ch['member_count']:,}",
                        views=f"{ch['avg_view']:,}",
                        topic=ch["topic"],
                        position=position)
        )

    _reset_state(user_id)


async def _do_broadcast(user_id: str, text: str, target: str):
    conn = db.get_conn()
    if target == "admins":
        rows = conn.execute("SELECT admin_id FROM admins WHERE is_active=1").fetchall()
        ids  = [r["admin_id"] for r in rows]
    elif target == "users":
        rows = conn.execute(
            "SELECT user_id FROM users WHERE role='user' AND is_blocked=0"
        ).fetchall()
        ids = [r["user_id"] for r in rows]
    else:
        rows = conn.execute("SELECT user_id FROM users WHERE is_blocked=0").fetchall()
        ids  = [r["user_id"] for r in rows]
    conn.close()

    sent, failed = 0, 0
    for uid in ids:
        try:
            await bot.send_text(chat_id=uid, text=text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    await _send(user_id,
                f"✅ پیام همگانی ارسال شد.\nموفق: {sent} | ناموفق: {failed}")


# ════════════════════════════════════════════════════════════
#  اجرای ربات
# ════════════════════════════════════════════════════════════

async def main():
    logger.info(f"ربات تبادل نسخه {config.BOT_VERSION} در حال راه‌اندازی...")
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())
