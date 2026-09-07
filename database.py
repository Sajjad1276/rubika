# ============================================================
#  database.py — لایه دیتابیس ربات تبادل روبیکا
#  SQLite + aiosqlite برای عملیات async
#  تمام توابع CRUD اینجا تعریف می‌شوند
# ============================================================

import sqlite3
import logging
from datetime import datetime
from typing import Optional

from config import (
    DATABASE_FILE, DEFAULT_MAX_CHANNELS_PER_ADMIN,
    DEFAULT_TOPICS, ChannelStatus
)

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════
#  متن‌های پیش‌فرض ربات
#  کلید → متن پیش‌فرض | متغیرهای قابل استفاده در توضیح
# ════════════════════════════════════════════════════════════
DEFAULT_TEXTS: dict[str, str] = {
    # ─── پنل کاربر ─────────────────────────────────────────
    "welcome":
        "سلام {name} عزیز! 👋\nبه ربات تبادل خوش آمدید.",
    "user_menu":
        "از منوی زیر انتخاب کنید:",
    "reg_ask_link":
        "🔗 لینک کانال خود را ارسال کنید:\n(مثال: @mychannel)",
    "reg_ask_members":
        "👥 تعداد دقیق اعضای کانال را وارد کنید:",
    "reg_ask_views":
        "👁 میانگین بازدید پست‌های کانال را وارد کنید:",
    "reg_ask_topic":
        "📂 موضوع کانال خود را انتخاب کنید:",
    "reg_ask_banner":
        "🖼 پست بنر را ارسال کنید:\n(عکس + متن باید باهم باشند)",
    "reg_confirm":
        "✅ اطلاعات دریافت شد!\n\nکانال: {channel}\nعضو: {members}\nویو: {views}\n\nبرای تأیید نهایی دکمه زیر را بزنید.",
    "reg_queued":
        "⏳ درخواست شما ثبت شد.\n\n📌 کانال: {channel}\n👤 ادمین مسئول: @{admin_username}\n📍 موقعیت در صف: نفر {position}\n⏱ زمان تخمینی: {wait_time} دقیقه",
    "reg_success":
        "🎉 کانال شما با موفقیت ثبت شد!\n\n📌 کانال: {channel}\n🔑 کد ثبت: {code}\n👤 ادمین مسئول: @{admin_username}\n📅 تاریخ: {date}",
    "reg_rejected":
        "❌ درخواست کانال {channel} رد شد.\n\n👤 ادمین مسئول: @{admin_username}\n📋 دلیل: {reason}\n\nمی‌توانید مجدداً اقدام کنید.",
    "status_check":
        "📊 وضعیت درخواست‌های شما:",
    "no_requests":
        "شما هنوز درخواستی ثبت نکرده‌اید.",
    "profile_text":
        "👤 پروفایل شما:\n\n🗓 تاریخ عضویت: {join_date}\n📦 کانال‌های ثبت‌شده: {channel_count}\n⚠️ تعداد اخطار: {warning_count}\n🔗 لینک معرف: {referral_link}",
    "referral_link_text":
        "🔗 لینک معرف شما:\n{referral_link}\n\nهر بار که کاربری از این لینک وارد شود، به حساب شما ثبت می‌شود.",

    # ─── اخطار و حذف ────────────────────────────────────────
    "warning_level1":
        "⚠️ اخطار سطح اول برای کانال {channel}\n\n🔑 کد ثبت: {code}\n👤 ادمین مسئول: @{admin_username}\n📋 دلیل: {reason}\n\nلطفاً ظرف {days} روز مشکل را برطرف کنید.",
    "warning_level2":
        "🔴 اخطار سطح دوم برای کانال {channel}\n\n🔑 کد ثبت: {code}\n👤 ادمین مسئول: @{admin_username}\n📋 دلیل: {reason}\n\nدر صورت عدم رفع مشکل، کانال از لیست حذف خواهد شد.",
    "channel_removed":
        "🚫 کانال {channel} از لیست حذف شد.\n\n🔑 کد ثبت: {code}\n👤 ادمین مسئول: @{admin_username}\n📋 دلیل: {reason}",

    # ─── پنل ادمین ──────────────────────────────────────────
    "admin_welcome":
        "سلام {name} عزیز! 🛡\nپنل مدیریت ادمین:",
    "admin_new_request":
        "📬 درخواست جدید در صف شما\n\n📌 کانال: {channel}\n👥 عضو: {members}\n👁 ویو: {views}\n📂 موضوع: {topic}\n📍 موقعیت در صف: {position}",
    "admin_join_reminder":
        "⚙️ لطفاً در کانال {channel} عضو شوید\nسپس دکمه زیر را بزنید.",
    "admin_promote_request":
        "✅ عضویت تأیید شد.\nاکنون منتظر ادمین شدن توسط مالک باشید.",
    "owner_promote_msg":
        "⚙️ درخواست ادمین شدن\n\nادمین: @{admin_username}\nکانال: {channel}\nآیدی ادمین: {admin_id}\n\nلطفاً با دسترسی‌های زیر ادمین کنید:\n✅ ارسال پیام\n✅ حذف پیام\n✅ ویرایش پیام",
    "admin_confirmed_notify":
        "✅ کانال {channel} با کد {code} تأیید شد.\nبنر به کانال بایگانی ارسال شد.",
    "admin_report_prompt":
        "📝 گزارش کار امروز خود را ارسال کنید:\n\nفرمت پیشنهادی:\n• تعداد ثبتی: ...\n• تعداد رد شده: ...\n• مشکلات: ...",
    "admin_report_sent":
        "✅ گزارش شما با موفقیت برای مالک ارسال شد.",
    "admin_timeout_warning":
        "⏰ شما {minutes} دقیقه است روی درخواست {code} هستید.\nلطفاً هرچه سریع‌تر اقدام کنید.",

    # ─── پنل مالک ───────────────────────────────────────────
    "owner_welcome":
        "سلام مالک عزیز! 👑\nپنل مدیریت:",
    "owner_report_received":
        "📊 گزارش روزانه از @{admin_username}\n\n{report_text}\n\n📅 تاریخ: {date}",

    # ─── سیستمی ────────────────────────────────────────────
    "maintenance_msg":
        "🔧 ربات در حال تعمیر است.\nبه زودی بازمی‌گردیم.",
    "force_join_msg":
        "برای استفاده از ربات ابتدا در کانال‌های زیر عضو شوید:",
    "force_join_btn":
        "✅ عضو شدم",
    "blocked_msg":
        "⛔ دسترسی شما به ربات مسدود شده است.",
    "invalid_input":
        "⚠️ ورودی نامعتبر است. لطفاً مجدداً تلاش کنید.",
    "back_btn":
        "🔙 بازگشت",
    "confirm_btn":
        "✅ تأیید",
    "cancel_btn":
        "❌ لغو",

    # ─── فرمت پیام کانال بایگانی ───────────────────────────
    "archive_caption":
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📌 نام کانال : {channel_name}\n"
        "🔗 لینک : {channel_link}\n"
        "👥 تعداد عضو : {members}\n"
        "👁 میانگین ویو : {views}\n"
        "📂 موضوع : {topic}\n"
        "🔑 کد ثبت : {code}\n"
        "👤 ثبت‌کننده : {user_id}\n"
        "📅 تاریخ ثبت : {date}\n"
        "━━━━━━━━━━━━━━━━━━━━",
}


# ════════════════════════════════════════════════════════════
#  راه‌اندازی و ساخت جداول
# ════════════════════════════════════════════════════════════

def get_conn() -> sqlite3.Connection:
    """اتصال به دیتابیس با تنظیمات بهینه."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row          # دسترسی به ستون‌ها با نام
    conn.execute("PRAGMA journal_mode=WAL") # عملکرد بهتر در write همزمان
    conn.execute("PRAGMA foreign_keys=ON")  # اعمال کلیدهای خارجی
    return conn


def init_db() -> None:
    """ساخت تمام جداول در صورت عدم وجود."""
    conn = get_conn()
    cur = conn.cursor()

    # ─── کاربران ────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id         TEXT PRIMARY KEY,   -- آیدی عددی کاربر (string)
            username        TEXT,               -- یوزرنیم روبیکا
            display_name    TEXT,               -- نام نمایشی
            role            TEXT DEFAULT 'user',-- owner | admin | user
            state           TEXT DEFAULT 'idle',-- وضعیت مکالمه جاری
            state_data      TEXT DEFAULT '{}',  -- داده‌های موقت state (JSON)
            is_blocked      INTEGER DEFAULT 0,  -- ۰=فعال، ۱=بلاک
            referral_by     TEXT,               -- آیدی معرف
            referral_code   TEXT UNIQUE,        -- کد معرف اختصاصی
            joined_at       TEXT DEFAULT (date('now')),
            last_seen       TEXT,
            FOREIGN KEY (referral_by) REFERENCES users(user_id)
        )
    """)

    # ─── ادمین‌ها ────────────────────────────────────────────
    # هر رکورد اینجا، یک ادمین با مشخصات کامل است
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            admin_id            TEXT PRIMARY KEY, -- همان user_id
            username            TEXT NOT NULL,    -- یوزرنیم (بدون @)
            display_name        TEXT NOT NULL,    -- نام نمایشی
            level               INTEGER DEFAULT 1,-- سطح ادمین (۱/۲/۳)
            min_members         INTEGER NOT NULL, -- حداقل عضو کانال‌های مرتبط
            max_members         INTEGER NOT NULL, -- حداکثر عضو کانال‌های مرتبط
            archive_channel_id  TEXT NOT NULL,    -- آیدی کانال بایگانی اختصاصی
            shift               TEXT DEFAULT 'fulltime',
            max_channels        INTEGER DEFAULT 40,
            is_active           INTEGER DEFAULT 1,-- ۱=فعال، ۰=تعلیق
            total_registered    INTEGER DEFAULT 0,-- کل ثبتی‌ها (برای رنکینگ)
            total_referrals     INTEGER DEFAULT 0,-- کل جذب‌ها (برای رنکینگ)
            added_at            TEXT DEFAULT (date('now')),
            added_by            TEXT,             -- user_id مالک
            FOREIGN KEY (admin_id) REFERENCES users(user_id)
        )
    """)

    # ─── کانال‌های ثبت‌شده ──────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            registration_code   TEXT UNIQUE NOT NULL, -- مثل A-07
            channel_link        TEXT NOT NULL,
            channel_name        TEXT,
            member_count        INTEGER NOT NULL,
            avg_view            INTEGER NOT NULL,
            topic               TEXT,
            banner_file_id      TEXT NOT NULL,    -- file_id بنر در روبیکا
            banner_caption      TEXT,             -- متن همراه بنر
            owner_user_id       TEXT NOT NULL,    -- کاربر ثبت‌کننده
            assigned_admin_id   TEXT NOT NULL,    -- ادمین مسئول
            admin_joined        INTEGER DEFAULT 0,-- ادمین عضو شده؟
            admin_promoted      INTEGER DEFAULT 0,-- ادمین شده؟
            owner_confirmed     INTEGER DEFAULT 0,-- مالک تأیید کرده؟
            queue_position      INTEGER DEFAULT 0,
            status              TEXT DEFAULT 'pending',
            warning_count       INTEGER DEFAULT 0,
            registered_at       TEXT DEFAULT (datetime('now')),
            confirmed_at        TEXT,
            archived_at         TEXT,
            rejected_at         TEXT,
            rejection_reason    TEXT,
            FOREIGN KEY (owner_user_id)     REFERENCES users(user_id),
            FOREIGN KEY (assigned_admin_id) REFERENCES admins(admin_id)
        )
    """)

    # ─── لیست کانال‌هایی که هر ادمین توشون ادمین شده ────────
    # (کانال‌های طرف تبادل — نه کانال بایگانی)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admin_channel_list (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id        TEXT NOT NULL,
            channel_link    TEXT NOT NULL,
            channel_name    TEXT,
            member_count    INTEGER,
            added_at        TEXT DEFAULT (date('now')),
            last_forward    TEXT,               -- آخرین زمان فوروارد
            total_forwards  INTEGER DEFAULT 0,
            is_active       INTEGER DEFAULT 1,
            FOREIGN KEY (admin_id) REFERENCES admins(admin_id)
        )
    """)

    # ─── صف درخواست‌ها ──────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS queue (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id        TEXT NOT NULL,
            channel_id      INTEGER NOT NULL,
            position        INTEGER NOT NULL,
            is_active       INTEGER DEFAULT 1, -- درخواست جاری ادمین
            created_at      TEXT DEFAULT (datetime('now')),
            started_at      TEXT,              -- وقتی ادمین شروع کرد
            FOREIGN KEY (admin_id)    REFERENCES admins(admin_id),
            FOREIGN KEY (channel_id) REFERENCES channels(id)
        )
    """)

    # ─── اخطارها ────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS warnings (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_registration_id INTEGER NOT NULL,
            admin_id                TEXT NOT NULL,
            level                   INTEGER NOT NULL, -- 1 یا 2
            reason                  TEXT NOT NULL,
            issued_at               TEXT DEFAULT (datetime('now')),
            expires_at              TEXT,
            is_resolved             INTEGER DEFAULT 0,
            resolved_at             TEXT,
            FOREIGN KEY (channel_registration_id) REFERENCES channels(id),
            FOREIGN KEY (admin_id) REFERENCES admins(admin_id)
        )
    """)

    # ─── گزارش روزانه ادمین‌ها ──────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_reports (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id        TEXT NOT NULL,
            report_text     TEXT NOT NULL,
            report_date     TEXT DEFAULT (date('now')),
            registered_count INTEGER DEFAULT 0,
            rejected_count  INTEGER DEFAULT 0,
            owner_feedback  TEXT,
            owner_approved  INTEGER,          -- NULL=بررسی نشده، 1=تأیید، 0=رد
            submitted_at    TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (admin_id) REFERENCES admins(admin_id)
        )
    """)

    # ─── تعرفه‌ها ────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tariffs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            label       TEXT NOT NULL,        -- نام پلن (مثل: پایه، حرفه‌ای)
            min_members INTEGER NOT NULL,
            max_members INTEGER NOT NULL,
            price       INTEGER NOT NULL,     -- قیمت (تومان)
            is_active   INTEGER DEFAULT 1,
            created_at  TEXT DEFAULT (date('now')),
            updated_at  TEXT
        )
    """)

    # ─── جوین اجباری ────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS forced_joins (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id      TEXT NOT NULL,    -- آیدی عددی کانال
            channel_username TEXT,            -- یوزرنیم کانال
            channel_title   TEXT,
            is_active       INTEGER DEFAULT 1,
            added_at        TEXT DEFAULT (date('now'))
        )
    """)

    # ─── متن‌های قابل ویرایش ────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS texts (
            key             TEXT PRIMARY KEY,
            value           TEXT NOT NULL,
            default_value   TEXT NOT NULL,
            description     TEXT,             -- توضیح برای مالک
            variables       TEXT,             -- متغیرهای قابل استفاده (JSON آرایه)
            updated_at      TEXT,
            updated_by      TEXT
        )
    """)

    # ─── موضوعات کانال ──────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS topics (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL UNIQUE,
            is_active   INTEGER DEFAULT 1,
            sort_order  INTEGER DEFAULT 0
        )
    """)

    # ─── تنظیمات سیستم ──────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key     TEXT PRIMARY KEY,
            value   TEXT NOT NULL
        )
    """)

    # ─── لاگ رویدادها ───────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS system_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type  TEXT NOT NULL,        -- register|approve|reject|warn|remove|block|...
            actor_id    TEXT,                 -- کسی که عمل را انجام داده
            target_id   TEXT,                 -- هدف عمل (user_id یا channel_id)
            detail      TEXT,                 -- جزئیات (JSON یا متن)
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.commit()

    # بارگذاری مقادیر اولیه
    _seed_texts(conn)
    _seed_topics(conn)
    _seed_settings(conn)

    conn.close()
    logger.info("دیتابیس با موفقیت راه‌اندازی شد.")


def _seed_texts(conn: sqlite3.Connection) -> None:
    """درج متن‌های پیش‌فرض در صورت خالی بودن جدول."""
    cur = conn.cursor()
    descriptions = {
        "welcome":            ("پیام خوش‌آمدگویی", "{name}"),
        "reg_ask_link":       ("درخواست لینک کانال", ""),
        "reg_ask_members":    ("درخواست تعداد عضو", ""),
        "reg_ask_views":      ("درخواست میانگین ویو", ""),
        "reg_ask_topic":      ("درخواست موضوع", ""),
        "reg_ask_banner":     ("درخواست بنر", ""),
        "reg_confirm":        ("تأیید اطلاعات", "{channel},{members},{views}"),
        "reg_queued":         ("پیام صف", "{channel},{admin_username},{position},{wait_time}"),
        "reg_success":        ("پیام ثبت موفق", "{channel},{code},{admin_username},{date}"),
        "reg_rejected":       ("پیام رد شدن", "{channel},{admin_username},{reason}"),
        "warning_level1":     ("اخطار سطح ۱", "{channel},{code},{admin_username},{reason},{days}"),
        "warning_level2":     ("اخطار سطح ۲", "{channel},{code},{admin_username},{reason}"),
        "channel_removed":    ("پیام حذف کانال", "{channel},{code},{admin_username},{reason}"),
        "admin_new_request":  ("اطلاع‌رسانی درخواست جدید به ادمین", "{channel},{members},{views},{topic},{position}"),
        "owner_promote_msg":  ("درخواست ادمین کردن از مالک", "{admin_username},{channel},{admin_id}"),
        "archive_caption":    ("فرمت پیام کانال بایگانی", "{channel_name},{channel_link},{members},{views},{topic},{code},{user_id},{date}"),
        "maintenance_msg":    ("پیام تعمیرات", ""),
        "force_join_msg":     ("پیام جوین اجباری", ""),
        "blocked_msg":        ("پیام بلاک", ""),
    }
    for key, default_val in DEFAULT_TEXTS.items():
        desc, variables = descriptions.get(key, ("", ""))
        cur.execute("""
            INSERT OR IGNORE INTO texts (key, value, default_value, description, variables)
            VALUES (?, ?, ?, ?, ?)
        """, (key, default_val, default_val, desc, variables))
    conn.commit()


def _seed_topics(conn: sqlite3.Connection) -> None:
    """درج موضوعات پیش‌فرض."""
    cur = conn.cursor()
    for i, topic in enumerate(DEFAULT_TOPICS):
        cur.execute(
            "INSERT OR IGNORE INTO topics (title, sort_order) VALUES (?, ?)",
            (topic, i)
        )
    conn.commit()


def _seed_settings(conn: sqlite3.Connection) -> None:
    """تنظیمات پیش‌فرض سیستم."""
    defaults = {
        "bot_active":               "1",    # ربات روشن است؟
        "force_join_active":        "0",    # جوین اجباری فعال است؟
        "max_channels_per_admin":   str(DEFAULT_MAX_CHANNELS_PER_ADMIN),
        "warning_expire_days":      "7",
        "admin_timeout_minutes":    "30",
    }
    cur = conn.cursor()
    for k, v in defaults.items():
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    conn.commit()


# ════════════════════════════════════════════════════════════
#  توابع عمومی
# ════════════════════════════════════════════════════════════

def get_text(key: str, **kwargs) -> str:
    """
    دریافت متن از دیتابیس و جایگزینی متغیرها.
    مثال: get_text('welcome', name='علی')
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT value FROM texts WHERE key = ?", (key,)
    ).fetchone()
    conn.close()
    if row:
        try:
            return row["value"].format(**kwargs)
        except KeyError:
            return row["value"]
    return f"[{key}]"


def update_text(key: str, new_value: str, updated_by: str) -> bool:
    """به‌روزرسانی یک متن توسط مالک."""
    conn = get_conn()
    conn.execute("""
        UPDATE texts SET value=?, updated_at=datetime('now'), updated_by=?
        WHERE key=?
    """, (new_value, updated_by, key))
    conn.commit()
    conn.close()
    return True


def reset_text(key: str) -> bool:
    """بازگشت یک متن به مقدار پیش‌فرض."""
    conn = get_conn()
    conn.execute("""
        UPDATE texts SET value=default_value, updated_at=datetime('now')
        WHERE key=?
    """, (key,))
    conn.commit()
    conn.close()
    return True


def get_all_texts() -> list[sqlite3.Row]:
    """دریافت همه متن‌ها برای نمایش در پنل مالک."""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM texts ORDER BY key").fetchall()
    conn.close()
    return rows


def get_setting(key: str) -> Optional[str]:
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else None


def set_setting(key: str, value: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
    )
    conn.commit()
    conn.close()


# ════════════════════════════════════════════════════════════
#  مدیریت کاربران
# ════════════════════════════════════════════════════════════

def get_or_create_user(user_id: str, username: str = None,
                        display_name: str = None, referral_by: str = None) -> sqlite3.Row:
    """دریافت یا ساخت کاربر. در صورت جدید بودن، کد معرف اختصاصی ایجاد می‌شود."""
    import secrets
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        ref_code = secrets.token_urlsafe(6)
        conn.execute("""
            INSERT INTO users (user_id, username, display_name, referral_by, referral_code, last_seen)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (user_id, username, display_name, referral_by, ref_code))
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        log_event(conn, "user_join", user_id, user_id, f"referral_by={referral_by}")
    else:
        conn.execute(
            "UPDATE users SET last_seen=datetime('now'), username=? WHERE user_id=?",
            (username, user_id)
        )
        conn.commit()
    conn.close()
    return row


def get_user(user_id: str) -> Optional[sqlite3.Row]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row


def get_user_role(user_id: str) -> str:
    """تشخیص نقش کاربر: owner | admin | user"""
    row = get_user(user_id)
    return row["role"] if row else "user"


def set_user_state(user_id: str, state: str, state_data: str = "{}") -> None:
    """ذخیره وضعیت مکالمه کاربر."""
    conn = get_conn()
    conn.execute(
        "UPDATE users SET state=?, state_data=? WHERE user_id=?",
        (state, state_data, user_id)
    )
    conn.commit()
    conn.close()


def get_user_state(user_id: str) -> tuple[str, str]:
    """دریافت وضعیت و داده‌های مکالمه کاربر."""
    conn = get_conn()
    row = conn.execute(
        "SELECT state, state_data FROM users WHERE user_id=?", (user_id,)
    ).fetchone()
    conn.close()
    if row:
        return row["state"], row["state_data"]
    return "idle", "{}"


def block_user(user_id: str, actor_id: str) -> None:
    conn = get_conn()
    conn.execute("UPDATE users SET is_blocked=1 WHERE user_id=?", (user_id,))
    conn.commit()
    log_event(conn, "user_block", actor_id, user_id)
    conn.close()


def unblock_user(user_id: str, actor_id: str) -> None:
    conn = get_conn()
    conn.execute("UPDATE users SET is_blocked=0 WHERE user_id=?", (user_id,))
    conn.commit()
    log_event(conn, "user_unblock", actor_id, user_id)
    conn.close()


def is_user_blocked(user_id: str) -> bool:
    row = get_user(user_id)
    return bool(row and row["is_blocked"])


# ════════════════════════════════════════════════════════════
#  مدیریت ادمین‌ها
# ════════════════════════════════════════════════════════════

def add_admin(admin_id: str, username: str, display_name: str,
              level: int, min_members: int, max_members: int,
              archive_channel_id: str, shift: str, max_channels: int,
              added_by: str) -> bool:
    """
    افزودن ادمین جدید.
    تمام مشخصات برای routing هوشمند لازم است.
    """
    conn = get_conn()
    try:
        # ابتدا نقش کاربر را به admin تغییر بده
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username, display_name, role) VALUES (?,?,?,'admin')",
            (admin_id, username, display_name)
        )
        conn.execute(
            "UPDATE users SET role='admin' WHERE user_id=?", (admin_id,)
        )
        conn.execute("""
            INSERT OR REPLACE INTO admins
            (admin_id, username, display_name, level, min_members, max_members,
             archive_channel_id, shift, max_channels, added_by)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (admin_id, username, display_name, level, min_members, max_members,
              archive_channel_id, shift, max_channels, added_by))
        conn.commit()
        log_event(conn, "admin_add", added_by, admin_id,
                  f"range={min_members}-{max_members}")
        return True
    except Exception as e:
        logger.error(f"خطا در افزودن ادمین: {e}")
        return False
    finally:
        conn.close()


def remove_admin(admin_id: str, actor_id: str) -> bool:
    """حذف ادمین — نقش کاربر به user برمی‌گردد."""
    conn = get_conn()
    try:
        conn.execute("UPDATE admins SET is_active=0 WHERE admin_id=?", (admin_id,))
        conn.execute("UPDATE users SET role='user' WHERE user_id=?", (admin_id,))
        conn.commit()
        log_event(conn, "admin_remove", actor_id, admin_id)
        return True
    finally:
        conn.close()


def suspend_admin(admin_id: str, actor_id: str) -> None:
    """تعلیق موقت ادمین بدون حذف."""
    conn = get_conn()
    conn.execute("UPDATE admins SET is_active=0 WHERE admin_id=?", (admin_id,))
    conn.commit()
    log_event(conn, "admin_suspend", actor_id, admin_id)
    conn.close()


def activate_admin(admin_id: str, actor_id: str) -> None:
    conn = get_conn()
    conn.execute("UPDATE admins SET is_active=1 WHERE admin_id=?", (admin_id,))
    conn.commit()
    log_event(conn, "admin_activate", actor_id, admin_id)
    conn.close()


def get_admin(admin_id: str) -> Optional[sqlite3.Row]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM admins WHERE admin_id=?", (admin_id,)).fetchone()
    conn.close()
    return row


def get_all_admins(only_active: bool = True) -> list[sqlite3.Row]:
    conn = get_conn()
    q = "SELECT * FROM admins"
    if only_active:
        q += " WHERE is_active=1"
    q += " ORDER BY level, display_name"
    rows = conn.execute(q).fetchall()
    conn.close()
    return rows


def find_admin_for_members(member_count: int) -> Optional[sqlite3.Row]:
    """
    هوشمند‌ترین تابع پروژه:
    بر اساس تعداد عضو، ادمین مناسب را پیدا می‌کند.
    اولویت: ادمین فعال با کمترین تعداد کانال جاری.
    """
    conn = get_conn()

    # ادمین‌هایی که بازه‌شان با member_count تطابق دارد
    candidates = conn.execute("""
        SELECT a.*,
               COUNT(c.id) AS current_channels
        FROM admins a
        LEFT JOIN channels c
            ON c.assigned_admin_id = a.admin_id
            AND c.status NOT IN ('rejected','cancelled','archived')
        WHERE a.is_active = 1
          AND a.min_members <= ?
          AND a.max_members >= ?
        GROUP BY a.admin_id
        HAVING current_channels < a.max_channels
        ORDER BY current_channels ASC
        LIMIT 1
    """, (member_count, member_count)).fetchone()

    conn.close()
    return candidates


def get_admin_leaderboard(period: str = "month") -> list[sqlite3.Row]:
    """
    لیست ادمین‌های برتر بر اساس ثبتی‌ها و جذب‌ها.
    period: today | week | month
    """
    conn = get_conn()
    if period == "today":
        date_filter = "date(c.registered_at) = date('now')"
    elif period == "week":
        date_filter = "c.registered_at >= datetime('now', '-7 days')"
    else:
        date_filter = "c.registered_at >= datetime('now', '-30 days')"

    rows = conn.execute(f"""
        SELECT a.admin_id, a.username, a.display_name,
               COUNT(c.id) AS reg_count,
               a.total_referrals
        FROM admins a
        LEFT JOIN channels c
            ON c.assigned_admin_id = a.admin_id
            AND c.status = 'archived'
            AND {date_filter}
        WHERE a.is_active = 1
        GROUP BY a.admin_id
        ORDER BY reg_count DESC, a.total_referrals DESC
    """).fetchall()
    conn.close()
    return rows


# ════════════════════════════════════════════════════════════
#  مدیریت کانال‌ها و صف
# ════════════════════════════════════════════════════════════

def _generate_code(admin_id: str) -> str:
    """
    تولید کد ثبت برای کانال جدید (مثل A-07).
    بر اساس حرف اول یوزرنیم ادمین + شماره ترتیبی.
    """
    conn = get_conn()
    admin = conn.execute(
        "SELECT username FROM admins WHERE admin_id=?", (admin_id,)
    ).fetchone()
    prefix = admin["username"][0].upper() if admin else "X"
    count = conn.execute("""
        SELECT COUNT(*) FROM channels WHERE assigned_admin_id=?
    """, (admin_id,)).fetchone()[0]
    conn.close()
    return f"{prefix}-{str(count + 1).zfill(2)}"


def create_channel_request(channel_link: str, channel_name: str,
                            member_count: int, avg_view: int,
                            topic: str, banner_file_id: str,
                            banner_caption: str, owner_user_id: str,
                            assigned_admin_id: str) -> Optional[int]:
    """ثبت درخواست کانال جدید و افزودن به صف."""
    conn = get_conn()
    try:
        code = _generate_code(assigned_admin_id)

        # موقعیت در صف این ادمین
        queue_pos = conn.execute("""
            SELECT COUNT(*) FROM queue
            WHERE admin_id=? AND is_active=1
        """, (assigned_admin_id,)).fetchone()[0] + 1

        conn.execute("""
            INSERT INTO channels
            (registration_code, channel_link, channel_name, member_count,
             avg_view, topic, banner_file_id, banner_caption,
             owner_user_id, assigned_admin_id, queue_position)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (code, channel_link, channel_name, member_count, avg_view,
              topic, banner_file_id, banner_caption,
              owner_user_id, assigned_admin_id, queue_pos))

        channel_db_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # افزودن به جدول صف
        conn.execute("""
            INSERT INTO queue (admin_id, channel_id, position)
            VALUES (?,?,?)
        """, (assigned_admin_id, channel_db_id, queue_pos))

        conn.commit()
        log_event(conn, "channel_register", owner_user_id,
                  str(channel_db_id), f"code={code},admin={assigned_admin_id}")
        return channel_db_id
    except Exception as e:
        logger.error(f"خطا در ثبت کانال: {e}")
        return None
    finally:
        conn.close()


def get_channel(channel_id: int) -> Optional[sqlite3.Row]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM channels WHERE id=?", (channel_id,)).fetchone()
    conn.close()
    return row


def get_channel_by_code(code: str) -> Optional[sqlite3.Row]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM channels WHERE registration_code=?", (code,)
    ).fetchone()
    conn.close()
    return row


def get_user_channels(user_id: str) -> list[sqlite3.Row]:
    """کانال‌های ثبت‌شده یک کاربر — با اطلاعات ادمین مسئول."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.*, a.username AS admin_username, a.display_name AS admin_name
        FROM channels c
        JOIN admins a ON c.assigned_admin_id = a.admin_id
        WHERE c.owner_user_id = ?
        ORDER BY c.registered_at DESC
    """, (user_id,)).fetchall()
    conn.close()
    return rows


def get_admin_queue(admin_id: str) -> list[sqlite3.Row]:
    """صف درخواست‌های یک ادمین به ترتیب."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.*, q.position, q.created_at AS queued_at
        FROM queue q
        JOIN channels c ON q.channel_id = c.id
        WHERE q.admin_id = ? AND q.is_active = 1 AND c.status = 'pending'
        ORDER BY q.position ASC
    """, (admin_id,)).fetchall()
    conn.close()
    return rows


def get_queue_position(channel_id: int) -> int:
    conn = get_conn()
    row = conn.execute(
        "SELECT position FROM queue WHERE channel_id=? AND is_active=1",
        (channel_id,)
    ).fetchone()
    conn.close()
    return row["position"] if row else 0


def estimate_wait_time(admin_id: str, position: int) -> int:
    """تخمین زمان انتظار بر اساس میانگین زمان بررسی ادمین (دقیقه)."""
    conn = get_conn()
    avg = conn.execute("""
        SELECT AVG(
            CAST((julianday(confirmed_at) - julianday(registered_at)) * 1440 AS INTEGER)
        )
        FROM channels
        WHERE assigned_admin_id=? AND status='archived'
        AND confirmed_at IS NOT NULL
    """, (admin_id,)).fetchone()[0]
    conn.close()
    avg_minutes = int(avg) if avg else 20
    return avg_minutes * max(position - 1, 0) + avg_minutes


def update_channel_status(channel_id: int, status: str,
                           actor_id: str, reason: str = None) -> None:
    conn = get_conn()
    now = datetime.now().isoformat()

    if status == ChannelStatus.ADMIN_JOINED:
        conn.execute(
            "UPDATE channels SET admin_joined=1, status=? WHERE id=?",
            (status, channel_id)
        )
    elif status == ChannelStatus.WAITING_OWNER:
        conn.execute(
            "UPDATE channels SET admin_promoted=0, status=? WHERE id=?",
            (status, channel_id)
        )
    elif status == ChannelStatus.CONFIRMED:
        conn.execute("""
            UPDATE channels SET admin_promoted=1, owner_confirmed=1,
            status=?, confirmed_at=? WHERE id=?
        """, (status, now, channel_id))
    elif status == ChannelStatus.ARCHIVED:
        conn.execute(
            "UPDATE channels SET status=?, archived_at=? WHERE id=?",
            (status, now, channel_id)
        )
        # آمار ادمین را به‌روز کن
        ch = conn.execute(
            "SELECT assigned_admin_id FROM channels WHERE id=?", (channel_id,)
        ).fetchone()
        if ch:
            conn.execute("""
                UPDATE admins SET total_registered = total_registered + 1
                WHERE admin_id=?
            """, (ch["assigned_admin_id"],))
    elif status == ChannelStatus.REJECTED:
        conn.execute("""
            UPDATE channels SET status=?, rejected_at=?, rejection_reason=?
            WHERE id=?
        """, (status, now, reason, channel_id))
        # از صف خارج کن
        conn.execute(
            "DELETE FROM queue WHERE channel_id=? AND is_active=1", (channel_id,)
        )

    conn.commit()
    log_event(conn, f"channel_{status}", actor_id, str(channel_id), reason)
    conn.close()


# ════════════════════════════════════════════════════════════
#  مدیریت اخطار و حذف
# ════════════════════════════════════════════════════════════

def issue_warning(channel_id: int, admin_id: str,
                  level: int, reason: str, expire_days: int = 7) -> int:
    """صدور اخطار برای یک کانال."""
    conn = get_conn()
    from datetime import timedelta
    expires = (datetime.now() + timedelta(days=expire_days)).isoformat()
    conn.execute("""
        INSERT INTO warnings (channel_registration_id, admin_id, level, reason, expires_at)
        VALUES (?,?,?,?,?)
    """, (channel_id, admin_id, level, reason, expires))
    conn.execute(
        "UPDATE channels SET warning_count = warning_count + 1 WHERE id=?",
        (channel_id,)
    )
    warning_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    log_event(conn, f"warning_level{level}", admin_id, str(channel_id), reason)
    conn.close()
    return warning_id


def resolve_warning(warning_id: int) -> None:
    conn = get_conn()
    conn.execute("""
        UPDATE warnings SET is_resolved=1, resolved_at=datetime('now')
        WHERE id=?
    """, (warning_id,))
    conn.commit()
    conn.close()


def get_channel_warnings(channel_id: int) -> list[sqlite3.Row]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM warnings WHERE channel_registration_id=?
        ORDER BY issued_at DESC
    """, (channel_id,)).fetchall()
    conn.close()
    return rows


# ════════════════════════════════════════════════════════════
#  مدیریت جوین اجباری
# ════════════════════════════════════════════════════════════

def get_active_forced_joins() -> list[sqlite3.Row]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM forced_joins WHERE is_active=1"
    ).fetchall()
    conn.close()
    return rows


def add_forced_join(channel_id: str, username: str, title: str) -> None:
    conn = get_conn()
    conn.execute("""
        INSERT OR IGNORE INTO forced_joins (channel_id, channel_username, channel_title)
        VALUES (?,?,?)
    """, (channel_id, username, title))
    conn.commit()
    conn.close()


def remove_forced_join(fj_id: int) -> None:
    conn = get_conn()
    conn.execute("UPDATE forced_joins SET is_active=0 WHERE id=?", (fj_id,))
    conn.commit()
    conn.close()


# ════════════════════════════════════════════════════════════
#  گزارش روزانه
# ════════════════════════════════════════════════════════════

def save_daily_report(admin_id: str, report_text: str,
                       registered: int = 0, rejected: int = 0) -> int:
    conn = get_conn()
    conn.execute("""
        INSERT INTO daily_reports
        (admin_id, report_text, registered_count, rejected_count)
        VALUES (?,?,?,?)
    """, (admin_id, report_text, registered, rejected))
    report_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return report_id


def owner_review_report(report_id: int, approved: bool, feedback: str = None) -> None:
    conn = get_conn()
    conn.execute("""
        UPDATE daily_reports SET owner_approved=?, owner_feedback=?
        WHERE id=?
    """, (1 if approved else 0, feedback, report_id))
    conn.commit()
    conn.close()


# ════════════════════════════════════════════════════════════
#  آمار کلی (پنل مالک)
# ════════════════════════════════════════════════════════════

def get_bot_stats() -> dict:
    conn = get_conn()
    stats = {}
    stats["total_users"] = conn.execute(
        "SELECT COUNT(*) FROM users WHERE role='user'"
    ).fetchone()[0]
    stats["total_admins"] = conn.execute(
        "SELECT COUNT(*) FROM admins WHERE is_active=1"
    ).fetchone()[0]
    stats["channels_today"] = conn.execute(
        "SELECT COUNT(*) FROM channels WHERE date(registered_at)=date('now')"
    ).fetchone()[0]
    stats["channels_week"] = conn.execute(
        "SELECT COUNT(*) FROM channels WHERE registered_at >= datetime('now','-7 days')"
    ).fetchone()[0]
    stats["channels_month"] = conn.execute(
        "SELECT COUNT(*) FROM channels WHERE registered_at >= datetime('now','-30 days')"
    ).fetchone()[0]
    stats["channels_total"] = conn.execute(
        "SELECT COUNT(*) FROM channels"
    ).fetchone()[0]
    stats["pending_count"] = conn.execute(
        "SELECT COUNT(*) FROM channels WHERE status='pending'"
    ).fetchone()[0]
    stats["active_warnings"] = conn.execute(
        "SELECT COUNT(*) FROM warnings WHERE is_resolved=0"
    ).fetchone()[0]
    conn.close()
    return stats


# ════════════════════════════════════════════════════════════
#  لاگ رویدادها
# ════════════════════════════════════════════════════════════

def log_event(conn: sqlite3.Connection, event_type: str,
              actor_id: str = None, target_id: str = None,
              detail: str = None) -> None:
    """ثبت رویداد در جدول لاگ. conn باید open باشد."""
    try:
        conn.execute("""
            INSERT INTO system_logs (event_type, actor_id, target_id, detail)
            VALUES (?,?,?,?)
        """, (event_type, actor_id, target_id, detail))
        conn.commit()
    except Exception as e:
        logger.warning(f"خطا در ثبت لاگ: {e}")
