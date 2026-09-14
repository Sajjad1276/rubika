import re

from sqlalchemy import select

from ..core.commerce import CommerceService
from ..core.config import Settings
from ..core.db import SessionFactory
from ..core.models import Channel, ListNetwork, RegistrationSource
from ..core.payments import prepare_payment
from ..core.roles import RoleService
from ..core.services import RegistrationService
from .common import is_duplicate_update, quick_keyboard, reply, resolve_user, update_text

CHANNEL_RE = re.compile(r"(?:https?://)?(?:rubika\.ir/)?(@?[A-Za-z0-9_]+)$")
_STATES: dict[str, dict[str, object]] = {}


def main_keyboard():
    return quick_keyboard(
        (("register", "📺 ثبت کانال"), ("status", "📊 وضعیت کانال")),
        (("ad", "📢 درخواست تبلیغ"), ("prices", "💰 تعرفه‌ها")),
        (("support", "🆘 پشتیبانی"),),
    )


async def send_main(event):
    await reply(event, "📣 شبکه تبلیغات\n\nاز منوی زیر انتخاب کنید:", keypad=main_keyboard())


def _start_state(user_id: str, state: str) -> None:
    _STATES[user_id] = {"state": state, "data": {}}


def _clear_state(user_id: str) -> None:
    _STATES.pop(user_id, None)


async def _finish_register(event, settings: Settings, user_id: str, data: dict[str, object]) -> None:
    async with SessionFactory() as db:
        user = await RoleService(db, settings).get_or_create_user(rubika_user_id=user_id)
        channel_ref = str(data["channel"]).strip()
        raw_code = str(data["list_code"]).strip().lstrip("#")
        network_list = await db.scalar(select(ListNetwork).where(ListNetwork.code == raw_code))
        if network_list is None:
            await db.rollback()
            await reply(event, "❌ کد لیست پیدا نشد.", keypad=main_keyboard())
            return
        request = await RegistrationService(db).start(
            rubika_guid=channel_ref,
            applicant=user,
            source=RegistrationSource.SELF,
            list_id=network_list.id,
        )
        await RegistrationService(db).submit_for_verification(request)
        await db.commit()
        await reply(event, f"✅ درخواست ثبت شد.\nکد پیگیری: {request.id[:8]}", keypad=main_keyboard())


async def _finish_ad(event, settings: Settings, user_id: str, data: dict[str, object]) -> None:
    async with SessionFactory() as db:
        user = await RoleService(db, settings).get_or_create_user(rubika_user_id=user_id)
        raw_code = str(data["list_code"]).strip().lstrip("#")
        network_list = await db.scalar(select(ListNetwork).where(ListNetwork.code == raw_code))
        if network_list is None:
            await db.rollback()
            await reply(event, "❌ کد لیست پیدا نشد.", keypad=main_keyboard())
            return
        try:
            service = CommerceService(db)
            unit, total = await service.quote(
                list_id=network_list.id,
                channel_count=int(data["channel_count"]),
                retention_hours=int(data["retention_hours"]),
            )
            order = await service.create_order(
                advertiser=user,
                title=str(data["title"]),
                content_ref=str(data["content_ref"]),
                list_id=network_list.id,
                channel_count=int(data["channel_count"]),
                retention_hours=int(data["retention_hours"]),
            )
            payment = await prepare_payment(db, order)
        except ValueError as exc:
            await db.rollback()
            await reply(event, f"⛔ سفارش ایجاد نشد: {exc}", keypad=main_keyboard())
            return
        await db.commit()
        await reply(
            event,
            "💳 سفارش آماده پرداخت شد\n\n"
            f"لیست: {network_list.code} | تعداد: {order.channel_count}\n"
            f"مدت: {order.retention_hours} ساعت\n"
            f"قیمت هر کانال: {unit:,}\nمبلغ کل: {total:,}\n"
            f"شناسه سفارش: {order.id[:8]}\nشناسه پرداخت: {payment.reference}\n\n"
            "پرداخت پس از بررسی ادمین تأیید می‌شود.",
            keypad=main_keyboard(),
        )


async def _handle_state(event, settings: Settings, user_id: str, text: str) -> bool:
    state = _STATES.get(user_id)
    if not state:
        return False
    if text in {"↩️ بازگشت", "/start", "لغو", "cancel"}:
        _clear_state(user_id)
        await send_main(event)
        return True

    name = str(state["state"])
    data = state["data"]
    if not isinstance(data, dict):
        data = {}
        state["data"] = data

    if name == "register_channel":
        if not CHANNEL_RE.fullmatch(text):
            await reply(event, "❌ فرمت کانال معتبر نیست. نمونه: @mychannel")
            return True
        data["channel"] = text
        state["state"] = "register_list"
        await reply(event, "📚 کد لیست تبلیغ را وارد کنید.\nمثال: #001 یا 001")
        return True
    if name == "register_list":
        data["list_code"] = text
        state["state"] = "register_confirm"
        await reply(event, "✅ برای ثبت درخواست عبارت «تأیید» را ارسال کنید.")
        return True
    if name == "register_confirm":
        if text.lower() not in {"تأیید", "تایید", "yes", "1"}:
            await reply(event, "❌ فقط «تأیید» را ارسال کنید.")
            return True
        _clear_state(user_id)
        await _finish_register(event, settings, user_id, data)
        return True

    if name == "ad_list":
        data["list_code"] = text
        state["state"] = "ad_title"
        await reply(event, "📝 عنوان تبلیغ را ارسال کنید.")
        return True
    if name == "ad_title":
        data["title"] = text
        state["state"] = "ad_content"
        await reply(event, "📎 شناسه پیام تبلیغ در کانال مرجع را ارسال کنید.")
        return True
    if name == "ad_content":
        data["content_ref"] = text
        state["state"] = "ad_count"
        await reply(event, "🔢 تعداد کانال هدف را وارد کنید.")
        return True
    if name == "ad_count":
        try:
            value = int(text)
            if not 1 <= value <= 100000:
                raise ValueError
        except ValueError:
            await reply(event, "❌ تعداد باید عددی بین 1 تا 100000 باشد.")
            return True
        data["channel_count"] = value
        state["state"] = "ad_retention"
        await reply(event, "⏱ مدت ماندگاری را به ساعت وارد کنید.")
        return True
    if name == "ad_retention":
        try:
            value = int(text)
            if not 1 <= value <= 720:
                raise ValueError
        except ValueError:
            await reply(event, "❌ مدت باید عددی بین 1 تا 720 ساعت باشد.")
            return True
        data["retention_hours"] = value
        _clear_state(user_id)
        await _finish_ad(event, settings, user_id, data)
        return True

    if name == "status":
        _clear_state(user_id)
        async with SessionFactory() as db:
            channel = await db.scalar(select(Channel).where(Channel.rubika_guid == text.lstrip("@")))
            await db.commit()
        await reply(
            event,
            f"📊 وضعیت: {channel.status.value}\nکد لیست: {channel.list_code or '-'}" if channel else "❌ کانال پیدا نشد.",
            keypad=main_keyboard(),
        )
        return True

    if name == "support":
        _clear_state(user_id)
        await reply(event, "✅ درخواست پشتیبانی ثبت شد.", keypad=main_keyboard())
        return True
    return False


async def build_user_bot(settings: Settings):
    from maxrubika import Bot

    bot = Bot(settings.user_bot_token, timeout=30, max_retries=5)

    @bot.on_callback()
    async def callbacks(bot, event):
        if is_duplicate_update(event):
            return
        if getattr(event, "button_id", None) in {"home", "back"}:
            user_id = await resolve_user(bot, event)
            if user_id:
                _clear_state(user_id)
            await send_main(event)

    @bot.on_message()
    async def handle(bot, event):
        if is_duplicate_update(event):
            return
        user_id = await resolve_user(bot, event)
        if not user_id:
            return
        text = update_text(event)
        if text in {"/start", "شروع", "منو", "menu", "↩️ بازگشت"}:
            _clear_state(user_id)
            await send_main(event)
            return
        if await _handle_state(event, settings, user_id, text):
            return
        if text == "📺 ثبت کانال":
            _start_state(user_id, "register_channel")
            await reply(event, "🔗 لینک یا شناسه عمومی کانال را ارسال کنید.\nمثال: @mychannel")
        elif text == "📊 وضعیت کانال":
            _start_state(user_id, "status")
            await reply(event, "📊 شناسه یا لینک کانال خود را ارسال کنید.")
        elif text == "📢 درخواست تبلیغ":
            _start_state(user_id, "ad_list")
            await reply(event, "📚 کد لیست تبلیغ را وارد کنید.\nمثال: #001 یا 001")
        elif text == "💰 تعرفه‌ها":
            await reply(event, "💰 تعرفه بر اساس لیست، تعداد کانال و مدت ماندگاری در درخواست تبلیغ محاسبه می‌شود.", keypad=main_keyboard())
        elif text == "🆘 پشتیبانی":
            _start_state(user_id, "support")
            await reply(event, "🆘 پیام پشتیبانی خود را ارسال کنید.")

    return bot
