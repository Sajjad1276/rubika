from fast_rub import Client

from ..core.config import Settings
from ..core.db import SessionFactory
from ..core.models import UserRole
from ..core.roles import RoleService
from .common import reply, update_text, update_user_id


async def build_admin_bot(settings: Settings) -> Client:
    bot = Client(settings.admin_bot_token)

    @bot.on_message()
    async def handle(message):
        user_id = update_user_id(message)
        if not user_id:
            return
        async with SessionFactory() as db:
            roles = RoleService(db, settings)
            user = await roles.get_or_create_user(rubika_user_id=user_id)
            allowed = roles.has(user, UserRole.ADMIN, UserRole.SUPERVISOR, UserRole.OWNER)
            await db.commit()
        if not allowed:
            await reply(message, "⛔ دسترسی این ربات فقط برای ادمین‌ها و ناظران شبکه است.")
            return

        text = update_text(message)
        if text in {"/start", "منو", "menu"}:
            await reply(
                message,
                "🛠 داشبورد ادمین\n\n"
                "1️⃣ وظایف امروز\n"
                "2️⃣ کانال‌ها\n"
                "3️⃣ درخواست‌های ثبت\n"
                "4️⃣ جذب کانال\n"
                "5️⃣ عملیات تبلیغ\n"
                "6️⃣ تخلفات\n"
                "7️⃣ عملکرد و درآمد\n"
                "8️⃣ آموزش",
            )
        elif text == "1":
            await reply(message, "📋 وظایف امروز شما در حال اتصال به TaskService است.")
        elif text == "2":
            await reply(message, "📺 مدیریت کانال‌های تحت مسئولیت شما.")
        elif text == "3":
            await reply(message, "📥 درخواست‌های جدید ثبت کانال.")
        elif text == "4":
            await reply(message, "🎯 ابزار جذب کانال و پیگیری سرنخ‌ها.")
        elif text == "5":
            await reply(message, "📣 عملیات تبلیغ و صف انتشار.")
        elif text == "6":
            await reply(message, "⚠️ تخلفات و اخطارهای ثبت‌شده.")
        elif text == "7":
            await reply(message, "📈 عملکرد، درآمد و KPI ادمین.")
        elif text == "8":
            await reply(message, "🎓 آموزش مرحله‌ای عملیات شبکه.")

    return bot
