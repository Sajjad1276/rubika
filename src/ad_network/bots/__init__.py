from .admin_bot import build_admin_bot as _build_admin_bot
from .owner_bot import build_owner_bot as _build_owner_bot
from .user_bot import build_user_bot
from .common import reply, resolve_user, update_type
from ..core.db import SessionFactory
from ..core.roles import RoleService
from ..core.models import UserRole


async def build_admin_bot(settings, account_resolver=None, account_runtime=None):
    bot = await _build_admin_bot(settings, account_resolver, account_runtime)

    @bot.on_message()
    async def admin_started(bot, event):
        if update_type(event) != "StartedBot":
            return
        user_id = await resolve_user(bot, event)
        if not user_id:
            return
        async with SessionFactory() as db:
            roles = RoleService(db, settings)
            user = await roles.get_or_create_user(rubika_user_id=user_id)
            if not roles.has(user, UserRole.ADMIN, UserRole.SUPERVISOR, UserRole.OWNER):
                await db.rollback()
                await reply(event, "⛔ دسترسی ندارید.")
                return
            await db.commit()
        from .admin_bot import admin_keyboard
        await reply(event, "🛠 داشبورد ادمین", keypad=admin_keyboard())

    return bot


async def build_owner_bot(settings):
    bot = await _build_owner_bot(settings)

    @bot.on_message()
    async def owner_started(bot, event):
        if update_type(event) != "StartedBot":
            return
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
            await db.commit()
        from .owner_bot import owner_keyboard
        await reply(event, "👑 OPEX CONTROL CENTER", keypad=owner_keyboard())

    return bot


__all__ = ["build_admin_bot", "build_owner_bot", "build_user_bot"]
