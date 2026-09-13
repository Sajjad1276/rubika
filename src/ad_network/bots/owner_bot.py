from fast_rub import Client
from sqlalchemy import func, select

from ..core.commerce import PriceRule
from ..core.config import Settings
from ..core.db import SessionFactory
from ..core.models import Channel, ChannelStatus, ListNetwork, User, UserRole
from ..core.roles import RoleService
from .common import button_id, inline_keyboard, reply, update_text, update_user_id


def owner_keyboard():
    return inline_keyboard(
        (("overview", "📊 نمای کلی"), ("lists", "🗂 لیست‌ها")),
        (("people", "👥 ادمین‌ها و ناظرها"), ("orders", "📢 سفارش‌ها")),
        (("pricing", "💰 تعرفه و درآمد"), ("rules", "📚 قوانین")),
        (("audit", "🧾 Audit"), ("modules", "⚙️ ماژول‌ها")),
    )


async def build_owner_bot(settings: Settings) -> Client:
    bot = Client(settings.owner_bot_token)

    async def handle_action(message, action: str):
        user_id = update_user_id(message)
        if not user_id:
            return
        async with SessionFactory() as db:
            roles = RoleService(db, settings)
            user = await roles.get_or_create_user(rubika_user_id=user_id)
            if not roles.has(user, UserRole.OWNER, UserRole.SUPERVISOR):
                await db.commit()
                await reply(message, "⛔ دسترسی ندارید.")
                return
            if action == "home":
                await db.commit()
                await reply(message, "👑 مدیریت شبکه", inline_keypad=owner_keyboard())
                return
            if action == "overview":
                lists = (await db.scalars(select(ListNetwork).where(ListNetwork.active.is_(True)))).all()
                channels = await db.scalar(select(func.count(Channel.id)).where(Channel.status == ChannelStatus.ACTIVE))
                admins = sum("admin" in (u.roles_json or "") for u in (await db.scalars(select(User))).all())
                await db.commit()
                await reply(message, f"📊 شبکه\n\nلیست فعال: {len(lists)}\nکانال فعال: {int(channels or 0)}\nادمین: {admins}", inline_keypad=owner_keyboard())
                return
            if action == "lists":
                lists = (await db.scalars(select(ListNetwork).order_by(ListNetwork.code))).all()
                lines = []
                for item in lists:
                    count = await db.scalar(select(func.count(Channel.id)).where(Channel.list_id == item.id, Channel.status == ChannelStatus.ACTIVE))
                    lines.append(f"{item.code} | {item.name} | {int(count or 0)} کانال")
                await db.commit()
                await reply(message, "🗂 لیست‌ها\n\n" + ("\n".join(lines) or "لیستی ثبت نشده است."), inline_keypad=owner_keyboard())
                return
            if action == "pricing":
                rules = (await db.scalars(select(PriceRule).where(PriceRule.active.is_(True)).order_by(PriceRule.min_channels))).all()
                lines = [f"{r.title} | حداقل {r.min_channels} | هر کانال {r.price_per_channel:,} | {r.retention_hours}h" for r in rules]
                await db.commit()
                await reply(message, "💰 تعرفه‌های فعال\n\n" + ("\n".join(lines) or "هنوز تعرفه‌ای ثبت نشده است."), inline_keypad=owner_keyboard())
                return
            responses = {
                "people": "👥 مدیریت نقش‌ها و دسترسی‌ها.", "orders": "📢 مدیریت سفارش‌ها و کمپین‌ها.",
                "rules": "📚 قوانین و قالب‌های شبکه.", "audit": "🧾 گزارش عملیات حساس.",
                "modules": "⚙️ تنظیمات ماژول‌های ربات.",
            }
            await db.commit()
            if action in responses:
                await reply(message, responses[action], inline_keypad=owner_keyboard())

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
            allowed = roles.has(user, UserRole.OWNER, UserRole.SUPERVISOR)
            await db.commit()
        if not allowed:
            await reply(message, "⛔ دسترسی این ربات فقط برای مالک و ناظر شبکه است.")
            return
        if text in {"/start", "منو", "menu"}:
            await reply(message, "👑 مدیریت شبکه", inline_keypad=owner_keyboard())

    return bot
