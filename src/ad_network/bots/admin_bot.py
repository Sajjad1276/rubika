from fast_rub import Client
from sqlalchemy import select

from ..core.config import Settings
from ..core.db import SessionFactory
from ..core.models import Channel, RegistrationRequest, RegistrationStatus, UserRole
from ..core.roles import RoleService
from ..core.services import RegistrationService, VerificationService
from .common import button_id, inline_keyboard, reply, update_text, update_user_id


def admin_keyboard():
    return inline_keyboard(
        (("requests", "📥 درخواست‌ها"), ("channels", "📺 کانال‌ها")),
        (("tasks", "📋 وظایف"), ("recruit", "🎯 جذب کانال")),
        (("campaigns", "📣 عملیات تبلیغ"), ("violations", "⚠️ تخلفات")),
        (("performance", "📈 عملکرد"), ("training", "🎓 آموزش")),
    )


async def build_admin_bot(settings: Settings) -> Client:
    bot = Client(settings.admin_bot_token)

    async def show_requests(message, user):
        async with SessionFactory() as db:
            requests = list((await db.scalars(
                select(RegistrationRequest)
                .where(RegistrationRequest.status == RegistrationStatus.PENDING_VERIFICATION)
                .order_by(RegistrationRequest.created_at).limit(20)
            )).all())
            if not requests:
                await db.commit()
                await reply(message, "📭 درخواست معلقی وجود ندارد.", inline_keypad=admin_keyboard())
                return
            rows = tuple((f"req:{item.id}", f"🔎 {item.id[:8]} | {item.list_id[:8]}") for item in requests)
            await db.commit()
            await reply(message, "📥 درخواست‌های در انتظار بررسی:", inline_keypad=inline_keyboard(rows))

    async def handle_action(message, action: str):
        user_id = update_user_id(message)
        if not user_id:
            return
        async with SessionFactory() as db:
            roles = RoleService(db, settings)
            user = await roles.get_or_create_user(rubika_user_id=user_id)
            if not roles.has(user, UserRole.ADMIN, UserRole.SUPERVISOR, UserRole.OWNER):
                await db.commit()
                await reply(message, "⛔ دسترسی ندارید.")
                return
            if action == "home":
                await db.commit()
                await reply(message, "🛠 داشبورد ادمین", inline_keypad=admin_keyboard())
                return
            if action == "requests":
                await db.commit()
                await show_requests(message, user)
                return
            if action.startswith("req:"):
                request = await db.scalar(select(RegistrationRequest).where(RegistrationRequest.id == action.split(":", 1)[1]))
                channel = await db.get(Channel, request.channel_id) if request else None
                if not request:
                    await db.commit()
                    await reply(message, "❌ درخواست پیدا نشد.")
                    return
                await db.commit()
                await reply(message, f"🔎 درخواست {request.id[:8]}\nکانال: {channel.rubika_guid if channel else '-'}\nلیست: {request.list_id}\n\nدسترسی را از طریق دکمه زیر بررسی کنید.", inline_keypad=inline_keyboard(((f"access:{request.id}", "🔐 احراز دسترسی"),), ((f"approve:{request.id}", "✅ تأیید"), (f"reject:{request.id}", "🚫 رد")), (("home", "↩️ بازگشت"),)))
                return
            if action.startswith("access:"):
                request = await db.scalar(select(RegistrationRequest).where(RegistrationRequest.id == action.split(":", 1)[1], RegistrationRequest.status == RegistrationStatus.PENDING_VERIFICATION))
                if not request:
                    await db.commit()
                    await reply(message, "❌ درخواست پیدا نشد.")
                    return
                await VerificationService(db).verify_from_rubika(request.channel_id, verified_by=user.id, list_id=request.list_id)
                await db.commit()
                await reply(message, "✅ دسترسی واقعی کانال از طریق اکانت عملیاتی List بررسی شد.", inline_keypad=inline_keyboard(((f"approve:{request.id}", "✅ فعال‌سازی"), ("home", "↩️ بازگشت"))))
                return
            if action.startswith("approve:"):
                request = await db.scalar(select(RegistrationRequest).where(RegistrationRequest.id == action.split(":", 1)[1], RegistrationRequest.status == RegistrationStatus.PENDING_VERIFICATION))
                if not request:
                    await db.commit()
                    await reply(message, "❌ درخواست پیدا نشد.")
                    return
                try:
                    await RegistrationService(db).verify(request, approved=True, verifier_id=user.id)
                    await db.commit()
                    await reply(message, f"✅ کانال فعال شد. کد: {request.id[:8]}", inline_keypad=admin_keyboard())
                except ValueError as exc:
                    await db.rollback()
                    await reply(message, f"⛔ فعال‌سازی انجام نشد: {exc}")
                return
            if action.startswith("reject:"):
                request = await db.scalar(select(RegistrationRequest).where(RegistrationRequest.id == action.split(":", 1)[1], RegistrationRequest.status == RegistrationStatus.PENDING_VERIFICATION))
                if request:
                    await RegistrationService(db).verify(request, approved=False, verifier_id=user.id)
                    await db.commit()
                    await reply(message, "🚫 درخواست رد شد.", inline_keypad=admin_keyboard())
                return
            responses = {
                "tasks": "📋 وظایف امروز آماده‌سازی می‌شوند.", "channels": "📺 کانال‌های تحت مسئولیت.",
                "recruit": "🎯 سرنخ‌های جذب کانال.", "campaigns": "📣 صف عملیات تبلیغ.",
                "violations": "⚠️ تخلفات شبکه.", "performance": "📈 عملکرد و درآمد.", "training": "🎓 آموزش مرحله‌ای.",
            }
            await db.commit()
            if action in responses:
                await reply(message, responses[action], inline_keypad=admin_keyboard())

    @bot.on_button()
    async def on_button(message):
        action = button_id(message)
        if action:
            await handle_action(message, action)

    @bot.on_message()
    async def handle(message):
        user_id = update_user_id(message)
        if not user_id:
            return
        text = update_text(message)
        async with SessionFactory() as db:
            roles = RoleService(db, settings)
            user = await roles.get_or_create_user(rubika_user_id=user_id)
            allowed = roles.has(user, UserRole.ADMIN, UserRole.SUPERVISOR, UserRole.OWNER)
            await db.commit()
        if not allowed:
            await reply(message, "⛔ دسترسی این ربات فقط برای ادمین‌ها و ناظران شبکه است.")
            return
        if text in {"/start", "منو", "menu"}:
            await reply(message, "🛠 داشبورد ادمین", inline_keypad=admin_keyboard())
            return
        if text == "3":
            await show_requests(message, user)

    return bot
