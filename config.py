# ============================================================
# config.py — تنظیمات مرکزی ربات تبادل روبیکا
# ============================================================

import os


# ─── اطلاعات ربات ────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("RUBIKA_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# شناسه یکتای مالک. این مقدار از یوزرنیم امن‌تر است.
OWNER_ID: str = os.getenv("RUBIKA_OWNER_ID", "").strip()

# یوزرنیم مالک برای سازگاری با نسخه قبلی.
OWNER_USERNAME: str = os.getenv(
    "RUBIKA_OWNER_USERNAME",
    "owner_username_here",
).strip().lstrip("@")


# ─── دیتابیس و لاگ ──────────────────────────────────────────
DATABASE_FILE: str = os.getenv("RUBIKA_DATABASE_FILE", "bot.db")
LOG_LEVEL: str = os.getenv("RUBIKA_LOG_LEVEL", "INFO").upper()
LOG_TO_FILE: bool = os.getenv("RUBIKA_LOG_TO_FILE", "1") == "1"
LOG_FILE: str = os.getenv("RUBIKA_LOG_FILE", "bot.log")


# ─── محدودیت‌ها ─────────────────────────────────────────────
DEFAULT_MAX_CHANNELS_PER_ADMIN: int = int(
    os.getenv("MAX_CHANNELS_PER_ADMIN", "40")
)
DEFAULT_WARNING_EXPIRE_DAYS: int = int(
    os.getenv("WARNING_EXPIRE_DAYS", "7")
)
ADMIN_REQUEST_TIMEOUT_MINUTES: int = int(
    os.getenv("ADMIN_REQUEST_TIMEOUT_MINUTES", "30")
)

BOT_VERSION: str = "1.1.0"


# ════════════════════════════════════════════════════════════
# وضعیت درخواست کانال
# ════════════════════════════════════════════════════════════

class ChannelStatus:
    PENDING = "pending"
    ADMIN_JOINED = "admin_joined"
    WAITING_OWNER = "waiting_owner"
    CONFIRMED = "confirmed"
    ARCHIVED = "archived"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class WarningLevel:
    LEVEL_1 = 1
    LEVEL_2 = 2


class UserRole:
    OWNER = "owner"
    ADMIN = "admin"
    USER = "user"


# ════════════════════════════════════════════════════════════
# ماشین وضعیت مکالمه
# ════════════════════════════════════════════════════════════

class ConvState:
    IDLE = "idle"

    REG_WAITING_LINK = "reg_waiting_link"
    REG_WAITING_MEMBERS = "reg_waiting_members"
    REG_WAITING_VIEWS = "reg_waiting_views"
    REG_WAITING_TOPIC = "reg_waiting_topic"
    REG_WAITING_BANNER = "reg_waiting_banner"
    REG_CONFIRM = "reg_confirm"

    ADMIN_IDLE = "admin_idle"
    ADMIN_REPORT_WRITING = "admin_report_writing"
    ADMIN_WARNING_REASON = "admin_warning_reason"
    ADMIN_REJECT_REASON = "admin_reject_reason"

    OWNER_IDLE = "owner_idle"
    OWNER_ADD_ADMIN = "owner_add_admin_step"
    OWNER_EDIT_TEXT_WAITING = "owner_edit_text_waiting"
    OWNER_ADD_FORCE_CHANNEL = "owner_add_force_channel"
    OWNER_BROADCAST_WRITING = "owner_broadcast_writing"
    OWNER_SET_TARIFF = "owner_set_tariff"
    OWNER_SET_MAX_CHANNELS = "owner_set_max_channels"


# ════════════════════════════════════════════════════════════
# مراحل افزودن ادمین
# ════════════════════════════════════════════════════════════

class AdminAddStep:
    USERNAME = "username"
    ADMIN_ID = "admin_id"
    DISPLAY_NAME = "display_name"
    LEVEL = "level"
    MIN_MEMBERS = "min_members"
    MAX_MEMBERS = "max_members"
    ARCHIVE_CHANNEL = "archive_ch"
    SHIFT = "shift"
    CONFIRM = "confirm"


class Shift:
    MORNING = "morning"
    AFTERNOON = "afternoon"
    NIGHT = "night"
    FULLTIME = "fulltime"


DEFAULT_TOPICS = [
    "طنز و سرگرمی",
    "اخبار و سیاست",
    "فناوری",
    "کسب‌وکار",
    "آموزشی",
    "ورزشی",
    "هنر و موسیقی",
    "سبک زندگی",
    "گردشگری",
    "سایر",
]
