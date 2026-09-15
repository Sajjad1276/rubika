from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from ..core.campaigns import Campaign, CampaignTarget
from ..core.commerce import AdOrder, EarningsEntry, Payment, PriceRule
from ..core.db import SessionFactory
from ..core.models import AuditLog, Channel, ChannelStatus, ListAccount, ListNetwork, Task, TaskStatus, User
from .common import inline_keyboard, reply


_STATUS = {
    "active": "فعال",
    "scheduled": "زمان‌بندی‌شده",
    "paused": "متوقف",
    "completed": "تکمیل‌شده",
    "failed": "ناموفق",
    "pending": "در انتظار",
    "in_progress": "در حال اجرا",
    "done": "تکمیل‌شده",
}


def _back(section: str) -> dict:
    return inline_keyboard(((section, "🔙 بازگشت"),))


def _money(value: int | None) -> str:
    return f"{int(value or 0):,}"


async def handle_owner_inline_action(event, action: str) -> bool:
    """Handle inline buttons that previously only reopened their parent panel."""
    if not action:
        return False

    if action.startswith("report:"):
        await _report(event, action.split(":", 1)[1])
        return True
    if action.startswith("tasks:"):
        await _tasks(event, action.split(":", 1)[1])
        return True
    if action.startswith("security:"):
        await _security(event, action.split(":", 1)[1])
        return True
    if action.startswith("notifications:"):
        await _notifications(event, action.split(":", 1)[1])
        return True
    if action.startswith("finance:"):
        await _finance(event, action.split(":", 1)[1])
        return True
    if action.startswith("performance:"):
        await _performance(event, action.split(":", 1)[1])
        return True
    if action.startswith("violations:"):
        await _violations(event, action.split(":", 1)[1])
        return True
    if action.startswith("emergency:"):
        await _emergency(event, action.split(":", 1)[1])
        return True
    return False


async def _report(event, kind: str) -> None:
    async with SessionFactory() as db:
        now = datetime.now(timezone.utc)
        if kind == "daily":
            since = now - timedelta(days=1)
            title = "📊 گزارش روزانه"
            order_filter = AdOrder.created_at >= since
            violation_filter = Violation.created_at >= since
        elif kind == "weekly":
            since = now - timedelta(days=7)
            title = "📊 گزارش هفتگی"
            order_filter = AdOrder.created_at >= since
            violation_filter = Violation.created_at >= since
        elif kind == "monthly":
            since = now - timedelta(days=30)
            title = "📊 گزارش ۳۰ روزه"
            order_filter = AdOrder.created_at >= since
            violation_filter = Violation.created_at >= since
        elif kind == "finance":
            revenue = await db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "confirmed")) or 0
            earnings = await db.scalar(select(func.coalesce(func.sum(EarningsEntry.amount), 0))) or 0
            payments = await db.scalar(select(func.count(Payment.id)).where(Payment.status == "confirmed")) or 0
            await db.commit()
            await reply(event, f"💰 گزارش مالی\n━━━━━━━━━━━━━━━━━━━━\nپرداخت تأییدشده: {payments}\nدرآمد: {_money(revenue)}\nسهم ثبت‌شده: {_money(earnings)}\nمانده ثبت‌نشده: {_money(int(revenue) - int(earnings))}", inline_keypad=_back("reports"))
            return
        elif kind == "channels":
            total = await db.scalar(select(func.count(Channel.id))) or 0
            active = await db.scalar(select(func.count(Channel.id)).where(Channel.status == ChannelStatus.ACTIVE)) or 0
            pending = await db.scalar(select(func.count(Channel.id)).where(Channel.status == ChannelStatus.PENDING)) or 0
            suspended = await db.scalar(select(func.count(Channel.id)).where(Channel.status == ChannelStatus.SUSPENDED)) or 0
            removed = await db.scalar(select(func.count(Channel.id)).where(Channel.status == ChannelStatus.REMOVED)) or 0
            await db.commit()
            await reply(event, f"📺 گزارش کانال‌ها\n━━━━━━━━━━━━━━━━━━━━\nکل: {total}\nفعال: {active}\nدر انتظار: {pending}\nتعلیق: {suspended}\nحذف‌شده: {removed}", inline_keypad=_back("reports"))
            return
        elif kind == "lists":
            total = await db.scalar(select(func.count(ListNetwork.id))) or 0
            active = await db.scalar(select(func.count(ListNetwork.id)).where(ListNetwork.active.is_(True))) or 0
            capacity = await db.scalar(select(func.coalesce(func.sum(ListNetwork.max_channels), 0))) or 0
            await db.commit()
            await reply(event, f"🗂 گزارش لیست‌ها\n━━━━━━━━━━━━━━━━━━━━\nکل: {total}\nفعال: {active}\nظرفیت کل: {capacity}", inline_keypad=_back("reports"))
            return
        elif kind == "campaigns":
            total = await db.scalar(select(func.count(Campaign.id))) or 0
            active = await db.scalar(select(func.count(Campaign.id)).where(Campaign.status.in_(["active", "scheduled"]))) or 0
            done = await db.scalar(select(func.count(Campaign.id)).where(Campaign.status == "completed")) or 0
            failed = await db.scalar(select(func.count(Campaign.id)).where(Campaign.status == "failed")) or 0
            await db.commit()
            await reply(event, f"📢 گزارش تبلیغات\n━━━━━━━━━━━━━━━━━━━━\nکل: {total}\nفعال/زمان‌بندی: {active}\nتکمیل: {done}\nناموفق: {failed}", inline_keypad=_back("reports"))
            return
        elif kind == "violations":
            total = await db.scalar(select(func.count(Violation.id))) or 0
            open_count = await db.scalar(select(func.count(Violation.id)).where(Violation.resolved.is_(False))) or 0
            critical = await db.scalar(select(func.count(Violation.id)).where(Violation.resolved.is_(False), Violation.severity >= 3)) or 0
            await db.commit()
            await reply(event, f"⚠️ گزارش تخلفات\n━━━━━━━━━━━━━━━━━━━━\nکل: {total}\nباز: {open_count}\nپرخطر: {critical}", inline_keypad=_back("reports"))
            return
        else:
            return

        orders = await db.scalar(select(func.count(AdOrder.id)).where(order_filter)) or 0
        revenue = await db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).join(AdOrder, AdOrder.id == Payment.order_id).where(Payment.status == "confirmed", order_filter)) or 0
        violations = await db.scalar(select(func.count(Violation.id)).where(violation_filter)) or 0
        campaigns = await db.scalar(select(func.count(Campaign.id)).where(Campaign.created_at >= since)) or 0
        await db.commit()
        await reply(event, f"{title}\n━━━━━━━━━━━━━━━━━━━━\nسفارش‌ها: {orders}\nکمپین‌ها: {campaigns}\nدرآمد: {_money(revenue)}\nتخلفات: {violations}", inline_keypad=_back("reports"))


async def _tasks(event, kind: str) -> None:
    async with SessionFactory() as db:
        query = select(Task).order_by(Task.created_at.desc()).limit(30)
        if kind == "pending":
            query = query.where(Task.status == TaskStatus.PENDING)
        elif kind == "urgent":
            query = query.where(Task.task_type.ilike("%urgent%"), Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]))
        elif kind == "active":
            query = query.where(Task.status == TaskStatus.IN_PROGRESS)
        elif kind == "done":
            query = query.where(Task.status == TaskStatus.DONE)
        rows = list((await db.scalars(query)).all())
        lines = [f"{task.id[:8]} | {task.task_type} | {_STATUS.get(str(task.status), str(task.status))}" for task in rows]
        await db.commit()
    await reply(event, "🧩 وظایف\n━━━━━━━━━━━━━━━━━━━━\n" + ("\n".join(lines) or "موردی وجود ندارد."), inline_keypad=_back("tasks"))


async def _security(event, kind: str) -> None:
    async with SessionFactory() as db:
        if kind == "audit":
            rows = list((await db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(20))).all())
            text = "🧾 ثبت رویدادها\n━━━━━━━━━━━━━━━━━━━━\n" + ("\n".join(f"{x.action} | {x.entity_type}:{x.entity_id[:8]}" for x in rows) or "رویدادی ثبت نشده است.")
        elif kind == "people":
            total = await db.scalar(select(func.count(User.id))) or 0
            admins = await db.scalar(select(func.count(User.id)).where(User.roles_json.ilike("%admin%"))) or 0
            owners = await db.scalar(select(func.count(User.id)).where(User.roles_json.ilike("%owner%"))) or 0
            text = f"👤 دسترسی‌ها\n━━━━━━━━━━━━━━━━━━━━\nکل کاربران: {total}\nادمین‌ها: {admins}\nمالک‌ها: {owners}"
        elif kind == "critical":
            count = await db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action.in_(["sensitive_action", "payment_confirmed"]))) or 0
            text = f"🚨 رخدادهای حساس\n━━━━━━━━━━━━━━━━━━━━\nرخدادهای حساس ثبت‌شده: {count}"
        else:
            text = "🔒 تنظیمات امنیتی\n━━━━━━━━━━━━━━━━━━━━\nاحراز نقش مالک/ناظر فعال است.\nثبت رویداد عملیات حساس فعال است.\nتأییدهای مالی در Audit Log ثبت می‌شوند."
        await db.commit()
    await reply(event, text, inline_keypad=_back("security"))


async def _notifications(event, kind: str) -> None:
    async with SessionFactory() as db:
        query = select(Violation).order_by(Violation.created_at.desc()).limit(20)
        if kind == "critical":
            query = query.where(Violation.resolved.is_(False), Violation.severity >= 3)
        elif kind == "warnings":
            query = query.where(Violation.resolved.is_(False), Violation.severity == 2)
        elif kind == "info":
            query = query.where(Violation.resolved.is_(False), Violation.severity <= 1)
        rows = list((await db.scalars(query)).all()) if kind != "readall" else []
        if kind == "readall":
            text = "✔️ اعلان‌ها\n━━━━━━━━━━━━━━━━━━━━\nمدل اعلان مستقل هنوز در دیتابیس تعریف نشده است؛ رخدادهای عملیاتی از تخلفات تغذیه می‌شوند."
        else:
            text = "🔔 اعلان‌ها\n━━━━━━━━━━━━━━━━━━━━\n" + ("\n".join(f"{x.violation_type} | شدت {x.severity}" for x in rows) or "اعلانی وجود ندارد.")
        await db.commit()
    await reply(event, text, inline_keypad=_back("notifications"))


async def _finance(event, kind: str) -> None:
    async with SessionFactory() as db:
        if kind == "revenue":
            total = await db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "confirmed")) or 0
            today = await db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "confirmed", func.date(Payment.confirmed_at) == datetime.now(timezone.utc).date())) or 0
            text = f"📊 درآمد\n━━━━━━━━━━━━━━━━━━━━\nامروز: {_money(today)}\nکل: {_money(total)}"
        elif kind == "payments":
            pending = await db.scalar(select(func.count(Payment.id)).where(Payment.status == "pending")) or 0
            confirmed = await db.scalar(select(func.count(Payment.id)).where(Payment.status == "confirmed")) or 0
            rejected = await db.scalar(select(func.count(Payment.id)).where(Payment.status == "rejected")) or 0
            text = f"💳 پرداخت‌ها\n━━━━━━━━━━━━━━━━━━━━\nدر انتظار: {pending}\nتأییدشده: {confirmed}\nردشده: {rejected}"
        elif kind == "pricing":
            rules = list((await db.scalars(select(PriceRule).where(PriceRule.active.is_(True)).order_by(PriceRule.min_channels))).all())
            text = "💵 تعرفه‌ها\n━━━━━━━━━━━━━━━━━━━━\n" + ("\n".join(f"{r.title} | حداقل {r.min_channels} | هر کانال {_money(r.price_per_channel)} | {r.retention_hours}ساعت" for r in rules) or "تعرفه فعالی ثبت نشده است.")
        else:
            revenue = await db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "confirmed")) or 0
            cost = await db.scalar(select(func.coalesce(func.sum(EarningsEntry.amount), 0))) or 0
            text = f"📈 سود و زیان\n━━━━━━━━━━━━━━━━━━━━\nدرآمد: {_money(revenue)}\nسهم ثبت‌شده: {_money(cost)}\nمانده: {_money(int(revenue) - int(cost))}"
        await db.commit()
    await reply(event, text, inline_keypad=_back("finance"))


async def _performance(event, kind: str) -> None:
    async with SessionFactory() as db:
        if kind == "lists":
            total = await db.scalar(select(func.count(ListNetwork.id))) or 0
            active = await db.scalar(select(func.count(ListNetwork.id)).where(ListNetwork.active.is_(True))) or 0
            text = f"🗂 عملکرد لیست‌ها\n━━━━━━━━━━━━━━━━━━━━\nکل: {total}\nفعال: {active}"
        elif kind == "channels":
            total = await db.scalar(select(func.count(Channel.id))) or 0
            active = await db.scalar(select(func.count(Channel.id)).where(Channel.status == ChannelStatus.ACTIVE)) or 0
            text = f"📺 عملکرد کانال‌ها\n━━━━━━━━━━━━━━━━━━━━\nکل: {total}\nفعال: {active}"
        elif kind == "campaigns":
            total = await db.scalar(select(func.count(CampaignTarget.id))) or 0
            done = await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.status == "retained")) or 0
            failed = await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.status == "failed")) or 0
            text = f"📢 عملکرد تبلیغات\n━━━━━━━━━━━━━━━━━━━━\nهدف‌ها: {total}\nماندگار: {done}\nناموفق: {failed}"
        else:
            revenue = await db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "confirmed")) or 0
            earnings = await db.scalar(select(func.coalesce(func.sum(EarningsEntry.amount), 0))) or 0
            text = f"💰 عملکرد مالی\n━━━━━━━━━━━━━━━━━━━━\nدرآمد: {_money(revenue)}\nسهم‌ها: {_money(earnings)}"
        await db.commit()
    await reply(event, text, inline_keypad=_back("performance"))


async def _violations(event, kind: str) -> None:
    async with SessionFactory() as db:
        if kind == "risk":
            rows = list((await db.scalars(select(Violation).where(Violation.resolved.is_(False), Violation.severity >= 3).order_by(Violation.created_at.desc()).limit(30))).all())
            text = "🔥 تخلفات پرخطر\n━━━━━━━━━━━━━━━━━━━━\n" + ("\n".join(f"{x.violation_type} | شدت {x.severity} | کانال {x.channel_id[:8]}" for x in rows) or "مورد پرخطری وجود ندارد.")
        else:
            total = await db.scalar(select(func.count(Violation.id))) or 0
            resolved = await db.scalar(select(func.count(Violation.id)).where(Violation.resolved.is_(True))) or 0
            open_count = int(total) - int(resolved)
            text = f"📊 آمار تخلفات\n━━━━━━━━━━━━━━━━━━━━\nکل: {total}\nباز: {open_count}\nحل‌شده: {resolved}"
        await db.commit()
    await reply(event, text, inline_keypad=_back("violations"))


async def _emergency(event, kind: str) -> None:
    async with SessionFactory() as db:
        if kind in {"ads", "rotation"}:
            result = await db.execute(select(Campaign).where(Campaign.status.in_(["active", "scheduled"])))
            campaigns = list(result.scalars().all())
            for campaign in campaigns:
                campaign.status = "paused"
            changed = len(campaigns)
            message = f"🛑 عملیات اضطراری تبلیغات\n━━━━━━━━━━━━━━━━━━━━\n{changed} کمپین متوقف شد."
        elif kind == "lists":
            result = await db.execute(select(ListNetwork).where(ListNetwork.active.is_(True)))
            lists = list(result.scalars().all())
            for network_list in lists:
                network_list.active = False
                network_list.status = "paused"
            message = f"🛑 توقف لیست‌ها\n━━━━━━━━━━━━━━━━━━━━\n{len(lists)} لیست متوقف شد."
        elif kind == "reconnect":
            active = await db.scalar(select(func.count(ListAccount.id)).where(ListAccount.active.is_(True))) or 0
            message = f"🔄 اتصال مجدد اکانت‌ها\n━━━━━━━━━━━━━━━━━━━━\n{active} اکانت فعال در چرخه همگام‌سازی قرار دارد."
        elif kind == "resume":
            result = await db.execute(select(ListNetwork).where(ListNetwork.status == "paused"))
            lists = list(result.scalars().all())
            for network_list in lists:
                network_list.active = True
                network_list.status = "active"
            message = f"▶️ ادامه عملیات\n━━━━━━━━━━━━━━━━━━━━\n{len(lists)} لیست دوباره فعال شد."
        else:
            message = "🛑 کنترل کارگرها\n━━━━━━━━━━━━━━━━━━━━\nوضعیت توقف در سطح اجرای worker نیازمند کنترل runtime است؛ این دکمه فعلاً وضعیت را گزارش می‌کند و ادعای توقف جعلی ندارد."
        await db.commit()
    await reply(event, message, inline_keypad=_back("emergency"))
