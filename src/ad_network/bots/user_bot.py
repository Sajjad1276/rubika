import re

from fast_rub import Client, Conversation
from fast_rub.core.forms import DataForm, Number, Text
from sqlalchemy import select

from ..core.commerce import CommerceService
from ..core.config import Settings
from ..core.db import SessionFactory
from ..core.models import Channel, ListNetwork, RegistrationSource
from ..core.payments import prepare_payment
from ..core.roles import RoleService
from ..core.services import RegistrationService
from .common import button_id, inline_keyboard, quick_keyboard, reply, update_text, update_user_id

CHANNEL_RE = re.compile(r"(?:https?://)?(?:rubika\.ir/)?(@?[A-Za-z0-9_]+)$")


def main_keyboard():
    return quick_keyboard(
        (("register", "📺 ثبت کانال"), ("status", "📊 وضعیت کانال")),
        (("ad", "📢 درخواست تبلیغ"), ("prices", "💰 تعرفه‌ها")),
        (("support", "🆘 پشتیبانی"),),
    )


async def send_main(message):
    await reply(message, "📣 شبکه تبلیغات\n\nاز منوی زیر انتخاب کنید:", keypad=main_keyboard())


class RegisterForm(DataForm):
    channel = Text("🔗 لینک یا شناسه عمومی کانال را ارسال کنید.\nمثال: @mychannel", min_len=2, max_len=255,
                   validator=lambda value: bool(CHANNEL_RE.fullmatch(value.strip())),
                   invalid_answer="❌ فرمت کانال معتبر نیست. نمونه: @mychannel")
    list_code = Text("📚 کد لیست تبلیغ را وارد کنید.\nمثال: #001 یا 001", min_len=1, max_len=32)
    confirm = Text("✅ برای ثبت درخواست عبارت «تأیید» را ارسال کنید.", valid_inputs=["تأیید", "تایید", "yes", "1"],
                   invalid_answer="❌ فقط «تأیید» را ارسال کنید.")


class AdForm(DataForm):
    list_code = Text("📚 کد لیست تبلیغ را وارد کنید.\nمثال: #001 یا 001", min_len=1, max_len=32)
    title = Text("📝 عنوان تبلیغ را ارسال کنید.", min_len=1, max_len=255)
    content_ref = Text("📎 شناسه پیام تبلیغ در کانال مرجع را ارسال کنید.", min_len=1, max_len=255)
    channel_count = Number("🔢 تعداد کانال هدف را وارد کنید.", min=1, max=100000)
    retention_hours = Number("⏱ مدت ماندگاری را به ساعت وارد کنید.", min=1, max=720)


class StatusForm(DataForm):
    channel = Text("📊 شناسه یا لینک کانال خود را ارسال کنید.", min_len=2, max_len=255)


class SupportForm(DataForm):
    message = Text("🆘 پیام پشتیبانی خود را ارسال کنید.", min_len=1, max_len=4000)


async def build_user_bot(settings: Settings) -> Client:
    bot = Client("rubika_user_bot", settings.user_bot_token)
    register = Conversation(name="user_register", timeout=300)
    ad = Conversation(name="user_ad", timeout=300)
    status = Conversation(name="user_status", timeout=120)
    support = Conversation(name="user_support", timeout=180)

    @register.entry_form(RegisterForm, commands=["register"])
    async def register_done(message, data):
        user_id = update_user_id(message)
        if not user_id: return Conversation.END
        async with SessionFactory() as db:
            user = await RoleService(db, settings).get_or_create_user(rubika_user_id=user_id)
            channel_ref = data["channel"].strip()
            raw_code = data["list_code"].strip().lstrip("#")
            network_list = await db.scalar(select(ListNetwork).where(ListNetwork.code == raw_code))
            if network_list is None:
                await db.rollback(); await reply(message, "❌ کد لیست پیدا نشد."); return Conversation.END
            request = await RegistrationService(db).start(rubika_guid=channel_ref, applicant=user, source=RegistrationSource.SELF, list_id=network_list.id)
            await RegistrationService(db).submit_for_verification(request)
            await db.commit()
            await reply(message, f"✅ درخواست ثبت شد.\nکد پیگیری: {request.id[:8]}", keypad=main_keyboard())
        return Conversation.END

    @ad.entry_form(AdForm, commands=["ad"])
    async def ad_done(message, data):
        user_id = update_user_id(message)
        if not user_id: return Conversation.END
        async with SessionFactory() as db:
            user = await RoleService(db, settings).get_or_create_user(rubika_user_id=user_id)
            raw_code = data["list_code"].strip().lstrip("#")
            network_list = await db.scalar(select(ListNetwork).where(ListNetwork.code == raw_code))
            if network_list is None:
                await db.rollback(); await reply(message, "❌ کد لیست پیدا نشد."); return Conversation.END
            try:
                service = CommerceService(db)
                unit, total = await service.quote(list_id=network_list.id, channel_count=int(data["channel_count"]), retention_hours=int(data["retention_hours"]))
                order = await service.create_order(advertiser=user, title=data["title"], content_ref=data["content_ref"], list_id=network_list.id,
                                                    channel_count=int(data["channel_count"]), retention_hours=int(data["retention_hours"]))
                payment = await prepare_payment(db, order)
            except ValueError as exc:
                await db.rollback(); await reply(message, f"⛔ سفارش ایجاد نشد: {exc}"); return Conversation.END
            await db.commit()
            await reply(message, "💳 سفارش آماده پرداخت شد\n\n"
                         f"لیست: {network_list.code} | تعداد: {order.channel_count}\n"
                         f"مدت: {order.retention_hours} ساعت\n"
                         f"قیمت هر کانال: {unit:,}\nمبلغ کل: {total:,}\n"
                         f"شناسه سفارش: {order.id[:8]}\nشناسه پرداخت: {payment.reference}\n\n"
                         "پرداخت پس از بررسی ادمین تأیید می‌شود.", keypad=main_keyboard())
        return Conversation.END

    @status.entry_form(StatusForm, commands=["status"])
    async def status_done(message, data):
        async with SessionFactory() as db:
            channel = await db.scalar(select(Channel).where(Channel.rubika_guid == data["channel"].strip().lstrip("@")))
            await db.commit()
            await reply(message, f"📊 وضعیت: {channel.status.value}\nکد لیست: {channel.list_code or '-'}" if channel else "❌ کانال پیدا نشد.", keypad=main_keyboard())
        return Conversation.END

    @support.entry_form(SupportForm, commands=["support"])
    async def support_done(message, data):
        await reply(message, "✅ درخواست پشتیبانی ثبت شد.", keypad=main_keyboard())
        return Conversation.END

    for conversation in (register, ad, status, support): bot.add_conversation(conversation)

    @bot.on_button()
    async def on_button(message):
        action = button_id(message)
        prompts = {"register": "/register", "ad": "/ad", "status": "/status", "support": "/support"}
        if action == "home": await send_main(message)
        elif action in prompts: await reply(message, f"برای شروع: {prompts[action]}")
        elif action == "prices": await reply(message, "💰 تعرفه بر اساس لیست، تعداد کانال و مدت ماندگاری در /ad محاسبه می‌شود.")

    @bot.on_message()
    async def handle(message):
        text = update_text(message)
        if text in {"/start", "شروع", "منو", "menu"}: await send_main(message)
        elif text == "📺 ثبت کانال": await reply(message, "برای شروع: /register")
        elif text == "📢 درخواست تبلیغ": await reply(message, "برای شروع: /ad")
        elif text == "📊 وضعیت کانال": await reply(message, "برای شروع: /status")
        elif text == "🆘 پشتیبانی": await reply(message, "برای شروع: /support")
        elif text == "💰 تعرفه‌ها": await reply(message, "💰 تعرفه بر اساس لیست، تعداد کانال و مدت ماندگاری در /ad محاسبه می‌شود.", keypad=main_keyboard())

    return bot
