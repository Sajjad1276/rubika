from fast_rub import Client

from ..core.config import Settings
from ..core.db import SessionFactory
from ..core.models import UserRole
from ..core.roles import RoleService
from .common import reply, update_text, update_user_id


async def build_owner_bot(settings: Settings) -> Client:
    bot = Client(settings.owner_bot_token)

    @bot.on_message()
    async def handle(message):
        user_id = update_user_id(message)
        if not user_id:
            return
        async with SessionFactory() as db:
            roles = RoleService(db, settings)
            user = await roles.get_or_create_user(rubika_user_id=user_id)
            allowed = roles.has(user, UserRole.OWNER, UserRole.SUPERVISOR)
            await db.commit()
        if not allowed:
            await reply(message, "⛔ دسترسی این ربات فقط برای مالک و ناظر شبکه است.")
            return

        text = update_text(message)
        if text in {"/start", "منو", "menu"}:
            await reply(
                message,
                "👑 مدیریت شبکه\n\n"
                "1️⃣ نمای کلی شبکه\n"
                "2️⃣ لیست‌ها\n"
                "3️⃣ ادمین‌ها و ناظرها\n"
                "4️⃣ سفارش‌ها و کمپین‌ها\n"
                "5️⃣ تعرفه و درآمد\n"
                "6️⃣ قوانین و قالب‌ها\n"
                "7️⃣ گزارش و Audit\n"
                "8️⃣ تنظیمات ماژول‌ها",
            )
        elif text == "1":
            await reply(message, "📊 نمای کلی شبکه در حال اتصال به AnalyticsService است.")
        elif text == "2":
            await reply(message, "🗂 مدیریت لیست‌ها.")
        elif text == "3":
            await reply(message, "👥 مدیریت نقش‌ها و دسترسی‌ها.")
        elif text == "4":
            await reply(message, "📢 مدیریت سفارش‌ها و کمپین‌ها.")
        elif text == "5":
            await reply(message, "💰 تعرفه‌ها، درآمد و تسویه.")
        elif text == "6":
            await reply(message, "📚 قوانین و Templateهای شبکه.")
        elif text == "7":
            await reply(message, "🧾 گزارش تغییرات و عملیات حساس.")
        elif text == "8":
            await reply(message, "⚙️ فعال/غیرفعال‌سازی و ترتیب ماژول‌های رابط ربات.")

    return bot
