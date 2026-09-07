# ============================================================
#  config.py — تنظیمات مرکزی ربات تبادل روبیکا
#  هیچ مقدار حساسی نباید مستقیم در کد باشد؛
#  توکن و یوزرنیم مالک اینجا تنظیم می‌شوند.
# ============================================================

# ─── اطلاعات ربات ────────────────────────────────────────────
BOT_TOKEN: str = "YOUR_BOT_TOKEN_HERE"

# ─── شناسه مالک (یوزرنیم بدون @) ────────────────────────────
# مثال: اگر آدرس روبیکا شما rubika.ir/u/john باشد → "john"
OWNER_USERNAME: str = "owner_username_here"

# ─── نام فایل دیتابیس ────────────────────────────────────────
DATABASE_FILE: str = "bot.db"

# ─── حداکثر کانال برای هر ادمین (پیش‌فرض) ───────────────────
# مالک می‌تواند این مقدار را از پنل تغییر دهد
DEFAULT_MAX_CHANNELS_PER_ADMIN: int = 40

# ─── مدت زمان اعتبار اخطار (روز) ────────────────────────────
DEFAULT_WARNING_EXPIRE_DAYS: int = 7

# ─── حداکثر زمان انتظار ادمین روی یک درخواست (دقیقه) ────────
# اگر ادمین بیشتر از این مقدار روی یک درخواست بماند → اخطار
ADMIN_REQUEST_TIMEOUT_MINUTES: int = 30

# ─── نسخه ربات ───────────────────────────────────────────────
BOT_VERSION: str = "1.0.0"

# ─── تنظیمات لاگ ─────────────────────────────────────────────
LOG_LEVEL: str = "INFO"           # DEBUG | INFO | WARNING | ERROR
LOG_TO_FILE: bool = True
LOG_FILE: str = "bot.log"

# ============================================================
#  ثوابت داخلی — تغییر ندهید مگر بدانید چه می‌کنید
# ============================================================

# وضعیت‌های ممکن برای یک درخواست کانال
class ChannelStatus:
    PENDING         = "pending"           # در انتظار اقدام ادمین
    ADMIN_JOINED    = "admin_joined"      # ادمین عضو شده، هنوز ادمین نشده
    WAITING_OWNER   = "waiting_owner"     # در انتظار تأیید ادمین شدن توسط مالک
    CONFIRMED       = "confirmed"         # تأیید شده — بنر ارسال خواهد شد
    ARCHIVED        = "archived"          # بنر ارسال شد، ثبت کامل است
    REJECTED        = "rejected"          # رد شده
    CANCELLED       = "cancelled"         # لغو شده توسط کاربر

# سطوح اخطار
class WarningLevel:
    LEVEL_1 = 1    # اخطار اول — هشدار
    LEVEL_2 = 2    # اخطار دوم — جدی

# نقش‌های کاربری
class UserRole:
    OWNER = "owner"
    ADMIN = "admin"
    USER  = "user"

# وضعیت‌های مکالمه (State Machine)
# هر کاربر در هر لحظه یک state دارد که در دیتابیس نگه داشته می‌شود
class ConvState:
    # ─── کاربر عادی ─────────────────────────────────────────
    IDLE                    = "idle"
    REG_WAITING_LINK        = "reg_waiting_link"
    REG_WAITING_MEMBERS     = "reg_waiting_members"
    REG_WAITING_VIEWS       = "reg_waiting_views"
    REG_WAITING_TOPIC       = "reg_waiting_topic"
    REG_WAITING_BANNER      = "reg_waiting_banner"
    REG_CONFIRM             = "reg_confirm"

    # ─── ادمین ───────────────────────────────────────────────
    ADMIN_IDLE              = "admin_idle"
    ADMIN_REPORT_WRITING    = "admin_report_writing"
    ADMIN_WARNING_REASON    = "admin_warning_reason"
    ADMIN_REJECT_REASON     = "admin_reject_reason"

    # ─── مالک ────────────────────────────────────────────────
    OWNER_IDLE              = "owner_idle"
    OWNER_ADD_ADMIN         = "owner_add_admin_step"
    OWNER_EDIT_TEXT_WAITING = "owner_edit_text_waiting"
    OWNER_ADD_FORCE_CHANNEL = "owner_add_force_channel"
    OWNER_BROADCAST_WRITING = "owner_broadcast_writing"
    OWNER_SET_TARIFF        = "owner_set_tariff"
    OWNER_SET_MAX_CHANNELS  = "owner_set_max_channels"

# مراحل افزودن ادمین توسط مالک (sub-state داخل OWNER_ADD_ADMIN)
class AdminAddStep:
    USERNAME        = "username"       # ۱. یوزرنیم ادمین
    DISPLAY_NAME    = "display_name"   # ۲. نام نمایشی
    LEVEL           = "level"          # ۳. سطح / تخصص (بازه آماری)
    MIN_MEMBERS     = "min_members"    # ۴. حداقل عضو کانال‌های مرتبط
    MAX_MEMBERS     = "max_members"    # ۵. حداکثر عضو کانال‌های مرتبط
    ARCHIVE_CHANNEL = "archive_ch"     # ۶. آیدی کانال بایگانی اختصاصی
    SHIFT           = "shift"          # ۷. شیفت کاری (صبح/عصر/شب)
    CONFIRM         = "confirm"        # ۸. تأیید نهایی

# شیفت‌های کاری
class Shift:
    MORNING   = "morning"    # صبح
    AFTERNOON = "afternoon"  # عصر
    NIGHT     = "night"      # شب
    FULLTIME  = "fulltime"   # تمام وقت

# موضوعات کانال (قابل گسترش از پنل مالک)
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
