from .admin_bot import build_admin_bot as _build_admin_bot
from .owner_localized import build_owner_bot as _build_owner_bot
from .owner_inline import handle as handle_owner_inline_action
from .user_bot import build_user_bot
from .common import button_id, reply, resolve_user, update_type
from ..core.db import SessionFactory
from ..core.roles import RoleService
from ..core.models import UserRole


class _CallbackProxy:
    def __init__(self, event, callback_id: str):
        self._event = event
        self.button_id = callback_id
        self.callback_button_id = callback_id

    def __getattr__(self, name):
        return getattr(self._event, name)


def _hide_unsupported_worker_control() -> None:
    """Remove controls that have no executable runtime contract."""
    from . import owner_localized

    original = owner_localized._clean_keyboard

    def clean(value):
        value = original(value)
        if isinstance(value, dict) and isinstance(value.get("rows"), list):
            rows = []
            for row in value["rows"]:
                if not isinstance(row, dict) or not isinstance(row.get("buttons"), list):
                    rows.append(row)
                    continue
                buttons = [b for b in row["buttons"] if not (isinstance(b, dict) and b.get("id") == "emergency:workers")]
                if buttons:
                    row = dict(row)
                    row["buttons"] = buttons
                    rows.append(row)
            value = dict(value)
            value["rows"] = rows
        return value

    owner_localized._clean_keyboard = clean


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
    _hide_unsupported_worker_control()
    bot = await _build_owner_bot(settings)
    from .owner_localized import _settings_option

    registry = getattr(bot, "_registry", None)
    handlers = getattr(registry, "_handlers", None)
    if isinstance(handlers, dict):
        for key, entries in list(handlers.items()):
            patched = []
            changed = False
            for constraints, original in entries:
                if getattr(original, "__name__", "") != "on_callback":
                    patched.append((constraints, original))
                    continue

                async def owner_callback(bot_instance, event, _original=original):
                    value = button_id(event)
                    parts = value.split(":") if value else []
                    if len(parts) == 3 and parts[0] == "settings":
                        await _settings_option(event, bot_instance, settings, parts[1], parts[2])
                        return
                    if await handle_owner_inline_action(event, value):
                        return
                    if value == "back":
                        await _original(bot_instance, _CallbackProxy(event, "dashboard"))
                        return
                    if len(parts) == 3 and parts[0] == "flow" and parts[1] == "back":
                        await _original(bot_instance, _CallbackProxy(event, parts[2]))
                        return
                    await _original(bot_instance, event)

                patched.append((constraints, owner_callback))
                changed = True
            if changed:
                handlers[key] = patched
                break

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
        from .owner_localized import localized_owner_keyboard
        await reply(event, "👑 مرکز فرماندهی اوپکس", keypad=localized_owner_keyboard())

    return bot


__all__ = ["build_admin_bot", "build_owner_bot", "build_user_bot"]
