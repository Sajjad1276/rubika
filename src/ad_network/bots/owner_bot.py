import json

from sqlalchemy import func, select

from ..core.commerce import AdOrder, Payment, PriceRule
from ..core.config import Settings
from ..core.db import SessionFactory
from ..core.models import AuditLog, Channel, ChannelStatus, ListNetwork, User, UserRole
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


def _normalize_username(value: str) -> str:
    return value.strip().lstrip("@").lower()


def _role_values(user: User) -> list[str]:
    try:
        value = json.loads(user.roles_json or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(item) for item in value] if isinstance(value, list) else []


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
                await db.rollback()
                await reply(event, "⛔ دسترسی ندارید.")
                return
            if action in {"home", "back"}:
                _STATES.pop(user_id, None)
                await db.commit()
                await reply(event, "👑 مدیریت شبکه", keypad=owner_keyboard())
                return
            if action == "overview":
                lists = (await db.scalars(select(ListNetwork).where(ListNetwork.active.is_(True)))).all()
                channels = await db.scalar(select(func.count(Channel.id)).where(Channel.status == ChannelStatus.ACTIVE))
                admins = 0
                supervisors = 0
                for item in (await db.scalars(select(User))).all():
                    role_set = set(_role_values(item))
                    admins += UserRole.ADMIN.value in role_set
                    supervisors += UserRole.SUPERVISOR.value in role_set
                await db.commit()
                await reply(
                    event,
                    f"📊 شبکه\n\nلیست فعال: {len(lists)}\nکانال فعال: {int(channels or 0)}\nادمین ثبت‌شده: {admins}\nناظر: {supervisors}",
                    keypad=owner_keyboard(),
                )
                return
            if action == "lists":
                lists = (await db.scalars(select(ListNetwork).order_by(ListNetwork.code))).all()
                lines = []
                for item in lists:
                    count = await db.scalar(select(func.count(Channel.id)).where(
                        Channel.list_id == item.id,
                        Channel.status == ChannelStatus.ACTIVE,
                    ))
                    state = "فعال" if item.active else "غیرفعال"
                    lines.append(f"{item.code} | {item.name} | {int(count or 0)} کانال | {state}")
                await db.commit()
                await reply(
                    event,
                    "🗂 لیست‌ها\n\n" + ("\n".join(lines) or "لیستی ثبت نشده است."),
                    inline_keypad=inline_keyboard((("list:add", "➕ ساخت لیست"),)),
                )
                return
            if action == "list:add":
                _STATES[user_id] = "list"
                await db.commit()
                await reply(event, "➕ ساخت لیست\nفرمت: کد | نام لیست | حداقل کانال\nمثال: 001 | سحابی | 20")
                return
            if action == "pricing":
                rules_rows = (await db.scalars(select(PriceRule).where(
                    PriceRule.active.is_(True)
                ).order_by(PriceRule.list_id, PriceRule.min_channels))).all()
                lines = [
                    f"{r.title} | لیست {r.list_id or 'عمومی'} | حداقل {r.min_channels} | هر کانال {r.price_per_channel:,} | {r.retention_hours}h"
                    for r in rules_rows
                ]
                await db.commit()
                await reply(
                    event,
                    "💰 تعرفه‌های فعال\n\n" + ("\n".join(lines) or "هنوز تعرفه‌ای ثبت نشده است."),
                    inline_keypad=inline_keyboard((("price:add", "➕ ثبت تعرفه"),)),
                )
                return
            if action == "price:add":
                _STATES[user_id] = "price"
                await db.commit()
                await reply(event, "➕ ثبت تعرفه\nفرمت: کد لیست | عنوان | حداقل کانال | قیمت هر کانال | ساعت ماندگاری\nمثال: 001 | پایه | 20 | 50000 | 6")
                return
            if action == "people":
                rows = []
                for item in (await db.scalars(select(User).order_by(User.username))).all():
                    role_set = set(_role_values(item))
                    privileged = [role for role in (UserRole.OWNER.value, UserRole.ADMIN.value, UserRole.SUPERVISOR.value) if role in role_set]
                    if privileged:
                        rows.append(f"@{item.username or '-'} | {', '.join(privileged)}")
                await db.commit()
                await reply(
                    event,
                    "👥 نقش‌های شبکه\n\n" + ("\n".join(rows) or "نقش مدیریتی ثبت نشده است."),
                    inline_keypad=inline_keyboard(
                        (("supervisor:add", "➕ افزودن ناظر"), ("supervisor:remove", "➖ حذف ناظر")),
                    ),
                )
                return
            if action in {"supervisor:add", "supervisor:remove"}:
                _STATES[user_id] = "supervisor_add" if action.endswith("add") else "supervisor_remove"
                await db.commit()
                await reply(event, "👤 نام کاربری روبیکا را با یا بدون @ ارسال کنید.")
                return
            if action == "orders":
                orders = list((await db.scalars(select(AdOrder).order_by(AdOrder.created_at.desc()).limit(20))).all())
                lines = [
                    f"{order.id[:8]} | {order.status.value if hasattr(order.status, 'value') else order.status} | {order.total_price:,} | {order.channel_count} کانال"
                    for order in orders
                ]
                await db.commit()
                await reply(event, "📢 سفارش‌های اخیر\n\n" + ("\n".join(lines) or "سفارشی وجود ندارد."), keypad=owner_keyboard())
                return
            if action == "rules":
                await db.commit()
                await reply(
                    event,
                    "📚 قوانین عملیاتی\n\n• کانال بدون احراز دسترسی فعال نمی‌شود.\n• حذف تبلیغ قبل از پایان ماندگاری تخلف است.\n• پرداخت فقط توسط ادمین مجاز تأیید می‌شود.\n• هر لیست فقط از اکانت عملیاتی فعال خودش استفاده می‌کند.",
                    keypad=owner_keyboard(),
                )
                return
            if action == "audit":
                logs = list((await db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(20))).all())
                lines = [f"{row.action} | {row.entity_type}:{row.entity_id[:8]} | actor={row.actor_id[:8] if row.actor_id else '-'}" for row in logs]
                await db.commit()
                await reply(event, "🧾 آخرین عملیات حساس\n\n" + ("\n".join(lines) or "لاگ عملیاتی وجود ندارد."), keypad=owner_keyboard())
                return
            if action == "modules":
                list_count = await db.scalar(select(func.count(ListNetwork.id)).where(ListNetwork.active.is_(True)))
                channel_count = await db.scalar(select(func.count(Channel.id)).where(Channel.status == ChannelStatus.ACTIVE))
                payment_count = await db.scalar(select(func.count(Payment.id)))
                await db.commit()
                await reply(
                    event,
                    f"⚙️ سلامت ماژول‌ها\n\nBotها: آماده\nDatabase: آماده\nMAXRubika: آماده\nلیست فعال: {int(list_count or 0)}\nکانال فعال: {int(channel_count or 0)}\nپرداخت ثبت‌شده: {int(payment_count or 0)}",
                    keypad=owner_keyboard(),
                )
                return

            await db.commit()

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
            await reply(event, "👑 مدیریت شبکه", keypad=owner_keyboard())
            return
        if text in mapping:
            await handle_action(event, mapping[text])
            return
        if user_id in _STATES:
            async with SessionFactory() as db:
                roles = RoleService(db, settings)
                user = await roles.get_or_create_user(rubika_user_id=user_id)
                if not roles.has(user, UserRole.OWNER, UserRole.SUPERVISOR):
                    await db.rollback()
                    _STATES.pop(user_id, None)
                    await reply(event, "⛔ دسترسی ندارید.")
                    return
                state = _STATES[user_id]
                parts = [x.strip() for x in text.split("|")]
                try:
                    if state == "list":
                        if len(parts) != 3 or not parts[0] or not parts[1]:
                            raise ValueError("فرمت: کد | نام لیست | حداقل کانال")
                        code, name, min_channels = parts[0].lstrip("#"), parts[1], int(parts[2])
                        if not 1 <= min_channels <= 1_000_000:
                            raise ValueError("حداقل کانال باید بین 1 تا 1000000 باشد")
                        if not code or len(code) > 32:
                            raise ValueError("کد لیست نامعتبر است")
                        if await db.scalar(select(ListNetwork).where(ListNetwork.code == code)):
                            raise ValueError("این کد لیست قبلاً استفاده شده است")
                        db.add(ListNetwork(code=code, name=name, min_channels=min_channels, active=True))
                        await db.commit()
                        _STATES.pop(user_id, None)
                        await reply(event, f"✅ لیست {code} ساخته شد.\nحداقل کانال: {min_channels}", keypad=owner_keyboard())
                        return
                    if state == "price":
                        if len(parts) != 5:
                            raise ValueError("فرمت: کد لیست | عنوان | حداقل کانال | قیمت هر کانال | ساعت")
                        code, title = parts[0].lstrip("#"), parts[1]
                        min_channels, price_per_channel, retention_hours = map(int, parts[2:5])
                        network = await db.scalar(select(ListNetwork).where(ListNetwork.code == code, ListNetwork.active.is_(True)))
                        if network is None:
                            raise ValueError("لیست فعال پیدا نشد")
                        if not title or min_channels < 1 or price_per_channel < 0 or retention_hours < 1:
                            raise ValueError("مقادیر تعرفه نامعتبر است")
                        db.add(PriceRule(
                            list_id=network.id,
                            title=title,
                            min_channels=min_channels,
                            price_per_channel=price_per_channel,
                            retention_hours=retention_hours,
                            active=True,
                        ))
                        await db.commit()
                        _STATES.pop(user_id, None)
                        await reply(event, "✅ تعرفه ثبت شد.", keypad=owner_keyboard())
                        return
                    if state == "supervisor_add":
                        username = _normalize_username(text)
                        if not username:
                            raise ValueError("نام کاربری خالی است")
                        info = await bot.get_user_info(username)
                        data = getattr(info, "to_dict", lambda: info)()
                        user_data = data.get("user", {}) if isinstance(data, dict) else {}
                        rubika_id = user_data.get("user_guid") or user_data.get("guid")
                        if not rubika_id:
                            raise ValueError("کاربر روبیکا پیدا نشد")
                        target = await roles.get_or_create_user(
                            rubika_user_id=str(rubika_id),
                            username=username,
                            display_name=user_data.get("first_name"),
                        )
                        role_set = set(roles.roles(target))
                        role_set.add(UserRole.SUPERVISOR.value)
                        target.roles_json = json.dumps(sorted(role_set), ensure_ascii=False)
                        await db.commit()
                        _STATES.pop(user_id, None)
                        await reply(event, f"✅ @{username} به‌عنوان ناظر ثبت شد.", keypad=owner_keyboard())
                        return
                    if state == "supervisor_remove":
                        username = _normalize_username(text)
                        target = await db.scalar(select(User).where(func.lower(User.username) == username))
                        if target is None:
                            raise ValueError("کاربر مدیریتی پیدا نشد")
                        role_set = set(roles.roles(target))
                        role_set.discard(UserRole.SUPERVISOR.value)
                        target.roles_json = json.dumps(sorted(role_set or {UserRole.USER.value}), ensure_ascii=False)
                        await db.commit()
                        _STATES.pop(user_id, None)
                        await reply(event, f"✅ نقش ناظر از @{username} حذف شد.", keypad=owner_keyboard())
                        return
                except (ValueError, TypeError) as exc:
                    await db.rollback()
                    await reply(event, f"❌ {exc}")
                    return
        async with SessionFactory() as db:
            roles = RoleService(db, settings)
            user = await roles.get_or_create_user(rubika_user_id=user_id)
            allowed = roles.has(user, UserRole.OWNER, UserRole.SUPERVISOR)
        if not allowed:
            await reply(event, "⛔ دسترسی این ربات فقط برای مالک و ناظر شبکه است.")

    return bot
