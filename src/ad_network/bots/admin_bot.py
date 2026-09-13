from fast_rub import Client
from sqlalchemy import select

from ..core.config import Settings
from ..core.db import SessionFactory
from ..core.models import Channel, RegistrationRequest, RegistrationStatus, UserRole
from ..core.roles import RoleService
from ..core.services import RegistrationService, VerificationService
from .common import reply, update_text, update_user_id


async def build_admin_bot(settings: Settings) -> Client:
    bot = Client(settings.admin_bot_token)

    @bot.on_message()
    async def handle(message):
        user_id = update_user_id(message)
        if not user_id:
            return
        text = update_text(message)
        async with SessionFactory() as db:
            roles = RoleService(db, settings)
            user = await roles.get_or_create_user(rubika_user_id=user_id)
            allowed = roles.has(user, UserRole.ADMIN, UserRole.SUPERVISOR, UserRole.OWNER)
            if not allowed:
                await db.commit()
                await reply(message, "⛔ دسترسی این ربات فقط برای ادمین‌ها و ناظران شبکه است.")
                return

            if text in {"/start", "منو", "menu"}:
                await db.commit()
                await reply(message, "🛠 داشبورد ادمین\n\n1️⃣ وظایف\n2️⃣ کانال‌ها\n3️⃣ درخواست‌های ثبت\n4️⃣ جذب کانال\n5️⃣ عملیات تبلیغ\n6️⃣ تخلفات\n7️⃣ عملکرد و درآمد\n8️⃣ آموزش")
                return

            if text == "3":
                requests = list((await db.scalars(
                    select(RegistrationRequest)
                    .where(RegistrationRequest.status == RegistrationStatus.PENDING_VERIFICATION)
                    .order_by(RegistrationRequest.created_at)
                    .limit(20)
                )).all())
                if not requests:
                    await db.commit()
                    await reply(message, "📭 درخواست معلقی وجود ندارد.")
                    return
                lines = [f"• {item.id[:8]} | لیست: {item.list_id}" for item in requests]
                await db.commit()
                await reply(message, "📥 درخواست‌های معلق:\n\n" + "\n".join(lines) + "\n\nبرای بررسی: بررسی <کد>")
                return

            parts = text.split(maxsplit=1)
            command = parts[0] if parts else ""
            short_id = parts[1].strip() if len(parts) == 2 else ""
            if command in {"بررسی", "check"} and short_id:
                request = await db.scalar(select(RegistrationRequest).where(
                    RegistrationRequest.id.like(f"{short_id}%"),
                    RegistrationRequest.status == RegistrationStatus.PENDING_VERIFICATION,
                ))
                if request is None:
                    await db.commit()
                    await reply(message, "❌ درخواست پیدا نشد.")
                    return
                channel = await db.get(Channel, request.channel_id)
                await db.commit()
                await reply(message, f"🔎 درخواست {request.id[:8]}\nکانال: {channel.rubika_guid if channel else '-'}\nلیست: {request.list_id}\n\nپس از بررسی دسترسی اکانت لیست، بنویسید:\nدسترسی {request.id[:8]}\n\nسپس برای فعال‌سازی:\nتأیید {request.id[:8]}")
                return

            if command in {"دسترسی", "access"} and short_id:
                request = await db.scalar(select(RegistrationRequest).where(
                    RegistrationRequest.id.like(f"{short_id}%"),
                    RegistrationRequest.status == RegistrationStatus.PENDING_VERIFICATION,
                ))
                if request is None:
                    await db.commit()
                    await reply(message, "❌ درخواست پیدا نشد.")
                    return
                await VerificationService(db).mark_permissions(
                    request.channel_id,
                    verified_by=user.id,
                    can_send=True,
                    can_edit=True,
                    can_delete=True,
                    notes="verified manually by admin bot",
                )
                await db.commit()
                await reply(message, "✅ دسترسی‌های ارسال، ویرایش و حذف ثبت شد. حالا «تأیید <کد>» را اجرا کنید.")
                return

            if command in {"تأیید", "تایید", "approve"} and short_id:
                request = await db.scalar(select(RegistrationRequest).where(
                    RegistrationRequest.id.like(f"{short_id}%"),
                    RegistrationRequest.status == RegistrationStatus.PENDING_VERIFICATION,
                ))
                if request is None:
                    await db.commit()
                    await reply(message, "❌ درخواست پیدا نشد.")
                    return
                try:
                    await RegistrationService(db).verify(request, approved=True, verifier_id=user.id)
                    await db.commit()
                except ValueError as exc:
                    await db.rollback()
                    await reply(message, f"⛔ فعال‌سازی انجام نشد: {exc}")
                    return
                await reply(message, f"✅ کانال فعال شد و کد لیست اختصاص یافت. درخواست {request.id[:8]}")
                return

            if command in {"رد", "ردکردن", "reject"} and short_id:
                request = await db.scalar(select(RegistrationRequest).where(
                    RegistrationRequest.id.like(f"{short_id}%"),
                    RegistrationRequest.status == RegistrationStatus.PENDING_VERIFICATION,
                ))
                if request is None:
                    await db.commit()
                    await reply(message, "❌ درخواست پیدا نشد.")
                    return
                await RegistrationService(db).verify(request, approved=False, verifier_id=user.id)
                await db.commit()
                await reply(message, f"🚫 درخواست {request.id[:8]} رد شد.")
                return

            await db.commit()
            responses = {
                "1": "📋 وظایف امروز.", "2": "📺 کانال‌های تحت مسئولیت.",
                "4": "🎯 جذب کانال و پیگیری سرنخ‌ها.", "5": "📣 صف عملیات تبلیغ.",
                "6": "⚠️ تخلفات.", "7": "📈 عملکرد و درآمد.", "8": "🎓 آموزش مرحله‌ای.",
            }
            if text in responses:
                await reply(message, responses[text])

    return bot
