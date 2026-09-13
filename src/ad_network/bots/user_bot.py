import re

from fast_rub import Client
from sqlalchemy import select

from ..core.config import Settings
from ..core.db import SessionFactory
from ..core.models import ListNetwork, RegistrationSource
from ..core.roles import RoleService
from ..core.services import RegistrationService
from ..core.session import SessionState
from .common import reply, update_text, update_user_id

CHANNEL_RE = re.compile(r"(?:https?://)?(?:rubika\.ir/)?(@?[A-Za-z0-9_]+)$")


async def build_user_bot(settings: Settings) -> Client:
    bot = Client(settings.user_bot_token)

    @bot.on_message()
    async def handle(message):
        user_id = update_user_id(message)
        if not user_id:
            return
        text = update_text(message)

        async with SessionFactory() as db:
            roles = RoleService(db, settings)
            user = await roles.get_or_create_user(rubika_user_id=user_id)
            conversation = SessionState(db, user_id, "user")
            session = await conversation.load()
            data = SessionState.data(session)

            if text in {"/start", "شروع", "منو", "menu"}:
                await conversation.set("idle")
                await db.commit()
                await reply(message, "📣 شبکه تبلیغات\n\n1️⃣ ثبت کانال\n2️⃣ وضعیت کانال\n3️⃣ درخواست تبلیغ\n4️⃣ تعرفه‌ها\n5️⃣ پشتیبانی\n\nبرای ثبت کانال، «1» را ارسال کنید.")
                return

            if session.state == "idle" and text == "1":
                await conversation.set("awaiting_channel", {})
                await db.commit()
                await reply(message, "🔗 لینک یا شناسه عمومی کانال را ارسال کنید.")
                return

            if session.state == "awaiting_channel":
                match = CHANNEL_RE.fullmatch(text)
                if not match:
                    await db.commit()
                    await reply(message, "❌ فرمت کانال معتبر نیست. نمونه: @mychannel")
                    return
                channel_ref = match.group(1)
                lists = list((await db.scalars(select(ListNetwork).where(ListNetwork.active.is_(True)).order_by(ListNetwork.code))).all())
                if not lists:
                    await conversation.set("idle")
                    await db.commit()
                    await reply(message, "⚠️ فعلاً هیچ لیست فعالی برای ثبت کانال وجود ندارد.")
                    return
                data = {"channel_ref": channel_ref}
                if len(lists) == 1:
                    data["list_id"] = lists[0].id
                    await conversation.set("awaiting_channel_confirmation", data)
                    await db.commit()
                    await reply(message, f"📋 لیست: {lists[0].name} ({lists[0].code})\n\nبرای ادامه «تأیید» را ارسال کنید.")
                    return
                await conversation.set("awaiting_list", data)
                await db.commit()
                options = "\n".join(f"{i + 1}️⃣ {item.name} ({item.code})" for i, item in enumerate(lists))
                await reply(message, f"📚 لیست موردنظر را انتخاب کنید:\n\n{options}")
                return

            if session.state == "awaiting_list":
                lists = list((await db.scalars(select(ListNetwork).where(ListNetwork.active.is_(True)).order_by(ListNetwork.code))).all())
                if not text.isdigit() or not 1 <= int(text) <= len(lists):
                    await db.commit()
                    await reply(message, "❌ شماره لیست معتبر نیست.")
                    return
                selected = lists[int(text) - 1]
                data["list_id"] = selected.id
                await conversation.set("awaiting_channel_confirmation", data)
                await db.commit()
                await reply(message, f"📋 {selected.name} ({selected.code}) انتخاب شد.\n\nبرای ثبت نهایی «تأیید» را بفرستید.")
                return

            if session.state == "awaiting_channel_confirmation":
                if text not in {"تأیید", "تایید", "yes", "1"}:
                    await conversation.set("idle")
                    await db.commit()
                    await reply(message, "ثبت لغو شد.")
                    return
                registration = RegistrationService(db)
                request = await registration.start(
                    rubika_guid=data["channel_ref"],
                    applicant=user,
                    source=RegistrationSource.SELF,
                    list_id=data["list_id"],
                )
                await registration.submit_for_verification(request)
                await conversation.set("idle")
                await db.commit()
                await reply(message, f"✅ درخواست ثبت شد.\n\nکد پیگیری: {request.id[:8]}\nپس از بررسی ادمین، نتیجه برای شما ارسال می‌شود.")
                return

            await conversation.set("idle")
            await db.commit()
            await reply(message, "برای شروع دوباره «/start» را ارسال کنید.")

    return bot
