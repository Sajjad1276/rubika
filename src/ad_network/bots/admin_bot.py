from fast_rub import Client
from sqlalchemy import func, select

from ..adapters.list_account import ListAccountGatewayResolver
from ..core.account_runtime import ListAccountRuntime
from ..core.campaigns import Campaign, CampaignTarget
from ..core.commerce import AdOrder, CommerceService, Payment, PaymentStatus
from ..core.config import Settings
from ..core.db import SessionFactory
from ..core.list_accounts import ListAccountResolver, ListAccountService
from ..core.models import Channel, RegistrationRequest, RegistrationStatus, UserRole, Violation
from ..core.roles import RoleService
from ..core.services import RegistrationService, VerificationService
from .account_routes import account_button, account_text
from .common import button_id, inline_keyboard, reply, update_text, update_user_id


def admin_keyboard():
    return inline_keyboard(
        (("requests", "📥 درخواست‌ها"), ("payments", "💳 پرداخت‌ها")),
        (("accounts", "👤 اکانت‌های لیست"), ("channels", "📺 کانال‌ها")),
        (("tasks", "📋 وظایف"), ("recruit", "🎯 جذب کانال")),
        (("campaigns", "📣 عملیات تبلیغ"), ("violations", "⚠️ تخلفات")),
        (("performance", "📈 عملکرد"), ("training", "🎓 آموزش")),
    )


async def build_admin_bot(
    settings: Settings,
    account_resolver: ListAccountResolver | None = None,
    account_runtime: ListAccountRuntime | None = None,
) -> Client:
    bot = Client("rubika_admin_bot", settings.admin_bot_token)
    gateway_resolver = ListAccountGatewayResolver(account_resolver) if account_resolver else None

    async def show_requests(message, user):
        async with SessionFactory() as db:
            requests = list((await db.scalars(select(RegistrationRequest).where(
                RegistrationRequest.status == RegistrationStatus.PENDING_VERIFICATION
            ).order_by(RegistrationRequest.created_at).limit(20))).all())
            await db.commit()
            if not requests:
                await reply(message, "📭 درخواست معلقی وجود ندارد.", inline_keypad=admin_keyboard())
                return
            await reply(message, "📥 درخواست‌های در انتظار بررسی:", inline_keypad=inline_keyboard(
                tuple((f"req:{item.id}", f"🔎 {item.id[:8]} | {item.list_id[:8] if item.list_id else '-'}") for item in requests)
            ))

    async def show_payments(message):
        async with SessionFactory() as db:
            payments = list((await db.scalars(select(Payment).where(
                Payment.status == PaymentStatus.PENDING
            ).order_by(Payment.created_at).limit(20))).all())
            await db.commit()
            if not payments:
                await reply(message, "📭 پرداخت معلقی وجود ندارد.", inline_keypad=admin_keyboard())
                return
            await reply(message, "💳 پرداخت‌های در انتظار تأیید:", inline_keypad=inline_keyboard(
                tuple((f"payment:{item.id}", f"💰 {item.amount:,} | {item.provider_reference or '-'}") for item in payments)
            ))

    async def show_channels(message):
        async with SessionFactory() as db:
            total = await db.scalar(select(func.count(Channel.id)))
            active = await db.scalar(select(func.count(Channel.id)).where(Channel.status == "active"))
            pending = await db.scalar(select(func.count(Channel.id)).where(Channel.status == "pending"))
            removed = await db.scalar(select(func.count(Channel.id)).where(Channel.status == "removed"))
            await db.commit()
        await reply(message, f"📺 وضعیت شبکه کانال‌ها\n\nکل: {int(total or 0)}\nفعال: {int(active or 0)}\nدر انتظار: {int(pending or 0)}\nحذف‌شده: {int(removed or 0)}", inline_keypad=admin_keyboard())

    async def show_campaigns(message):
        async with SessionFactory() as db:
            campaigns = list((await db.scalars(
                select(Campaign).order_by(Campaign.created_at.desc()).limit(15)
            )).all())
            lines = []
            for campaign in campaigns:
                total = await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.campaign_id == campaign.id))
                published = await db.scalar(select(func.count(CampaignTarget.id)).where(
                    CampaignTarget.campaign_id == campaign.id, CampaignTarget.status == "published"
                ))
                retained = await db.scalar(select(func.count(CampaignTarget.id)).where(
                    CampaignTarget.campaign_id == campaign.id, CampaignTarget.status == "retained"
                ))
                lines.append(f"{campaign.id[:8]} | {campaign.status} | {int(published or 0)}/{int(total or 0)} منتشر | {int(retained or 0)} ماندگار")
            await db.commit()
        await reply(message, "📣 وضعیت کمپین‌ها\n\n" + ("\n".join(lines) or "کمپینی وجود ندارد."), inline_keypad=admin_keyboard())

    async def show_violations(message):
        async with SessionFactory() as db:
            rows = list((await db.scalars(
                select(Violation).order_by(Violation.created_at.desc()).limit(20)
            )).all())
            lines = [f"{row.channel_id[:8]} | {row.violation_type} | شدت {row.severity} | {'حل‌شده' if row.resolved else 'باز'}" for row in rows]
            await db.commit()
        await reply(message, "⚠️ تخلفات اخیر\n\n" + ("\n".join(lines) or "تخلفی ثبت نشده است."), inline_keypad=admin_keyboard())

    async def show_performance(message):
        async with SessionFactory() as db:
            orders = await db.scalar(select(func.count(AdOrder.id)))
            paid = await db.scalar(select(func.count(AdOrder.id)).where(AdOrder.status.in_(["paid", "scheduled", "running", "completed"])))
            revenue = await db.scalar(select(func.coalesce(func.sum(AdOrder.total_price), 0)).where(AdOrder.status.in_(["paid", "scheduled", "running", "completed"])))
            earnings = await db.scalar(select(func.coalesce(func.sum(__import__("ad_network.core.commerce", fromlist=["EarningsEntry"]).EarningsEntry.amount), 0)))
            await db.commit()
        await reply(message, f"📈 عملکرد\n\nسفارش‌ها: {int(orders or 0)}\nپرداخت‌شده/فعال: {int(paid or 0)}\nگردش ثبت‌شده: {int(revenue or 0):,}\nدرآمد ثبت‌شده: {int(earnings or 0):,}", inline_keypad=admin_keyboard())

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
            if action == "accounts" or action.startswith("account:"):
                await db.commit()
                if account_runtime is None:
                    await reply(message, "⛔ Runtime اکانت‌ها در دسترس نیست.")
                else:
                    await account_button(message, action, account_runtime)
                return
            if action == "requests":
                await db.commit()
                await show_requests(message, user)
                return
            if action == "payments":
                await db.commit()
                await show_payments(message)
                return
            if action == "channels":
                await db.commit()
                await show_channels(message)
                return
            if action == "campaigns":
                await db.commit()
                await show_campaigns(message)
                return
            if action == "violations":
                await db.commit()
                await show_violations(message)
                return
            if action == "performance":
                await db.commit()
                await show_performance(message)
                return
            if action.startswith("payment:"):
                payment_id = action.split(":", 1)[1]
                payment = await db.get(Payment, payment_id)
                order = await db.get(AdOrder, payment.order_id) if payment else None
                if not payment or not order:
                    await db.commit()
                    await reply(message, "❌ پرداخت پیدا نشد.")
                    return
                await db.commit()
                await reply(message, f"💳 پرداخت {payment.provider_reference or '-'}\nمبلغ: {payment.amount:,}\nسفارش: {order.id[:8]}", inline_keypad=inline_keyboard(((f"confirm_payment:{payment.id}", "✅ تأیید پرداخت"),), (("payments", "↩️ بازگشت"),)))
                return
            if action.startswith("confirm_payment:"):
                payment_id = action.split(":", 1)[1]
                try:
                    payment = await CommerceService(db).confirm_payment(payment_id, confirmer_id=user.id)
                    await db.commit()
                    await reply(message, f"✅ پرداخت تأیید و کمپین زمان‌بندی شد. سفارش {payment.order_id[:8]}", inline_keypad=admin_keyboard())
                except ValueError as exc:
                    await db.rollback()
                    await reply(message, f"⛔ تأیید انجام نشد: {exc}")
                return
            if action.startswith("req:"):
                request = await db.scalar(select(RegistrationRequest).where(RegistrationRequest.id == action.split(":", 1)[1]))
                channel = await db.get(Channel, request.channel_id) if request else None
                if not request:
                    await db.commit()
                    await reply(message, "❌ درخواست پیدا نشد.")
                    return
                await db.commit()
                await reply(message, f"🔎 درخواست {request.id[:8]}\nکانال: {channel.rubika_guid if channel else '-'}\nلیست: {request.list_id}\n\nدسترسی را بررسی کنید.", inline_keypad=inline_keyboard(((f"access:{request.id}", "🔐 احراز دسترسی"),), ((f"approve:{request.id}", "✅ تأیید"), (f"reject:{request.id}", "🚫 رد")), (("home", "↩️ بازگشت"),)))
                return
            if action.startswith("access:"):
                request = await db.scalar(select(RegistrationRequest).where(RegistrationRequest.id == action.split(":", 1)[1], RegistrationRequest.status == RegistrationStatus.PENDING_VERIFICATION))
                if not request or gateway_resolver is None:
                    await db.commit()
                    await reply(message, "⛔ درخواست یا gateway در دسترس نیست.")
                    return
                try:
                    account = await ListAccountService(db).require_active(request.list_id)
                    gateway = gateway_resolver.resolve(account)
                    await VerificationService(db).verify_from_rubika(channel_id=request.channel_id, gateway=gateway, operational_account_user_id=account.rubika_user_id, verifier_id=user.id)
                    await db.commit()
                    await reply(message, "✅ دسترسی واقعی کانال بررسی شد.", inline_keypad=inline_keyboard(((f"approve:{request.id}", "✅ فعال‌سازی"), ("home", "↩️ بازگشت"))))
                except (ValueError, RuntimeError) as exc:
                    await db.rollback()
                    await reply(message, f"⛔ احراز انجام نشد: {exc}")
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
                    await reply(message, "✅ کانال فعال شد.", inline_keypad=admin_keyboard())
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
            await db.commit()
            responses = {"tasks": "📋 وظایف امروز در صف هستند.", "recruit": "🎯 سرنخ‌های جذب کانال در حال جمع‌آوری است.", "training": "🎓 آموزش مرحله‌ای شبکه فعال است."}
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
        if text and account_runtime is not None and await account_text(message, account_runtime):
            return
        async with SessionFactory() as db:
            user = await RoleService(db, settings).get_or_create_user(rubika_user_id=user_id)
            allowed = RoleService(db, settings).has(user, UserRole.ADMIN, UserRole.SUPERVISOR, UserRole.OWNER)
            await db.commit()
        if not allowed:
            await reply(message, "⛔ دسترسی این ربات فقط برای ادمین‌ها و ناظران شبکه است.")
            return
        if text in {"/start", "منو", "menu"}:
            await reply(message, "🛠 داشبورد ادمین", inline_keypad=admin_keyboard())
        elif text == "3":
            await show_requests(message, user)

    return bot
