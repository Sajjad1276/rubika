from fast_rub import Client
from sqlalchemy import func, select

from ..core.commerce import PriceRule
from ..core.config import Settings
from ..core.db import SessionFactory
from ..core.models import Channel, ChannelStatus, ListNetwork, User, UserRole
from ..core.roles import RoleService
from .common import reply, update_text, update_user_id


async def build_owner_bot(settings: Settings) -> Client:
    bot = Client(settings.owner_bot_token)

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
            if not allowed:
                await db.commit()
                await reply(message, "⛔ دسترسی این ربات فقط برای مالک و ناظر شبکه است.")
                return

            if text in {"/start", "منو", "menu"}:
                await db.commit()
                await reply(
                    message,
                    "👑 مدیریت شبکه\n\n"
                    "1️⃣ نمای کلی شبکه\n2️⃣ لیست‌ها\n3️⃣ ادمین‌ها و ناظرها\n"
                    "4️⃣ سفارش‌ها و کمپین‌ها\n5️⃣ تعرفه و درآمد\n6️⃣ قوانین و قالب‌ها\n"
                    "7️⃣ گزارش و Audit\n8️⃣ تنظیمات ماژول‌ها",
                )
                return

            if text == "1":
                lists = (await db.scalars(select(ListNetwork).where(ListNetwork.active.is_(True)))).all()
                channels = await db.scalar(select(func.count(Channel.id)).where(Channel.status == ChannelStatus.ACTIVE))
                admins = await db.scalar(select(func.count(User.id)).where(User.roles_json.contains("admin")))
                await db.commit()
                await reply(message, f"📊 شبکه\n\nلیست فعال: {len(lists)}\nکانال فعال: {int(channels or 0)}\nادمین: {int(admins or 0)}")
                return

            if text == "2":
                lists = (await db.scalars(select(ListNetwork).order_by(ListNetwork.code))).all()
                lines = []
                for item in lists:
                    count = await db.scalar(select(func.count(Channel.id)).where(
                        Channel.list_id == item.id, Channel.status == ChannelStatus.ACTIVE
                    ))
                    lines.append(f"{item.code} | {item.name} | {int(count or 0)} کانال")
                await db.commit()
                await reply(message, "🗂 لیست‌ها\n\n" + ("\n".join(lines) or "لیستی ثبت نشده است."))
                return

            if text == "5":
                rules = (await db.scalars(select(PriceRule).where(PriceRule.active.is_(True)).order_by(PriceRule.min_channels))).all()
                if not rules:
                    await db.commit()
                    await reply(message, "💰 هنوز تعرفه‌ای ثبت نشده.\nنمونه: تعرفه <list_id> <حداقل> <قیمت_هر_کانال> <ساعت>")
                    return
                lines = [f"{r.title} | حداقل {r.min_channels} | هر کانال {r.price_per_channel:,} | {r.retention_hours}h" for r in rules]
                await db.commit()
                await reply(message, "💰 تعرفه‌های فعال\n\n" + "\n".join(lines))
                return

            parts = text.split()
            if parts and parts[0] in {"تعرفه", "price"} and len(parts) == 5:
                try:
                    list_id, minimum, unit, hours = parts[1], int(parts[2]), int(parts[3]), int(parts[4])
                    if minimum <= 0 or unit < 0 or hours <= 0:
                        raise ValueError
                    if await db.get(ListNetwork, list_id) is None:
                        raise ValueError("list not found")
                    rule = PriceRule(list_id=list_id, title=f"تعرفه {list_id[:8]}", min_channels=minimum,
                                     price_per_channel=unit, retention_hours=hours, active=True)
                    db.add(rule)
                    await db.commit()
                    await reply(message, "✅ تعرفه ثبت شد.")
                except ValueError as exc:
                    await db.rollback()
                    await reply(message, f"❌ فرمت تعرفه نامعتبر است: {exc}")
                return

            responses = {
                "3": "👥 مدیریت ادمین‌ها، ناظرها و دسترسی‌ها.",
                "4": "📢 سفارش‌ها و کمپین‌ها.",
                "6": "📚 قوانین و قالب‌های شبکه.",
                "7": "🧾 گزارش Audit و عملیات حساس.",
                "8": "⚙️ تنظیمات ماژول‌های ربات.",
            }
            await db.commit()
            if text in responses:
                await reply(message, responses[text])

    return bot
