from fast_rub import Client

from ..core.config import Settings
from ..core.db import SessionFactory
from ..core.roles import RoleService
from .common import BotContext, reply, update_text, update_user_id


async def build_user_bot(settings: Settings) -> Client:
    bot = Client(settings.user_bot_token)

    @bot.on_message()
    async def handle(message):
        user_id = update_user_id(message)
        if not user_id:
            return
        async with SessionFactory() as db:
            roles = RoleService(db, settings)
            await roles.get_or_create_user(rubika_user_id=user_id)
            await db.commit()

        text = update_text(message)
        if text in {"/start", "شروع", "منو", "menu"}:
            await reply(
                message,
                "📣 شبکه تبلیغات\n\n"
                "ثبت و مدیریت کانال‌ها، درخواست تبلیغ و پیگیری سفارش‌ها از همین ربات.\n\n"
                "1️⃣ ثبت کانال\n"
                "2️⃣ وضعیت کانال\n"
                "3️⃣ درخواست تبلیغ\n"
                "4️⃣ تعرفه‌ها\n"
                "5️⃣ پشتیبانی\n\n"
                "فعلاً برای ادامه، شماره گزینه را ارسال کنید.",
            )
        elif text == "1":
            await reply(message, "🔗 لینک یا شناسه کانال را ارسال کنید تا فرآیند ثبت شروع شود.")
        elif text == "2":
            await reply(message, "📊 وضعیت کانال شما در نسخه عملیاتی از دیتابیس خوانده می‌شود.")
        elif text == "3":
            await reply(message, "📢 درخواست تبلیغ: در حال آماده‌سازی مرحله انتخاب لیست و تعرفه.")
        elif text == "4":
            await reply(message, "💰 تعرفه‌ها پس از فعال شدن ماژول قیمت‌گذاری نمایش داده می‌شوند.")
        elif text == "5":
            await reply(message, "🧑‍💻 درخواست پشتیبانی ثبت می‌شود.")

    return bot
