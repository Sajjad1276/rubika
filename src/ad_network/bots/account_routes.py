from sqlalchemy import select

from ..core.account_management import AccountManagementService
from ..core.db import SessionFactory
from ..core.list_accounts import ListAccountService
from ..core.models import ListAccount, ListNetwork
from .common import inline_keyboard, reply, resolve_user, update_text

_STATES: dict[str, tuple[str, str | None]] = {}


def account_keyboard(accounts: list[ListAccount], lists: dict[str, ListNetwork]):
    rows = []
    for account in accounts:
        network = lists.get(account.list_id)
        rows.append((f"account:{account.id}", f"🟢 {network.code if network else account.list_id[:8]} | {account.rubika_user_id}"))
    rows.append(("account:add", "➕ اتصال اکانت جدید"))
    return inline_keyboard(*[tuple(rows[i:i + 2]) for i in range(0, len(rows), 2)])


async def show_accounts(event):
    async with SessionFactory() as db:
        accounts = await ListAccountService(db).list_active()
        lists = {}
        if accounts:
            lists = {
                x.id: x
                for x in (
                    await db.scalars(
                        select(ListNetwork).where(ListNetwork.id.in_({a.list_id for a in accounts}))
                    )
                ).all()
            }
        await db.commit()
    await reply(event, "👤 اکانت‌های عملیاتی لیست:", inline_keypad=account_keyboard(accounts, lists))


async def account_button(event, action: str, runtime, bot) -> bool:
    user_id = await resolve_user(bot, event)
    if not user_id:
        return False
    if action == "accounts":
        await show_accounts(event)
        return True
    if action == "account:add":
        _STATES[user_id] = ("add", None)
        await reply(event, "➕ اتصال اکانت جدید\nکد لیست | شناسه کاربر روبیکا | مسیر Session\nSession باید روی سرور یا Volume موجود باشد.")
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
            await reply(event, "❌ اکانت پیدا نشد.")
            return True
        await reply(
            event,
            f"👤 {network.code if network else account.list_id}\nروبیکا: {account.rubika_user_id}\nSession: {account.session_ref or '-'}",
            inline_keypad=inline_keyboard(
                ((f"account:test:{account.id}", "🔌 تست اتصال"), (f"account:replace:{account.id}", "🔄 تعویض")),
                ((f"account:disable:{account.id}", "⛔ غیرفعال"), ("accounts", "↩️ بازگشت")),
            ),
        )
        return True
    if len(parts) != 3:
        return False
    op, account_id = parts[1], parts[2]
    async with SessionFactory() as db:
        account = await db.get(ListAccount, account_id)
        if not account:
            await db.commit()
            await reply(event, "❌ اکانت پیدا نشد.")
            return True
        if op == "test":
            await db.commit()
            try:
                await runtime.connect(account)
                await reply(event, "✅ Session با موفقیت متصل است.")
            except RuntimeError as exc:
                await reply(event, f"❌ اتصال ناموفق: {exc}")
            return True
        if op == "replace":
            _STATES[user_id] = ("replace", account.id)
            await db.commit()
            await reply(event, "🔄 مشخصات اکانت جدید را بفرست:\nشناسه کاربر روبیکا | مسیر Session")
            return True
        if op == "disable":
            try:
                await ListAccountService(db).deactivate(account.id)
                await db.commit()
                await runtime.disconnect(account.id)
                await reply(event, "⛔ اکانت غیرفعال و از Runtime خارج شد.")
            except (ValueError, RuntimeError) as exc:
                await db.rollback()
                await reply(event, f"❌ عملیات ناموفق: {exc}")
            return True
    return False


async def account_text(event, runtime, bot) -> bool:
    uid = await resolve_user(bot, event)
    if not uid:
        return False
    state = _STATES.get(uid)
    if not state:
        return False

    text = update_text(event)
    parts = [x.strip() for x in text.split("|")]
    if state[0] == "add":
        if len(parts) != 3 or not all(parts):
            await reply(event, "فرمت: کد لیست | شناسه کاربر روبیکا | مسیر Session")
            return True
        list_code, rubika_user_id, session_ref = parts
    else:
        if len(parts) != 2 or not all(parts):
            await reply(event, "فرمت: شناسه کاربر روبیکا | مسیر Session")
            return True
        rubika_user_id, session_ref = parts
        list_code = ""

    if not AccountManagementService.resolve_session_path(session_ref).is_file():
        await reply(event, "❌ فایل Session پیدا نشد.")
        return True

    async with SessionFactory() as db:
        service = AccountManagementService(db, runtime)
        try:
            if state[0] == "add":
                account = await service.attach(
                    list_code=list_code,
                    rubika_user_id=rubika_user_id,
                    session_ref=session_ref,
                )
            else:
                account = await service.replace(
                    state[1],
                    rubika_user_id=rubika_user_id,
                    session_ref=session_ref,
                )
            await db.commit()
            _STATES.pop(uid, None)
        except ValueError as exc:
            await db.rollback()
            await reply(event, f"❌ ثبت ناموفق: {exc}")
            return True

    try:
        await runtime.connect(account)
        await reply(event, "✅ اکانت ثبت و Session متصل شد.")
    except RuntimeError as exc:
        await reply(event, f"⚠️ ثبت شد ولی اتصال ناموفق بود: {exc}")
    return True
