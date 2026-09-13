import re

from fast_rub import Client
from sqlalchemy import select

from ..core.commerce import CommerceService
from ..core.config import Settings
from ..core.db import SessionFactory
from ..core.models import ListNetwork, RegistrationSource
from ..core.roles import RoleService
from ..core.services import RegistrationService
from ..core.session import SessionState
from .common import button_id, inline_keyboard, reply, update_text, update_user_id

CHANNEL_RE = re.compile(r"(?:https?://)?(?:rubika\.ir/)?(@?[A-Za-z0-9_]+)$")


def main_keyboard():
    return inline_keyboard(
        (("register", "📺 ثبت کانال"), ("status", "📊 وضعیت کانال")),
        (("ad", "📢 درخواست تبلیغ"), ("prices", "💰 تعرفه‌ها")),
        (("support", "🆘 پشتیبانی"),),
    )


async def send_main(message):
    await reply(message, "📣 شبکه تبلیغات\n\nاز منوی زیر انتخاب کنید:", inline_keypad=main_keyboard())


async def build_user_bot(settings: Settings) -> Client:
    bot = Client(settings.user_bot_token)

    async def handle_action(message, action: str):
        user_id = update_user_id(message)
        if not user_id:
            return
        async with SessionFactory() as db:
            roles = RoleService(db, settings)
            user = await roles.get_or_create_user(rubika_user_id=user_id)
            conversation = SessionState(db, user_id, "user")
            session = await conversation.load()
            data = SessionState.data(session)

            if action == "home":
                await conversation.set("idle")
                await db.commit()
                await send_main(message)
                return

            if action == "register":
                await conversation.set("awaiting_channel", {})
                await db.commit()
                await reply(message, "🔗 لینک یا شناسه عمومی کانال را ارسال کنید.\n\nنمونه: @mychannel")
                return

            if action == "ad":
                lists = list((await db.scalars(select(ListNetwork).where(ListNetwork.active.is_(True)).order_by(ListNetwork.code))).all())
                if not lists:
                    await db.commit()
                    await reply(message, "⚠️ فعلاً لیست فعالی برای تبلیغ وجود ندارد.")
                    return
                await conversation.set("ad_list", {})
                await db.commit()
                rows = tuple((f"adlist:{item.id}", f"{item.code} | {item.name}") for item in lists)
                await reply(message, "📢 لیست تبلیغ را انتخاب کنید:", inline_keypad=inline_keyboard(rows))
                return

            if action == "status":
                await db.commit()
                await reply(message, "📊 برای مشاهده وضعیت، شناسه یا لینک کانال خود را ارسال کنید.")
                await conversation.set("awaiting_status_channel", {})
                return

            if action == "prices":
                await db.commit()
                await reply(message, "💰 تعرفه‌ها از منوی تبلیغ و بر اساس لیست هدف محاسبه می‌شوند.")
                return

            if action == "support":
                await db.commit()
                await reply(message, "🆘 پیام پشتیبانی خود را ارسال کنید. درخواست شما ثبت می‌شود.")
                await conversation.set("support_message", {})
                return

            if action.startswith("list:"):
                data["list_id"] = action.split(":", 1)[1]
                await conversation.set("awaiting_channel_confirmation", data)
                selected = await db.get(ListNetwork, data["list_id"])
                await db.commit()
                await reply(message, f"📋 {selected.name if selected else 'لیست'} انتخاب شد.\nبرای ثبت نهایی تأیید کنید.", inline_keypad=inline_keyboard((("reg:confirm", "✅ تأیید"), ("home", "↩️ انصراف"))))
                return

            if action == "reg:confirm":
                if not data.get("channel_ref") or not data.get("list_id"):
                    await conversation.set("idle")
                    await db.commit()
                    await reply(message, "❌ اطلاعات ثبت ناقص است.")
                    return
                request = await RegistrationService(db).start(
                    rubika_guid=data["channel_ref"], applicant=user,
                    source=RegistrationSource.SELF, list_id=data["list_id"],
                )
                await RegistrationService(db).submit_for_verification(request)
                await conversation.set("idle")
                await db.commit()
                await reply(message, f"✅ درخواست ثبت شد.\nکد پیگیری: {request.id[:8]}", inline_keypad=inline_keyboard((("home", "🏠 منوی اصلی"),)))
                return

            if action.startswith("adlist:"):
                list_id = action.split(":", 1)[1]
                if await db.get(ListNetwork, list_id) is None:
                    await db.commit()
                    await reply(message, "❌ لیست پیدا نشد.")
                    return
                data["list_id"] = list_id
                await conversation.set("ad_title", data)
                await db.commit()
                await reply(message, "📝 عنوان تبلیغ را ارسال کنید.")
                return

            await db.commit()

    @bot.on_button()
    async def on_button(message):
        action = button_id(message)
        if action:
            await handle_action(message, action)

    @bot.on_message()
    async def handle(message):
        user_id = update_user_id(message)
        if not user_id:
            return
        text = update_text(message)

        if text in {"/start", "شروع", "منو", "menu"}:
            await send_main(message)
            async with SessionFactory() as db:
                await SessionState(db, user_id, "user").set("idle")
                await db.commit()
            return

        async with SessionFactory() as db:
            roles = RoleService(db, settings)
            user = await roles.get_or_create_user(rubika_user_id=user_id)
            conversation = SessionState(db, user_id, "user")
            session = await conversation.load()
            data = SessionState.data(session)

            if session.state == "awaiting_channel":
                match = CHANNEL_RE.fullmatch(text)
                if not match:
                    await db.commit()
                    await reply(message, "❌ فرمت کانال معتبر نیست. نمونه: @mychannel")
                    return
                data["channel_ref"] = match.group(1)
                lists = list((await db.scalars(select(ListNetwork).where(ListNetwork.active.is_(True)).order_by(ListNetwork.code))).all())
                if not lists:
                    await conversation.set("idle")
                    await db.commit()
                    await reply(message, "⚠️ فعلاً هیچ لیست فعالی وجود ندارد.")
                    return
                if len(lists) == 1:
                    data["list_id"] = lists[0].id
                    await conversation.set("awaiting_channel_confirmation", data)
                    await db.commit()
                    await reply(message, f"📋 {lists[0].name}\nبرای ثبت نهایی تأیید کنید.", inline_keypad=inline_keyboard((("reg:confirm", "✅ تأیید"), ("home", "↩️ انصراف"))))
                    return
                await conversation.set("awaiting_list", data)
                await db.commit()
                rows = tuple((f"list:{item.id}", f"{item.code} | {item.name}") for item in lists)
                await reply(message, "📚 لیست موردنظر را انتخاب کنید:", inline_keypad=inline_keyboard(rows))
                return

            if session.state == "awaiting_list":
                await db.commit()
                await reply(message, "از دکمه‌های لیست استفاده کنید.")
                return

            if session.state == "awaiting_channel_confirmation":
                if text.lower() in {"تأیید", "تایید", "yes", "1"}:
                    request = await RegistrationService(db).start(
                        rubika_guid=data["channel_ref"], applicant=user,
                        source=RegistrationSource.SELF, list_id=data["list_id"],
                    )
                    await RegistrationService(db).submit_for_verification(request)
                    await conversation.set("idle")
                    await db.commit()
                    await reply(message, f"✅ درخواست ثبت شد.\nکد پیگیری: {request.id[:8]}")
                    return
                await conversation.set("idle")
                await db.commit()
                await reply(message, "ثبت لغو شد.")
                return

            if session.state == "ad_title":
                data["title"] = text[:255]
                await conversation.set("ad_content_ref", data)
                await db.commit()
                await reply(message, "📎 شناسه پیام تبلیغ در کانال مرجع را ارسال کنید.")
                return

            if session.state == "ad_content_ref":
                data["content_ref"] = text
                await conversation.set("ad_count", data)
                await db.commit()
                await reply(message, "🔢 تعداد کانال هدف را وارد کنید.")
                return

            if session.state == "ad_count":
                if not text.isdigit() or int(text) <= 0:
                    await db.commit()
                    await reply(message, "❌ تعداد باید عدد مثبت باشد.")
                    return
                data["channel_count"] = int(text)
                await conversation.set("ad_retention", data)
                await db.commit()
                await reply(message, "⏱ مدت ماندگاری را به ساعت وارد کنید. مثال: 6")
                return

            if session.state == "ad_retention":
                if not text.isdigit() or int(text) <= 0:
                    await db.commit()
                    await reply(message, "❌ مدت باید عدد مثبت باشد.")
                    return
                try:
                    unit, total = await CommerceService(db).quote(
                        list_id=data["list_id"], channel_count=data["channel_count"], retention_hours=int(text)
                    )
                    order = await CommerceService(db).create_order(
                        advertiser=user, title=data["title"], content_ref=data["content_ref"],
                        list_id=data["list_id"], channel_count=data["channel_count"], retention_hours=int(text)
                    )
                except ValueError as exc:
                    await conversation.set("idle")
                    await db.commit()
                    await reply(message, f"⛔ قیمت‌گذاری انجام نشد: {exc}")
                    return
                await conversation.set("idle")
                await db.commit()
                await reply(message, f"💰 پیش‌فاکتور آماده شد\n\nتعداد: {order.channel_count}\nمدت: {order.retention_hours} ساعت\nقیمت هر کانال: {unit:,}\nمبلغ کل: {total:,}\n\nشناسه سفارش: {order.id[:8]}", inline_keypad=inline_keyboard((("home", "🏠 منوی اصلی"),)))
                return

            if session.state == "support_message":
                await conversation.set("idle")
                await db.commit()
                await reply(message, "✅ درخواست پشتیبانی ثبت شد.")
                return

            if session.state == "awaiting_status_channel":
                await conversation.set("idle")
                channel = await db.scalar(select(__import__("ad_network.core.models", fromlist=["Channel"]).Channel).where(__import__("ad_network.core.models", fromlist=["Channel"]).Channel.rubika_guid == text.lstrip("@")))
                await db.commit()
                if channel:
                    await reply(message, f"📊 وضعیت: {channel.status.value}\nکد لیست: {channel.list_code or '-'}")
                else:
                    await reply(message, "❌ کانال پیدا نشد.")
                return

            await db.commit()

    return bot
