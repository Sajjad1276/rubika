from sqlalchemy import func, select

from ..core.commerce import PriceRule
from ..core.config import Settings
from ..core.db import SessionFactory
from ..core.models import Channel, ChannelStatus, ListNetwork, User, UserRole
from ..core.roles import RoleService
from .common import button_id, inline_keyboard, is_duplicate_update, quick_keyboard, reply, resolve_user, update_text

_STATES: dict[str, str] = {}


def owner_keyboard():
    return quick_keyboard(
        (("overview", "📊 نمای کلی"), ("lists", "🗂 لیست‌ها")),
        (("people", "👥 ادمین‌ها و ناظرها"), ("orders", "📢 سفارش‌ها")),
        (("pricing", "💰 تعرفه و درآمد"), ("rules", "📚 قوانین")),
        (("audit", "🧾 Audit"), ("modules", "⚙️ ماژول‌ها")),
    )


async def build_owner_bot(settings: Settings):
    from maxrubika import Bot

    bot = Bot(settings.owner_bot_token, timeout=30, max_retries=5)

    async def handle_action(event, action: str):
        user_id = await resolve_user(bot, event)
        if not user_id:
            return
        async with SessionFactory() as db:
            roles = RoleService(db, settings)
            user = await roles.get_or_create_user(rubika_user_id=user_id)
            if not roles.has(user, UserRole.OWNER, UserRole.SUPERVISOR):
                await db.commit(); await reply(event, "⛔ دسترسی ندارید."); return
            if action in {"home", "back"}:
                await db.commit(); await reply(event, "👑 مدیریت شبکه", keypad=owner_keyboard()); return
            if action == "overview":
                lists = (await db.scalars(select(ListNetwork).where(ListNetwork.active.is_(True)))).all()
                channels = await db.scalar(select(func.count(Channel.id)).where(Channel.status == ChannelStatus.ACTIVE))
                admins = sum("admin" in (u.roles_json or "") for u in (await db.scalars(select(User))).all())
                await db.commit(); await reply(event, f"📊 شبکه\n\nلیست فعال: {len(lists)}\nکانال فعال: {int(channels or 0)}\nادمین: {admins}", keypad=owner_keyboard()); return
            if action == "lists":
                lists = (await db.scalars(select(ListNetwork).order_by(ListNetwork.code))).all()
                lines = []
                for item in lists:
                    count = await db.scalar(select(func.count(Channel.id)).where(Channel.list_id == item.id, Channel.status == ChannelStatus.ACTIVE))
                    lines.append(f"{item.code} | {item.name} | {int(count or 0)} کانال")
                await db.commit(); await reply(event, "🗂 لیست‌ها\n\n" + ("\n".join(lines) or "لیستی ثبت نشده است."), inline_keypad=inline_keyboard((("list:add", "➕ ساخت لیست"),))); return
            if action == "list:add":
                _STATES[user_id] = "list"; await db.commit(); await reply(event, "➕ ساخت لیست\nفرمت: کد | نام لیست | حداقل کانال\nمثال: 001 | سحابی | 20"); return
            if action == "pricing":
                rules = (await db.scalars(select(PriceRule).where(PriceRule.active.is_(True)).order_by(PriceRule.min_channels))).all()
                lines = [f"{r.title} | لیست {r.list_id or 'عمومی'} | حداقل {r.min_channels} | هر کانال {r.price_per_channel:,} | {r.retention_hours}h" for r in rules]
                await db.commit(); await reply(event, "💰 تعرفه‌های فعال\n\n" + ("\n".join(lines) or "هنوز تعرفه‌ای ثبت نشده است."), inline_keypad=inline_keyboard((("price:add", "➕ ثبت تعرفه"),))); return
            if action == "price:add":
                _STATES[user_id] = "price"; await db.commit(); await reply(event, "➕ ثبت تعرفه\nفرمت: کد لیست | عنوان | حداقل کانال | قیمت هر کانال | ساعت ماندگاری\nمثال: 001 | پایه | 20 | 50000 | 6"); return
            responses = {
                "people": "👥 مدیریت نقش‌ها و دسترسی‌ها.", "orders": "📢 مدیریت سفارش‌ها و کمپین‌ها.",
                "rules": "📚 قوانین و قالب‌های شبکه.", "audit": "🧾 گزارش عملیات حساس.",
                "modules": "⚙️ تنظیمات ماژول‌های ربات.",
            }
            await db.commit()
            if action in responses:
                await reply(event, responses[action], keypad=owner_keyboard())

    @bot.on_callback()
    async def on_callback(bot, event):
        if is_duplicate_update(event):
            return
        action = button_id(event)
        if action:
            await handle_action(event, action)

    mapping = {
        "📊 نمای کلی": "overview", "🗂 لیست‌ها": "lists", "👥 ادمین‌ها و ناظرها": "people", "📢 سفارش‌ها": "orders",
        "💰 تعرفه و درآمد": "pricing", "📚 قوانین": "rules", "🧾 Audit": "audit", "⚙️ ماژول‌ها": "modules",
    }

    @bot.on_message()
    async def handle(bot, event):
        if is_duplicate_update(event):
            return
        user_id = await resolve_user(bot, event)
        if not user_id:
            return
        text = update_text(event)
        if text in {"/start", "منو", "menu", "↩️ بازگشت"}:
            _STATES.pop(user_id, None)
            await reply(event, "👑 مدیریت شبکه", keypad=owner_keyboard()); return
        if text in mapping:
            await handle_action(event, mapping[text]); return
        if user_id in _STATES:
            async with SessionFactory() as db:
                roles = RoleService(db, settings)
                user = await roles.get_or_create_user(rubika_user_id=user_id)
                if not roles.has(user, UserRole.OWNER, UserRole.SUPERVISOR):
                    await db.commit(); _STATES.pop(user_id, None); await reply(event, "⛔ دسترسی ندارید."); return
                state = _STATES[user_id]
                parts = [x.strip() for x in text.split("|")]
                try:
                    if state == "list":
                        if len(parts) != 3 or not parts[0] or not parts[1]: raise ValueError("فرمت: کد | نام لیست | حداقل کانال")
                        code, name, min_channels = parts[0].lstrip("#"), parts[1], int(parts[2])
                        if min_channels < 1: raise ValueError("حداقل کانال باید مثبت باشد")
                        if await db.scalar(select(ListNetwork).where(ListNetwork.code == code)): raise ValueError("این کد لیست قبلاً استفاده شده است")
                        db.add(ListNetwork(code=code, name=name, min_channels=min_channels, active=True)); await db.commit(); _STATES.pop(user_id, None)
                        await reply(event, f"✅ لیست {code} ساخته شد.\nحداقل کانال: {min_channels}", keypad=owner_keyboard()); return
                    if state == "price":
                        if len(parts) != 5: raise ValueError("فرمت: کد لیست | عنوان | حداقل کانال | قیمت هر کانال | ساعت")
                        code, title = parts[0].lstrip("#"), parts[1]
                        min_channels, price_per_channel, retention_hours = map(int, parts[2:5])
                        network = await db.scalar(select(ListNetwork).where(ListNetwork.code == code, ListNetwork.active.is_(True)))
                        if network is None: raise ValueError("لیست فعال پیدا نشد")
                        if min_channels < 1 or price_per_channel < 0 or retention_hours < 1: raise ValueError("مقادیر تعرفه نامعتبر است")
                        db.add(PriceRule(list_id=network.id, title=title, min_channels=min_channels, price_per_channel=price_per_channel, retention_hours=retention_hours, active=True))
                        await db.commit(); _STATES.pop(user_id, None); await reply(event, "✅ تعرفه ثبت شد.", keypad=owner_keyboard()); return
                except (ValueError, TypeError) as exc:
                    await db.rollback(); await reply(event, f"❌ {exc}"); return
        async with SessionFactory() as db:
            roles = RoleService(db, settings)
            user = await roles.get_or_create_user(rubika_user_id=user_id)
            allowed = roles.has(user, UserRole.OWNER, UserRole.SUPERVISOR)
            await db.commit()
        if not allowed:
            await reply(event, "⛔ دسترسی این ربات فقط برای مالک و ناظر شبکه است.")

    return bot
