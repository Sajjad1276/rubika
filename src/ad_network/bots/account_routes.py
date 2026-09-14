from sqlalchemy import select

from ..core.account_management import AccountManagementService
from ..core.db import SessionFactory
from ..core.list_accounts import ListAccountService
from ..core.models import ListAccount, ListNetwork
from .common import inline_keyboard, reply

_STATES: dict[str, tuple[str, str | None]] = {}


def account_keyboard(accounts: list[ListAccount], lists: dict[str, ListNetwork]):
    rows = []
    for account in accounts:
        network = lists.get(account.list_id)
        rows.append((f"account:{account.id}", f"🟢 {network.code if network else account.list_id[:8]} | {account.rubika_user_id}"))
    rows.append(("account:add", "➕ اتصال اکانت جدید"))
    rows.append(("home", "↩️ بازگشت"))
    keypad_rows = [tuple(rows[i:i + 2]) for i in range(0, len(rows), 2)]
    return inline_keyboard(*keypad_rows)


async def show_accounts(message):
    async with SessionFactory() as db:
        accounts = await ListAccountService(db).list_active()
        lists = {}
        if accounts:
            lists = {x.id: x for x in (await db.scalars(select(ListNetwork).where(ListNetwork.id.in_({a.list_id for a in accounts})))).all()}
        await db.commit()
    await reply(message, "👤 اکانت‌های عملیاتی لیست:", inline_keypad=account_keyboard(accounts, lists))


async def account_button(message, action: str, runtime) -> bool:
    if action == "accounts":
        await show_accounts(message)
        return True
    if action == "account:add":
        _STATES[_uid(message)] = ("add", None)
        await reply(message, "➕ اتصال اکانت جدید\nکد لیست | شناسه کاربر روبیکا | مسیر Session\nSession باید روی سرور یا Volume موجود باشد.")
        return True
    if not action.startswith("account:"):
        return False
    parts = action.split(":")
    if len(parts) == 2:
        account_id = parts[1]
        async with SessionFactory() as db:
            account = await db.get(ListAccount, account_id)
            network = await db.get(ListNetwork, account.list_id) if account else None
            await db.commit()
        if not account:
            await reply(message, "❌ اکانت پیدا نشد.")
            return True
        await reply(message, f"👤 {network.code if network else account.list_id}\nروبیکا: {account.rubika_user_id}\nSession: {account.session_ref or '-'}", inline_keypad=inline_keyboard(
            ((f"account:test:{account.id}", "🔌 تست اتصال"), (f"account:replace:{account.id}", "🔄 تعویض")),
            ((f"account:disable:{account.id}", "⛔ غیرفعال"), ("accounts", "↩️ بازگشت")),
        ))
        return True
    if len(parts) != 3:
        return False
    op, account_id = parts[1], parts[2]
    async with SessionFactory() as db:
        account = await db.get(ListAccount, account_id)
        if not account:
            await db.commit(); await reply(message, "❌ اکانت پیدا نشد."); return True
        if op == "test":
            await db.commit()
            try:
                await runtime.connect(account)
                await reply(message, "✅ Session با موفقیت متصل است.")
            except RuntimeError as exc:
                await reply(message, f"❌ اتصال ناموفق: {exc}")
            return True
        if op == "replace":
            _STATES[_uid(message)] = ("replace", account.id)
            await db.commit()
            await reply(message, "🔄 اکانت جدید را بفرست:\nکد لیست | شناسه کاربر روبیکا | مسیر Session")
            return True
        if op == "disable":
            try:
                await ListAccountService(db).deactivate(account.id)
                await db.commit()
                await runtime.disconnect(account.id)
                await reply(message, "⛔ اکانت غیرفعال و از Runtime خارج شد.")
            except (ValueError, RuntimeError) as exc:
                await db.rollback(); await reply(message, f"❌ عملیات ناموفق: {exc}")
            return True
    return False


def _uid(message) -> str:
    event = getattr(message, "new_message", message)
    return str(getattr(event, "author_object_guid", getattr(event, "author_guid", "")) or "")


async def account_text(message, runtime) -> bool:
    uid = _uid(message)
    state = _STATES.get(uid)
    if not state:
        return False
    parts = [x.strip() for x in str(getattr(getattr(message, "new_message", message), "text", "")).split("|")]
    if len(parts) != 3 or not all(parts):
        await reply(message, "فرمت: کد لیست | شناسه کاربر روبیکا | مسیر Session")
        return True
    list_code, rubika_user_id, session_ref = parts
    if not AccountManagementService.resolve_session_path(session_ref).exists():
        await reply(message, "❌ فایل Session پیدا نشد.")
        return True
    async with SessionFactory() as db:
        service = AccountManagementService(db, runtime)
        try:
            if state[0] == "add":
                account = await service.attach(list_code=list_code, rubika_user_id=rubika_user_id, session_ref=session_ref)
            else:
                account = await service.replace(state[1], rubika_user_id=rubika_user_id, session_ref=session_ref)
            await db.commit()
            _STATES.pop(uid, None)
        except ValueError as exc:
            await db.rollback(); await reply(message, f"❌ ثبت ناموفق: {exc}"); return True
    try:
        await runtime.connect(account)
        await reply(message, "✅ اکانت ثبت و Session متصل شد.")
    except RuntimeError as exc:
        await reply(message, f"⚠️ ثبت شد ولی اتصال ناموفق بود: {exc}")
    return True
