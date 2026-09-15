from sqlalchemy import func, select

from ..adapters.list_account import ListAccountGatewayResolver
from ..core.campaigns import Campaign, CampaignTarget
from ..core.commerce import AdOrder, CommerceService, EarningsEntry, Payment, PaymentStatus
from ..core.config import Settings
from ..core.db import SessionFactory
from ..core.list_accounts import ListAccountResolver, ListAccountService
from ..core.models import (
    Channel,
    ListNetwork,
    RegistrationRequest,
    RegistrationSource,
    RegistrationStatus,
    Task,
    TaskStatus,
    UserRole,
    Violation,
)
from ..core.roles import RoleService
from ..core.services import RegistrationService, VerificationService
from .common import button_id, inline_keyboard, is_duplicate_update, quick_keyboard, reply, resolve_user, update_text

_RECRUIT_STATES: dict[str, str] = {}


def admin_keyboard():
    return quick_keyboard(
        (("requests", "📥 درخواست‌ها"), ("payments", "💳 پرداخت‌ها")),
        (("channels", "📺 کانال‌ها"), ("tasks", "📋 وظایف")),
        (("recruit", "🎯 جذب کانال"), ("campaigns", "📣 عملیات تبلیغ")),
        (("violations", "⚠️ تخلفات"), ("performance", "📈 عملکرد")),
        (("training", "🎓 آموزش"),),
    )


async def build_admin_bot(settings: Settings, account_resolver: ListAccountResolver | None = None, account_runtime=None):
    from maxrubika import Bot

    bot = Bot(settings.admin_bot_token, timeout=30, max_retries=5)
    gateway_resolver = ListAccountGatewayResolver(account_resolver) if account_resolver else None

    async def show_requests(event):
        async with SessionFactory() as db:
            requests = list((await db.scalars(select(RegistrationRequest).where(
                RegistrationRequest.status == RegistrationStatus.PENDING_VERIFICATION
            ).order_by(RegistrationRequest.created_at).limit(20))).all())
        if not requests:
            await reply(event, "📭 درخواست معلقی وجود ندارد.", keypad=admin_keyboard()); return
        await reply(event, "📥 درخواست‌های در انتظار بررسی:", inline_keypad=inline_keyboard(
            tuple((f"req:{item.id}", f"🔎 {item.id[:8]} | {item.list_id[:8] if item.list_id else '-'}") for item in requests)
        ))

    async def show_payments(event):
        async with SessionFactory() as db:
            payments = list((await db.scalars(select(Payment).where(
                Payment.status == PaymentStatus.PENDING
            ).order_by(Payment.created_at).limit(20))).all())
        if not payments:
            await reply(event, "📭 پرداخت معلقی وجود ندارد.", keypad=admin_keyboard()); return
        await reply(event, "💳 پرداخت‌های در انتظار تأیید:", inline_keypad=inline_keyboard(
            tuple((f"payment:{item.id}", f"💰 {item.amount:,} | {item.provider_reference or '-'}") for item in payments)
        ))

    async def show_channels(event):
        async with SessionFactory() as db:
            total = await db.scalar(select(func.count(Channel.id)))
            active = await db.scalar(select(func.count(Channel.id)).where(Channel.status == "active"))
            pending = await db.scalar(select(func.count(Channel.id)).where(Channel.status == "pending"))
            removed = await db.scalar(select(func.count(Channel.id)).where(Channel.status == "removed"))
        await reply(event, f"📺 وضعیت شبکه کانال‌ها\n\nکل: {int(total or 0)}\nفعال: {int(active or 0)}\nدر انتظار: {int(pending or 0)}\nحذف‌شده: {int(removed or 0)}", keypad=admin_keyboard())

    async def show_campaigns(event):
        async with SessionFactory() as db:
            campaigns = list((await db.scalars(select(Campaign).order_by(Campaign.created_at.desc()).limit(15))).all())
            lines = []
            for campaign in campaigns:
                total = await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.campaign_id == campaign.id))
                published = await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.campaign_id == campaign.id, CampaignTarget.status == "published"))
                retained = await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.campaign_id == campaign.id, CampaignTarget.status == "retained"))
                lines.append(f"{campaign.id[:8]} | {campaign.status} | {int(published or 0)}/{int(total or 0)} منتشر | {int(retained or 0)} ماندگار")
        await reply(event, "📣 وضعیت کمپین‌ها\n\n" + ("\n".join(lines) or "کمپینی وجود ندارد."), keypad=admin_keyboard())

    async def show_violations(event):
        async with SessionFactory() as db:
            rows = list((await db.scalars(select(Violation).order_by(Violation.created_at.desc()).limit(20))).all())
        lines = [f"{row.channel_id[:8]} | {row.violation_type} | شدت {row.severity} | {'حل‌شده' if row.resolved else 'باز'}" for row in rows]
        await reply(event, "⚠️ تخلفات اخیر\n\n" + ("\n".join(lines) or "تخلفی ثبت نشده است."), keypad=admin_keyboard())

    async def show_performance(event):
        async with SessionFactory() as db:
            orders = await db.scalar(select(func.count(AdOrder.id)))
            paid = await db.scalar(select(func.count(AdOrder.id)).where(AdOrder.status.in_(["paid", "scheduled", "running", "completed"])))
            revenue = await db.scalar(select(func.coalesce(func.sum(AdOrder.total_price), 0)).where(AdOrder.status.in_(["paid", "scheduled", "running", "completed"])))
            earnings = await db.scalar(select(func.coalesce(func.sum(EarningsEntry.amount), 0)))
        await reply(event, f"📈 عملکرد\n\nسفارش‌ها: {int(orders or 0)}\nپرداخت‌شده/فعال: {int(paid or 0)}\nگردش ثبت‌شده: {int(revenue or 0):,}\nدرآمد ثبت‌شده: {int(earnings or 0):,}", keypad=admin_keyboard())

    async def show_tasks(event, user_id: str):
        async with SessionFactory() as db:
            tasks = list((await db.scalars(select(Task).where(Task.assignee_id == user_id, Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS])).order_by(Task.created_at.desc()).limit(20))).all())
        lines = [f"{task.id[:8]} | {task.task_type} | {task.status.value if hasattr(task.status, 'value') else task.status}" for task in tasks]
        await reply(event, "📋 وظایف من\n\n" + ("\n".join(lines) or "وظیفه‌ای در صف نیست."), keypad=admin_keyboard())

    async def show_recruitment(event):
        async with SessionFactory() as db:
            rows = list((await db.scalars(select(RegistrationRequest).where(RegistrationRequest.source == RegistrationSource.ADMIN_RECRUITED, RegistrationRequest.status.in_([RegistrationStatus.DRAFT, RegistrationStatus.PENDING_VERIFICATION])).order_by(RegistrationRequest.created_at.desc()).limit(20))).all())
            pending_verification = sum(row.status == RegistrationStatus.PENDING_VERIFICATION for row in rows)
        await reply(event, f"🎯 جذب کانال\n\nسرنخ‌های باز: {len(rows)}\nدر انتظار احراز: {pending_verification}", inline_keypad=inline_keyboard((("recruit:start", "➕ ثبت کانال جذب‌شده"),)))

    async def handle_action(event, action: str):
        user_id = await resolve_user(bot, event)
        if not user_id: return
        async with SessionFactory() as db:
            roles = RoleService(db, settings)
            user = await roles.get_or_create_user(rubika_user_id=user_id)
            if not roles.has(user, UserRole.ADMIN, UserRole.SUPERVISOR, UserRole.OWNER):
                await db.rollback(); await reply(event, "⛔ دسترسی ندارید."); return
            if action in {"home", "back"}:
                _RECRUIT_STATES.pop(user_id, None); await db.commit(); await reply(event, "🛠 داشبورد ادمین", keypad=admin_keyboard()); return
            if action == "requests": await db.commit(); await show_requests(event); return
            if action == "payments": await db.commit(); await show_payments(event); return
            if action == "channels": await db.commit(); await show_channels(event); return
            if action == "campaigns": await db.commit(); await show_campaigns(event); return
            if action == "violations": await db.commit(); await show_violations(event); return
            if action == "performance": await db.commit(); await show_performance(event); return
            if action == "tasks": await db.commit(); await show_tasks(event, user.id); return
            if action == "recruit": await db.commit(); await show_recruitment(event); return
            if action == "recruit:start":
                _RECRUIT_STATES[user_id] = "recruit"; await db.commit(); await reply(event, "🎯 فرمت جذب: شناسه کانال | کد لیست\nمثال: @mychannel | 001"); return
            if action == "training":
                await db.commit(); await reply(event, "🎓 آموزش شبکه\n\n1) احراز دسترسی کانال\n2) تأیید پرداخت\n3) پایش ماندگاری\n4) ثبت تخلف و پیگیری آن", keypad=admin_keyboard()); return
            if action.startswith("payment:"):
                payment = await db.get(Payment, action.split(":", 1)[1]); order = await db.get(AdOrder, payment.order_id) if payment else None
                if not payment or not order: await db.commit(); await reply(event, "❌ پرداخت پیدا نشد."); return
                await db.commit(); await reply(event, f"💳 پرداخت {payment.provider_reference or '-'}\nمبلغ: {payment.amount:,}\nسفارش: {order.id[:8]}", inline_keypad=inline_keyboard(((f"confirm_payment:{payment.id}", "✅ تأیید پرداخت"),), (("payments", "↩️ بازگشت"),))); return
            if action.startswith("confirm_payment:"):
                try:
                    payment = await CommerceService(db).confirm_payment(action.split(":", 1)[1], confirmer_id=user.id); await db.commit(); await reply(event, f"✅ پرداخت تأیید و کمپین زمان‌بندی شد. سفارش {payment.order_id[:8]}", keypad=admin_keyboard())
                except ValueError as exc: await db.rollback(); await reply(event, f"⛔ تأیید انجام نشد: {exc}")
                return
            if action.startswith("req:"):
                request = await db.scalar(select(RegistrationRequest).where(RegistrationRequest.id == action.split(":", 1)[1])); channel = await db.get(Channel, request.channel_id) if request else None
                if not request: await db.commit(); await reply(event, "❌ درخواست پیدا نشد."); return
                await db.commit(); await reply(event, f"🔎 درخواست {request.id[:8]}\nکانال: {channel.rubika_guid if channel else '-'}\nلیست: {request.list_id}\n\nدسترسی را بررسی کنید.", inline_keypad=inline_keyboard(((f"access:{request.id}", "🔐 احراز دسترسی"),), ((f"approve:{request.id}", "✅ تأیید"), (f"reject:{request.id}", "🚫 رد")))); return
            if action.startswith("access:"):
                request = await db.scalar(select(RegistrationRequest).where(RegistrationRequest.id == action.split(":", 1)[1], RegistrationRequest.status == RegistrationStatus.PENDING_VERIFICATION))
                if not request or gateway_resolver is None: await db.commit(); await reply(event, "⛔ درخواست یا gateway در دسترس نیست."); return
                try:
                    account = await ListAccountService(db).require_active(request.list_id)
                    await VerificationService(db).verify_from_rubika(channel_id=request.channel_id, gateway=gateway_resolver.resolve(account), operational_account_user_id=account.rubika_user_id, verifier_id=user.id)
                    await db.commit(); await reply(event, "✅ دسترسی واقعی کانال بررسی شد.", inline_keypad=inline_keyboard(((f"approve:{request.id}", "✅ فعال‌سازی"),)))
                except (ValueError, RuntimeError) as exc: await db.rollback(); await reply(event, f"⛔ احراز انجام نشد: {exc}")
                return
            if action.startswith("approve:"):
                request = await db.scalar(select(RegistrationRequest).where(RegistrationRequest.id == action.split(":", 1)[1], RegistrationRequest.status == RegistrationStatus.PENDING_VERIFICATION))
                if not request: await db.commit(); await reply(event, "❌ درخواست پیدا نشد."); return
                try: await RegistrationService(db).verify(request, approved=True, verifier_id=user.id); await db.commit(); await reply(event, "✅ کانال فعال شد.", keypad=admin_keyboard())
                except ValueError as exc: await db.rollback(); await reply(event, f"⛔ فعال‌سازی انجام نشد: {exc}")
                return
            if action.startswith("reject:"):
                request = await db.scalar(select(RegistrationRequest).where(RegistrationRequest.id == action.split(":", 1)[1], RegistrationRequest.status == RegistrationStatus.PENDING_VERIFICATION))
                if request: await RegistrationService(db).verify(request, approved=False, verifier_id=user.id); await db.commit(); await reply(event, "🚫 درخواست رد شد.", keypad=admin_keyboard())
                return
            await db.commit()

    @bot.on_callback()
    async def on_callback(bot, event):
        if not is_duplicate_update(event):
            action = button_id(event)
            if action: await handle_action(event, action)

    mapping = {
        "📥 درخواست‌ها": "requests", "💳 پرداخت‌ها": "payments", "📺 کانال‌ها": "channels", "📋 وظایف": "tasks",
        "🎯 جذب کانال": "recruit", "📣 عملیات تبلیغ": "campaigns", "⚠️ تخلفات": "violations", "📈 عملکرد": "performance", "🎓 آموزش": "training",
    }

    @bot.on_message()
    async def handle(bot, event):
        if is_duplicate_update(event): return
        user_id = await resolve_user(bot, event)
        if not user_id: return
        text = update_text(event)
        if text in {"/start", "منو", "menu", "↩️ بازگشت"}:
            _RECRUIT_STATES.pop(user_id, None); await reply(event, "🛠 داشبورد ادمین", keypad=admin_keyboard()); return
        if _RECRUIT_STATES.get(user_id) == "recruit":
            parts = [x.strip() for x in text.split("|")]
            if len(parts) != 2 or not all(parts): await reply(event, "❌ فرمت: شناسه کانال | کد لیست"); return
            async with SessionFactory() as db:
                roles = RoleService(db, settings); user = await roles.get_or_create_user(rubika_user_id=user_id)
                if not roles.has(user, UserRole.ADMIN, UserRole.SUPERVISOR, UserRole.OWNER): await db.rollback(); _RECRUIT_STATES.pop(user_id, None); await reply(event, "⛔ دسترسی ندارید."); return
                code = parts[1].lstrip("#"); network = await db.scalar(select(ListNetwork).where(ListNetwork.code == code, ListNetwork.active.is_(True)))
                if network is None: await db.rollback(); await reply(event, "❌ کد لیست فعال پیدا نشد."); return
                try:
                    request = await RegistrationService(db).start(rubika_guid=parts[0], applicant=user, source=RegistrationSource.ADMIN_RECRUITED, recruited_by_admin_id=user.id, list_id=network.id)
                    await RegistrationService(db).submit_for_verification(request); await db.commit(); _RECRUIT_STATES.pop(user_id, None); await reply(event, f"✅ جذب ثبت شد. درخواست {request.id[:8]} در صف احراز قرار گرفت.", keypad=admin_keyboard())
                except ValueError as exc: await db.rollback(); await reply(event, f"❌ جذب ثبت نشد: {exc}")
            return
        if text in mapping: await handle_action(event, mapping[text]); return
        async with SessionFactory() as db:
            user = await RoleService(db, settings).get_or_create_user(rubika_user_id=user_id); allowed = RoleService(db, settings).has(user, UserRole.ADMIN, UserRole.SUPERVISOR, UserRole.OWNER)
        if not allowed: await reply(event, "⛔ دسترسی این ربات فقط برای ادمین‌ها و ناظران شبکه است.")

    return bot
