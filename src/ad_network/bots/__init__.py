from .admin_bot import build_admin_bot as _build_admin_bot
from .owner_bot import build_owner_bot as _build_owner_bot
from .user_bot import build_user_bot
from .common import reply, resolve_user, update_type


async def build_admin_bot(settings, account_resolver=None, account_runtime=None):
    bot = await _build_admin_bot(settings, account_resolver, account_runtime)

    @bot.on_message()
    async def admin_started(bot, event):
        if update_type(event) != "StartedBot":
            return
        user_id = await resolve_user(bot, event)
        if user_id:
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
        if user_id:
            from .owner_bot import owner_keyboard
            await reply(event, "👑 مدیریت شبکه", keypad=owner_keyboard())

    return bot


__all__ = ["build_admin_bot", "build_owner_bot", "build_user_bot"]
