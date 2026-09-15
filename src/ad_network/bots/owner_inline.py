from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from ..core.campaigns import Campaign, CampaignTarget
from ..core.commerce import AdOrder, EarningsEntry, Payment, PriceRule
from ..core.db import SessionFactory
from ..core.models import AuditLog, Channel, ChannelStatus, ListAccount, ListNetwork, Task, TaskStatus, User, Violation
from .common import inline_keyboard, reply


def back(section: str):
    return inline_keyboard(((section, "🔙 بازگشت"),))


def money(value) -> str:
    return f"{int(value or 0):,}"


async def handle(event, action: str) -> bool:
    if not action:
        return False
    prefix, _, key = action.partition(":")
    handlers = {
        "report": _report,
        "tasks": _tasks,
        "security": _security,
        "notifications": _notifications,
        "finance": _finance,
        "performance": _performance,
        "violations": _violations,
        "emergency": _emergency,
    }
    handler = handlers.get(prefix)
    if handler is None:
        return False
    await handler(event, key)
    return True


async def _report(event, key: str):
    async with SessionFactory() as db:
        now = datetime.now(timezone.utc)
        periods = {"daily": 1, "weekly": 7, "monthly": 30}
        if key in periods:
            since = now - timedelta(days=periods[key])
            orders = await db.scalar(select(func.count(AdOrder.id)).where(AdOrder.created_at >= since)) or 0
            campaigns = await db.scalar(select(func.count(Campaign.id)).where(Campaign.created_at >= since)) or 0
            revenue = await db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).join(AdOrder, AdOrder.id == Payment.order_id).where(Payment.status == "confirmed", AdOrder.created_at >= since)) or 0
            violations = await db.scalar(select(func.count(Violation.id)).where(Violation.created_at >= since)) or 0
            title = {"daily": "روزانه", "weekly": "هفتگی", "monthly": "۳۰ روزه"}[key]
            text = f"📊 گزارش {title}\n━━━━━━━━━━━━━━━━━━━━\nسفارش‌ها: {orders}\nکمپین‌ها: {campaigns}\nدرآمد: {money(revenue)}\nتخلفات: {violations}"
        elif key == "finance":
            revenue = await db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "confirmed")) or 0
            earnings = await db.scalar(select(func.coalesce(func.sum(EarningsEntry.amount), 0))) or 0
            text = f"💰 گزارش مالی\n━━━━━━━━━━━━━━━━━━━━\nدرآمد: {money(revenue)}\nسهم ثبت‌شده: {money(earnings)}\nمانده: {money(int(revenue)-int(earnings))}"
        elif key == "channels":
            total = await db.scalar(select(func.count(Channel.id))) or 0
            active = await db.scalar(select(func.count(Channel.id)).where(Channel.status == ChannelStatus.ACTIVE)) or 0
            pending = await db.scalar(select(func.count(Channel.id)).where(Channel.status == ChannelStatus.PENDING)) or 0
            suspended = await db.scalar(select(func.count(Channel.id)).where(Channel.status == ChannelStatus.SUSPENDED)) or 0
            removed = await db.scalar(select(func.count(Channel.id)).where(Channel.status == ChannelStatus.REMOVED)) or 0
            text = f"📺 گزارش کانال‌ها\n━━━━━━━━━━━━━━━━━━━━\nکل: {total}\nفعال: {active}\nدر انتظار: {pending}\nتعلیق: {suspended}\nحذف: {removed}"
        elif key == "lists":
            total = await db.scalar(select(func.count(ListNetwork.id))) or 0
            active = await db.scalar(select(func.count(ListNetwork.id)).where(ListNetwork.active.is_(True))) or 0
            capacity = await db.scalar(select(func.coalesce(func.sum(ListNetwork.max_channels), 0))) or 0
            text = f"🗂 گزارش لیست‌ها\n━━━━━━━━━━━━━━━━━━━━\nکل: {total}\nفعال: {active}\nظرفیت: {capacity}"
        elif key == "campaigns":
            total = await db.scalar(select(func.count(Campaign.id))) or 0
            active = await db.scalar(select(func.count(Campaign.id)).where(Campaign.status.in_(["active", "scheduled"]))) or 0
            done = await db.scalar(select(func.count(Campaign.id)).where(Campaign.status == "completed")) or 0
            failed = await db.scalar(select(func.count(Campaign.id)).where(Campaign.status == "failed")) or 0
            text = f"📢 گزارش تبلیغات\n━━━━━━━━━━━━━━━━━━━━\nکل: {total}\nفعال/زمان‌بندی: {active}\nتکمیل: {done}\nناموفق: {failed}"
        elif key == "violations":
            total = await db.scalar(select(func.count(Violation.id))) or 0
            open_count = await db.scalar(select(func.count(Violation.id)).where(Violation.resolved.is_(False))) or 0
            critical = await db.scalar(select(func.count(Violation.id)).where(Violation.resolved.is_(False), Violation.severity >= 3)) or 0
            text = f"⚠️ گزارش تخلفات\n━━━━━━━━━━━━━━━━━━━━\nکل: {total}\nباز: {open_count}\nپرخطر: {critical}"
        else:
            await db.rollback()
            return
        await db.commit()
    await reply(event, text, inline_keypad=back("reports"))


async def _tasks(event, key: str):
    async with SessionFactory() as db:
        query = select(Task).order_by(Task.created_at.desc()).limit(30)
        filters = {"pending": TaskStatus.PENDING, "active": TaskStatus.IN_PROGRESS, "done": TaskStatus.DONE}
        if key in filters:
            query = query.where(Task.status == filters[key])
        elif key == "urgent":
            query = query.where(Task.task_type.ilike("%urgent%"), Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]))
        rows = list((await db.scalars(query)).all())
        text = "🧩 وظایف\n━━━━━━━━━━━━━━━━━━━━\n" + ("\n".join(f"{x.id[:8]} | {x.task_type} | {x.status.value}" for x in rows) or "موردی وجود ندارد.")
        await db.commit()
    await reply(event, text, inline_keypad=back("tasks"))


async def _security(event, key: str):
    async with SessionFactory() as db:
        if key == "audit":
            rows = list((await db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(20))).all())
            text = "🧾 ثبت رویدادها\n━━━━━━━━━━━━━━━━━━━━\n" + ("\n".join(f"{x.action} | {x.entity_type}:{x.entity_id[:8]}" for x in rows) or "رویدادی ثبت نشده است.")
        elif key == "people":
            total = await db.scalar(select(func.count(User.id))) or 0
            admins = await db.scalar(select(func.count(User.id)).where(User.roles_json.ilike("%admin%"))) or 0
            owners = await db.scalar(select(func.count(User.id)).where(User.roles_json.ilike("%owner%"))) or 0
            text = f"👤 دسترسی‌ها\n━━━━━━━━━━━━━━━━━━━━\nکاربران: {total}\nادمین: {admins}\nمالک: {owners}"
        elif key == "critical":
            count = await db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "sensitive_action")) or 0
            text = f"🚨 رخدادهای حساس\n━━━━━━━━━━━━━━━━━━━━\nتعداد: {count}"
        else:
            text = "🔒 تنظیمات امنیتی\n━━━━━━━━━━━━━━━━━━━━\nاحراز نقش مالک و ناظر فعال است.\nثبت عملیات حساس فعال است.\nثبت عملیات مالی در گزارش رویدادها انجام می‌شود."
        await db.commit()
    await reply(event, text, inline_keypad=back("security"))


async def _notifications(event, key: str):
    async with SessionFactory() as db:
        query = select(Violation).where(Violation.resolved.is_(False)).order_by(Violation.created_at.desc()).limit(20)
        if key == "critical":
            query = query.where(Violation.severity >= 3)
        elif key == "warnings":
            query = query.where(Violation.severity == 2)
        elif key == "info":
            query = query.where(Violation.severity <= 1)
        rows = [] if key == "readall" else list((await db.scalars(query)).all())
        text = "✔️ اعلان‌ها\n━━━━━━━━━━━━━━━━━━━━\nرخدادهای اعلان از وضعیت تخلفات تغذیه می‌شوند.\n" + ("\n".join(f"{x.violation_type} | شدت {x.severity}" for x in rows) if rows else "اعلانی وجود ندارد.")
        await db.commit()
    await reply(event, text, inline_keypad=back("notifications"))


async def _finance(event, key: str):
    async with SessionFactory() as db:
        if key == "revenue":
            total = await db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "confirmed")) or 0
            today = await db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "confirmed", func.date(Payment.confirmed_at) == datetime.now(timezone.utc).date())) or 0
            text = f"📊 درآمد\n━━━━━━━━━━━━━━━━━━━━\nامروز: {money(today)}\nکل: {money(total)}"
        elif key == "payments":
            pending = await db.scalar(select(func.count(Payment.id)).where(Payment.status == "pending")) or 0
            confirmed = await db.scalar(select(func.count(Payment.id)).where(Payment.status == "confirmed")) or 0
            rejected = await db.scalar(select(func.count(Payment.id)).where(Payment.status == "rejected")) or 0
            text = f"💳 پرداخت‌ها\n━━━━━━━━━━━━━━━━━━━━\nدر انتظار: {pending}\nتأیید: {confirmed}\nرد: {rejected}"
        elif key == "pricing":
            rules = list((await db.scalars(select(PriceRule).where(PriceRule.active.is_(True)).order_by(PriceRule.min_channels))).all())
            text = "💵 تعرفه‌ها\n━━━━━━━━━━━━━━━━━━━━\n" + ("\n".join(f"{r.title} | {money(r.price_per_channel)} / کانال | {r.retention_hours}ساعت" for r in rules) or "تعرفه فعالی وجود ندارد.")
        elif key == "profit":
            revenue = await db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "confirmed")) or 0
            earnings = await db.scalar(select(func.coalesce(func.sum(EarningsEntry.amount), 0))) or 0
            text = f"📈 سود و زیان\n━━━━━━━━━━━━━━━━━━━━\nدرآمد: {money(revenue)}\nسهم: {money(earnings)}\nمانده: {money(int(revenue)-int(earnings))}"
        else:
            return
        await db.commit()
    await reply(event, text, inline_keypad=back("finance"))


async def _performance(event, key: str):
    async with SessionFactory() as db:
        if key == "lists":
            total = await db.scalar(select(func.count(ListNetwork.id))) or 0
            active = await db.scalar(select(func.count(ListNetwork.id)).where(ListNetwork.active.is_(True))) or 0
            text = f"🗂 عملکرد لیست‌ها\n━━━━━━━━━━━━━━━━━━━━\nکل: {total}\nفعال: {active}"
        elif key == "channels":
            total = await db.scalar(select(func.count(Channel.id))) or 0
            active = await db.scalar(select(func.count(Channel.id)).where(Channel.status == ChannelStatus.ACTIVE)) or 0
            text = f"📺 عملکرد کانال‌ها\n━━━━━━━━━━━━━━━━━━━━\nکل: {total}\nفعال: {active}"
        elif key == "campaigns":
            total = await db.scalar(select(func.count(CampaignTarget.id))) or 0
            retained = await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.status == "retained")) or 0
            failed = await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.status == "failed")) or 0
            text = f"📢 عملکرد تبلیغات\n━━━━━━━━━━━━━━━━━━━━\nهدف‌ها: {total}\nماندگار: {retained}\nناموفق: {failed}"
        elif key == "finance":
            revenue = await db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "confirmed")) or 0
            earnings = await db.scalar(select(func.coalesce(func.sum(EarningsEntry.amount), 0))) or 0
            text = f"💰 عملکرد مالی\n━━━━━━━━━━━━━━━━━━━━\nدرآمد: {money(revenue)}\nسهم: {money(earnings)}"
        else:
            return
        await db.commit()
    await reply(event, text, inline_keypad=back("performance"))


async def _violations(event, key: str):
    async with SessionFactory() as db:
        if key == "risk":
            rows = list((await db.scalars(select(Violation).where(Violation.resolved.is_(False), Violation.severity >= 3).order_by(Violation.created_at.desc()).limit(30))).all())
            text = "🔥 تخلفات پرخطر\n━━━━━━━━━━━━━━━━━━━━\n" + ("\n".join(f"{x.violation_type} | شدت {x.severity}" for x in rows) or "مورد پرخطری وجود ندارد.")
        elif key == "stats":
            total = await db.scalar(select(func.count(Violation.id))) or 0
            resolved = await db.scalar(select(func.count(Violation.id)).where(Violation.resolved.is_(True))) or 0
            text = f"📊 آمار تخلفات\n━━━━━━━━━━━━━━━━━━━━\nکل: {total}\nباز: {int(total)-int(resolved)}\nحل‌شده: {resolved}"
        else:
            return
        await db.commit()
    await reply(event, text, inline_keypad=back("violations"))


async def _emergency(event, key: str):
    async with SessionFactory() as db:
        if key in {"ads", "rotation"}:
            rows = list((await db.scalars(select(Campaign).where(Campaign.status.in_(["active", "scheduled"]))).all()))
            for row in rows:
                row.status = "paused"
            text = f"🛑 توقف تبلیغات\n━━━━━━━━━━━━━━━━━━━━\n{len(rows)} کمپین متوقف شد."
        elif key == "lists":
            rows = list((await db.scalars(select(ListNetwork).where(ListNetwork.active.is_(True))).all()))
            for row in rows:
                row.active = False
                row.status = "paused"
            text = f"🛑 توقف لیست‌ها\n━━━━━━━━━━━━━━━━━━━━\n{len(rows)} لیست متوقف شد."
        elif key == "resume":
            rows = list((await db.scalars(select(ListNetwork).where(ListNetwork.status == "paused")).all()))
            for row in rows:
                row.active = True
                row.status = "active"
            text = f"▶️ ادامه عملیات\n━━━━━━━━━━━━━━━━━━━━\n{len(rows)} لیست فعال شد."
        elif key == "reconnect":
            count = await db.scalar(select(func.count(ListAccount.id)).where(ListAccount.active.is_(True))) or 0
            text = f"🔄 اتصال اکانت‌ها\n━━━━━━━━━━━━━━━━━━━━\n{count} اکانت فعال در چرخه همگام‌سازی قرار دارد."
        elif key == "workers":
            text = "🛑 توقف worker\n━━━━━━━━━━━━━━━━━━━━\nاین کنترل به runtime متصل نشده است و عمداً وضعیت جعلی گزارش نمی‌کند."
        else:
            return
        await db.commit()
    await reply(event, text, inline_keypad=back("emergency"))
