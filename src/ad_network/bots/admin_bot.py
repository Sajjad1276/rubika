from fast_rub import Client
from sqlalchemy import select

from ..adapters.list_account import ListAccountGatewayResolver
from ..core.commerce import AdOrder, CommerceService, Payment, PaymentStatus
from ..core.config import Settings
from ..core.db import SessionFactory
from ..core.list_accounts import ListAccountResolver, ListAccountService
from ..core.models import Channel, RegistrationRequest, RegistrationStatus, UserRole
from ..core.roles import RoleService
from ..core.services import RegistrationService, VerificationService
from .common import button_id, inline_keyboard, reply, update_text, update_user_id


def admin_keyboard():
    return inline_keyboard(
        (("requests", "📥 درخواست‌ها"), ("payments", "💳 پرداخت‌ها")),
        (("channels", "📺 کانال‌ها"), ("tasks", "📋 وظایف")),
        (("recruit", "🎯 جذب کانال"), ("campaigns", "📣 عملیات تبلیغ")),
        (("violations", "⚠️ تخلفات"), ("performance", "📈 عملکرد")),
        (("training", "🎓 آموزش"),),
    )


async def build_admin_bot(settings: Settings, account_resolver: ListAccountResolver | None = None) -> Client:
    bot = Client("rubika_admin_bot", settings.admin_bot_token)
    gateway_resolver = ListAccountGatewayResolver(account_resolver) if account_resolver else None

    async def show_requests(message, user):
        async with SessionFactory() as db:
            requests = list((await db.scalars(select(RegistrationRequest).where(
                RegistrationRequest.status == RegistrationStatus.PENDING_VERIFICATION
            ).order_by(RegistrationRequest.created_at).limit(20))).all())
            await db.commit()
            if not requests:
                await reply(message, "📭 درخواست معلقی وجود ندارد.", inline_keypad=admin_keyboard()); return
            await reply(message, "📥 درخواست‌های در انتظار بررسی:", inline_keypad=inline_keyboard(
                tuple((f"req:{item.id}", f"🔎 {item.id[:8]} | {item.list_id[:8]}") for item in requests)
            ))

    async def show_payments(message):
        async with SessionFactory() as db:
            payments = list((await db.scalars(select(Payment).where(
                Payment.status == PaymentStatus.PENDING
            ).order_by(Payment.created_at).limit(20))).all())
            await db.commit()
            if not payments:
                await reply(message, "📭 پرداخت معلقی وجود ندارد.", inline_keypad=admin_keyboard()); return
            await reply(message, "💳 پرداخت‌های در انتظار تأیید:", inline_keypad=inline_keyboard(
                tuple((f"payment:{item.id}", f"💰 {item.amount:,} | {item.provider_reference or '-'}") for item in payments)
            ))

    async def handle_action(message, action: str):
        user_id = update_user_id(message)
        if not user_id: return
        async with SessionFactory() as db:
            roles = RoleService(db, settings)
            user = await roles.get_or_create_user(rubika_user_id=user_id)
            if not roles.has(user, UserRole.ADMIN, UserRole.SUPERVISOR, UserRole.OWNER):
                await db.commit(); await reply(message, "⛔ دسترسی ندارید."); return
            if action == "home":
                await db.commit(); await reply(message, "🛠 داشبورد ادمین", inline_keypad=admin_keyboard()); return
            if action == "requests":
                await db.commit(); await show_requests(message, user); return
            if action == "payments":
                await db.commit(); await show_payments(message); return
            if action.startswith("payment:"):
                payment_id = action.split(":", 1)[1]
                payment = await db.get(Payment, payment_id)
                order = await db.get(AdOrder, payment.order_id) if payment else None
                if not payment or not order:
                    await db.commit(); await reply(message, "❌ پرداخت پیدا نشد."); return
                await db.commit()
                await reply(message, f"💳 پرداخت {payment.provider_reference or '-'}\nمبلغ: {payment.amount:,}\nسفارش: {order.id[:8]}",
                            inline_keypad=inline_keyboard(((f"confirm_payment:{payment.id}", "✅ تأیید پرداخت"),), (("payments", "↩️ بازگشت"),)))
                return
            if action.startswith("confirm_payment:"):
                payment_id = action.split(":", 1)[1]
                try:
                    payment = await CommerceService(db).confirm_payment(payment_id, confirmer_id=user.id)
                    await db.commit()
                    await reply(message, f"✅ پرداخت تأیید شد. سفارش {payment.order_id[:8]} اکنون قابل زمان‌بندی است.", inline_keypad=admin_keyboard())
                except ValueError as exc:
                    await db.rollback(); await reply(message, f"⛔ تأیید انجام نشد: {exc}")
                return
            if action.startswith("req:"):
                request = await db.scalar(select(RegistrationRequest).where(RegistrationRequest.id == action.split(":", 1)[1]))
                channel = await db.get(Channel, request.channel_id) if request else None
                if not request:
                    await db.commit(); await reply(message, "❌ درخواست پیدا نشد."); return
                await db.commit()
                await reply(message, f"🔎 درخواست {request.id[:8]}\nکانال: {channel.rubika_guid if channel else '-'}\nلیست: {request.list_id}\n\nدسترسی را بررسی کنید.",
                            inline_keypad=inline_keyboard(((f"access:{request.id}", "🔐 احراز دسترسی"),),
                                                           ((f"approve:{request.id}", "✅ تأیید"), (f"reject:{request.id}", "🚫 رد")),
                                                           (("home", "↩️ بازگشت"),)))
                return
            if action.startswith("access:"):
                request = await db.scalar(select(RegistrationRequest).where(RegistrationRequest.id == action.split(":", 1)[1], RegistrationRequest.status == RegistrationStatus.PENDING_VERIFICATION))
                if not request or gateway_resolver is None:
                    await db.commit(); await reply(message, "⛔ درخواست یا gateway در دسترس نیست."); return
                try:
                    account = await ListAccountService(db).require_active(request.list_id)
                    gateway = gateway_resolver.resolve(account)
                    await VerificationService(db).verify_from_rubika(channel_id=request.channel_id, gateway=gateway,
                                                                      operational_account_user_id=account.rubika_user_id, verifier_id=user.id)
                    await db.commit(); await reply(message, "✅ دسترسی واقعی کانال بررسی شد.", inline_keypad=inline_keyboard(((f"approve:{request.id}", "✅ فعال‌سازی"), ("home", "↩️ بازگشت"))))
                except (ValueError, RuntimeError) as exc:
                    await db.rollback(); await reply(message, f"⛔ احراز انجام نشد: {exc}")
                return
            if action.startswith("approve:"):
                request = await db.scalar(select(RegistrationRequest).where(RegistrationRequest.id == action.split(":", 1)[1], RegistrationRequest.status == RegistrationStatus.PENDING_VERIFICATION))
                if not request:
                    await db.commit(); await reply(message, "❌ درخواست پیدا نشد."); return
                try:
                    await RegistrationService(db).verify(request, approved=True, verifier_id=user.id)
                    await db.commit(); await reply(message, "✅ کانال فعال شد.", inline_keypad=admin_keyboard())
                except ValueError as exc:
                    await db.rollback(); await reply(message, f"⛔ فعال‌سازی انجام نشد: {exc}")
                return
            if action.startswith("reject:"):
                request = await db.scalar(select(RegistrationRequest).where(RegistrationRequest.id == action.split(":", 1)[1], RegistrationRequest.status == RegistrationStatus.PENDING_VERIFICATION))
                if request:
                    await RegistrationService(db).verify(request, approved=False, verifier_id=user.id)
                    await db.commit(); await reply(message, "🚫 درخواست رد شد.", inline_keypad=admin_keyboard())
                return
            responses = {"tasks":"📋 وظایف امروز آماده‌سازی می‌شوند.","channels":"📺 کانال‌های تحت مسئولیت.","recruit":"🎯 سرنخ‌های جذب کانال.","campaigns":"📣 صف عملیات تبلیغ.","violations":"⚠️ تخلفات شبکه.","performance":"📈 عملکرد و درآمد.","training":"🎓 آموزش مرحله‌ای."}
            await db.commit()
            if action in responses: await reply(message, responses[action], inline_keypad=admin_keyboard())

    @bot.on_button()
    async def on_button(message):
        action = button_id(message)
        if action: await handle_action(message, action)

    @bot.on_message()
    async def handle(message):
        user_id = update_user_id(message)
        if not user_id: return
        text = update_text(message)
        async with SessionFactory() as db:
            user = await RoleService(db, settings).get_or_create_user(rubika_user_id=user_id)
            allowed = RoleService(db, settings).has(user, UserRole.ADMIN, UserRole.SUPERVISOR, UserRole.OWNER)
            await db.commit()
        if not allowed:
            await reply(message, "⛔ دسترسی این ربات فقط برای ادمین‌ها و ناظران شبکه است."); return
        if text in {"/start", "منو", "menu"}: await reply(message, "🛠 داشبورد ادمین", inline_keypad=admin_keyboard())
        elif text == "3": await show_requests(message, user)

    return bot
