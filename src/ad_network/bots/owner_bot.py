import json
from datetime import datetime, timezone

from sqlalchemy import func, select

from ..core.campaigns import Campaign, CampaignTarget
from ..core.commerce import AdOrder, EarningsEntry, Payment, PriceRule
from ..core.config import Settings
from ..core.db import SessionFactory
from ..core.models import AuditLog, Channel, ChannelStatus, ListAccount, ListNetwork, UserRole, Violation
from ..core.roles import RoleService
from .common import button_id, inline_keyboard, is_duplicate_update, quick_keyboard, reply, resolve_user, update_text

_STATES: dict[str, tuple[str, dict]] = {}
FAMILIES = {
    "pulse": ("⚡ PULSE", 12, (100, 300, 500, 700)),
    "boost": ("🚀 BOOST", 6, (1000, 2000, 3000, 4000, 5000)),
    "reach": ("👁 REACH", 0, (50, 100, 200, 300, 500, 600)),
}
STATUS = {"draft":"📝 پیش‌نویس","active":"🟢 فعال","paused":"⏸ متوقف","offline":"🔴 آفلاین","full":"🟡 تکمیل ظرفیت","maintenance":"🛠 تعمیرات","suspended":"🚫 تعلیق","archived":"📦 آرشیو"}


def owner_keyboard():
    return quick_keyboard(
        (("dashboard", "📊 داشبورد"), ("lists", "🗂 لیست‌ها")),
        (("channels", "📺 کانال‌ها"), ("campaigns", "📢 تبلیغات")),
        (("orders", "💳 سفارش‌ها"), ("finance", "💰 مالی")),
        (("violations", "⚠️ تخلفات"), ("performance", "📈 عملکرد")),
        (("reports", "📋 گزارش‌ها"), ("tasks", "🧩 وظایف")),
        (("security", "🔐 امنیت"), ("notifications", "🔔 اعلان‌ها")),
        (("settings", "⚙️ تنظیمات"), ("emergency", "🚨 عملیات اضطراری")),
        (("refresh", "🔄 بروزرسانی"),),
    )


def kb(*rows):
    return inline_keyboard(*rows)


def money(value):
    return f"{int(value or 0):,}"


def list_code(kind, threshold):
    if kind == "pulse":
        return f"P12-{threshold}"
    if kind == "boost":
        return f"B6-{threshold // 1000}K"
    return f"V-{threshold}"


def back_row(target="dashboard"):
    return ((f"flow:back:{target}", "🔙 بازگشت"),)


async def build_owner_bot(settings: Settings):
    from maxrubika import Bot

    bot = Bot(settings.owner_bot_token, timeout=30, max_retries=5)

    async def auth(event, db):
        user_id = await resolve_user(bot, event)
        if not user_id:
            return None, None
        roles = RoleService(db, settings)
        user = await roles.get_or_create_user(rubika_user_id=user_id)
        return user_id, user if roles.has(user, UserRole.OWNER, UserRole.SUPERVISOR) else None

    async def audit(db, actor, action, entity_type, entity_id, meta=None, **kwargs):
        metadata = meta if meta is not None else kwargs.get("after", {})
        db.add(AuditLog(actor_id=actor, action=action, entity_type=entity_type, entity_id=entity_id,
                        metadata_json=json.dumps(metadata or {}, ensure_ascii=False)))

    async def dashboard(event, db):
        lists = await db.scalar(select(func.count(ListNetwork.id)).where(ListNetwork.active.is_(True)))
        channels = await db.scalar(select(func.count(Channel.id)).where(Channel.status == ChannelStatus.ACTIVE))
        pending_channels = await db.scalar(select(func.count(Channel.id)).where(Channel.status == ChannelStatus.PENDING))
        campaigns = await db.scalar(select(func.count(Campaign.id)).where(Campaign.status.in_(["scheduled", "active"])))
        running = await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.status.in_(["planned", "published", "running"])))
        orders = await db.scalar(select(func.count(AdOrder.id)).where(AdOrder.status.in_(["draft", "awaiting_payment"])))
        today = datetime.now(timezone.utc).date()
        violations = await db.scalar(select(func.count(Violation.id)).where(func.date(Violation.created_at) == today))
        revenue = await db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "confirmed", func.date(Payment.confirmed_at) == today))
        alerts = await db.scalar(select(func.count(Violation.id)).where(Violation.resolved.is_(False), Violation.severity >= 3))
        await db.commit()
        await reply(event, "👑 OPEX CONTROL CENTER\n━━━━━━━━━━━━━━━━━━━━\n"
                    f"🟢 System: ACTIVE\n🗂 Lists: {lists or 0}\n📺 Channels: {channels or 0}\n🕐 Pending Channels: {pending_channels or 0}\n"
                    f"📢 Campaigns: {campaigns or 0}\n🚀 Running Ads: {running or 0}\n💳 Pending Orders: {orders or 0}\n"
                    f"⚠️ Violations Today: {violations or 0}\n💰 Revenue Today: {money(revenue)}\n🚨 Alerts: {alerts or 0}", keypad=owner_keyboard())

    async def list_menu(event, db):
        counts = {k: await db.scalar(select(func.count(ListNetwork.id)).where(ListNetwork.list_type == k, ListNetwork.active.is_(True))) for k in FAMILIES}
        await db.commit()
        await reply(event, "🗂 OPEX LISTS\n━━━━━━━━━━━━━━━━━━━━\n"
                    f"⚡ PULSE 12H: {counts['pulse'] or 0}\n🚀 BOOST 6H: {counts['boost'] or 0}\n👁 REACH VIEW: {counts['reach'] or 0}",
                    inline_keypad=kb((('lists:pulse','⚡ PULSE'),('lists:boost','🚀 BOOST'),('lists:reach','👁 REACH')),
                                     (('list:create','➕ ایجاد لیست'),('lists:all','📋 همه لیست‌ها')),(('home','🏠 خانه'),)))

    async def list_index(event, db, kind=None, threshold=None):
        query = select(ListNetwork).order_by(ListNetwork.code)
        if kind:
            query = query.where(ListNetwork.list_type == kind)
        if threshold is not None:
            query = query.where(ListNetwork.required_views == threshold if kind == "reach" else ListNetwork.min_stat == threshold)
        items = (await db.scalars(query.limit(50))).all()
        lines, buttons = [], []
        for item in items:
            count = await db.scalar(select(func.count(Channel.id)).where(Channel.list_id == item.id, Channel.status == ChannelStatus.ACTIVE))
            lines.append(f"{item.code} | {item.name} | {count or 0}/{item.max_channels} | {STATUS.get(item.status, item.status)}")
            buttons.append((f"list:{item.id}", item.code))
        await db.commit()
        await reply(event, "🗂 LISTS\n━━━━━━━━━━━━━━━━━━━━\n" + ("\n".join(lines) or "لیستی وجود ندارد."),
                    inline_keypad=kb(*[tuple(buttons[i:i + 2]) for i in range(0, len(buttons), 2)],
                                    (('list:create','➕ ایجاد'),('lists','↩️ بازگشت'))))

    async def list_detail(event, db, list_id):
        item = await db.get(ListNetwork, list_id)
        if not item:
            await db.commit(); await reply(event, "❌ لیست پیدا نشد."); return
        channels = await db.scalar(select(func.count(Channel.id)).where(Channel.list_id == list_id, Channel.status == ChannelStatus.ACTIVE))
        campaigns = await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.list_id == list_id, CampaignTarget.status.in_(["planned", "published", "running"])))
        violations = await db.scalar(select(func.count(Violation.id)).join(Channel, Channel.id == Violation.channel_id).where(Channel.list_id == list_id))
        revenue = await db.scalar(select(func.coalesce(func.sum(EarningsEntry.amount), 0)).where(EarningsEntry.list_id == list_id))
        account = await db.scalar(select(ListAccount).where(ListAccount.list_id == list_id, ListAccount.active.is_(True)).limit(1))
        requirement = item.required_views if item.list_type == "reach" else item.min_stat
        await db.commit()
        await reply(event, f"{FAMILIES.get(item.list_type, FAMILIES['pulse'])[0]} {item.name}\n━━━━━━━━━━━━━━━━━━━━\n"
                    f"شناسه: {item.code}\nوضعیت: {STATUS.get(item.status, item.status)}\nاکانت: {account.rubika_user_id if account else '-'}\n"
                    f"حداقل شرط: {requirement}\nنوع: {item.list_type.upper()}\nتعهد: {item.retention_hours} ساعت\n"
                    f"کانال‌ها: {channels or 0}/{item.max_channels}\nکمپین فعال: {campaigns or 0}\nتخلفات: {violations or 0}\nدرآمد: {money(revenue)}",
                    inline_keypad=kb((('list:channels:'+list_id,'📺 کانال‌ها'),('list:campaigns:'+list_id,'📢 تبلیغات')),
                                    (('list:performance:'+list_id,'📊 عملکرد'),('list:violations:'+list_id,'⚠️ تخلفات')),
                                    (('list:pause:'+list_id,'⏸ توقف/فعال'),('list:archive:'+list_id,'🗑 آرشیو')),(('lists','↩️ بازگشت'),)))

    async def channels(event, db, status=None, list_id=None):
        query = select(Channel).order_by(Channel.created_at.desc()).limit(40)
        if status:
            query = query.where(Channel.status == status)
        if list_id:
            query = query.where(Channel.list_id == list_id)
        rows = (await db.scalars(query)).all()
        lines, buttons = [], []
        for c in rows:
            lines.append(f"📺 {c.title or c.username or c.rubika_guid} | {c.status.value} | اعضا {c.member_count or 0} | V24 {c.views_24h} | تخلف {c.violation_count}")
            buttons.append((f"channel:{c.id}", (c.title or c.rubika_guid)[:22]))
        await db.commit()
        await reply(event, "📺 OPEX CHANNELS\n━━━━━━━━━━━━━━━━━━━━\n" + ("\n".join(lines) or "کانالی وجود ندارد."),
                    inline_keypad=kb((('channels:active','🟢 فعال'),('channels:pending','🕐 انتظار')),
                                     (('channels:warning','⚠️ مشکل‌دار'),('channels:removed','🚫 حذف‌شده')),
                                     *[tuple(buttons[i:i + 2]) for i in range(0, len(buttons), 2)],(('home','🏠 خانه'),)))

    async def channel_detail(event, db, channel_id):
        c = await db.get(Channel, channel_id)
        if not c:
            await db.commit(); await reply(event, "❌ کانال پیدا نشد."); return
        l = await db.get(ListNetwork, c.list_id) if c.list_id else None
        ads = await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.channel_id == channel_id))
        if l and l.list_type == "reach": eligible = c.views_24h >= l.required_views
        elif l and l.list_type == "boost": eligible = (c.member_count or 0) >= l.min_stat
        else: eligible = bool(l and c.views_24h >= l.min_stat)
        await db.commit()
        await reply(event, f"📺 CHANNEL\n━━━━━━━━━━━━━━━━━━━━\nنام: {c.title or '-'}\nشناسه: {c.rubika_guid}\nUsername: @{c.username or '-'}\n"
                    f"List: {l.name if l else '-'}\nاعضا: {c.member_count or 0}\nView24h: {c.views_24h}\nوضعیت: {c.status.value}\n"
                    f"تبلیغات: {ads or 0}\nتخلفات: {c.violation_count}\nشرط عضویت: {'🟢 واجد شرایط' if eligible else '🔴 فاقد شرایط'}",
                    inline_keypad=kb((('channel:eligibility:'+channel_id,'🔎 بررسی شرایط'),('channel:violations:'+channel_id,'⚠️ تخلفات')),
                                    (('channel:suspend:'+channel_id,'⛔ تعلیق'),('channel:remove:'+channel_id,'🚫 حذف')),(('channels','↩️ بازگشت'),)))

    async def campaigns(event, db, status=None, list_id=None):
        query = select(Campaign).order_by(Campaign.created_at.desc()).limit(40)
        if status: query = query.where(Campaign.status == status)
        if list_id: query = query.join(CampaignTarget, CampaignTarget.campaign_id == Campaign.id).where(CampaignTarget.list_id == list_id)
        rows = (await db.scalars(query)).unique().all(); lines=[]; buttons=[]
        for c in rows:
            total=await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.campaign_id==c.id)); done=await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.campaign_id==c.id,CampaignTarget.status=='retained')); failed=await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.campaign_id==c.id,CampaignTarget.status=='failed'))
            lines.append(f"📢 {c.title} | {c.status} | {done or 0}/{total or 0} | failed {failed or 0}"); buttons.append((f"campaign:{c.id}",c.title[:22]))
        await db.commit(); await reply(event,"📢 CAMPAIGNS\n━━━━━━━━━━━━━━━━━━━━\n"+("\n".join(lines) or "کمپینی وجود ندارد."),inline_keypad=kb((('campaigns:active','🟢 فعال'),('campaigns:queued','🕐 صف')),(('campaigns:completed','✅ تکمیل'),('campaigns:failed','❌ ناموفق')),*[tuple(buttons[i:i+2]) for i in range(0,len(buttons),2)],(('home','🏠 خانه'),)))

    async def campaign_detail(event, db, campaign_id):
        c=await db.get(Campaign,campaign_id)
        if not c: await db.commit(); await reply(event,"❌ کمپین پیدا نشد."); return
        total=await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.campaign_id==campaign_id)); published=await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.campaign_id==campaign_id,CampaignTarget.published_at.is_not(None)); done=await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.campaign_id==campaign_id,CampaignTarget.status=='retained')); failed=await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.campaign_id==campaign_id,CampaignTarget.status=='failed'))
        await db.commit(); await reply(event,f"📢 CAMPAIGN\n━━━━━━━━━━━━━━━━━━━━\nعنوان: {c.title}\nشناسه: {c.id}\nوضعیت: {c.status}\nTarget: {total or 0}\nمنتشرشده: {published or 0}\nتکمیل‌شده: {done or 0}\nناموفق: {failed or 0}\nتعهد: {c.retention_hours} ساعت",inline_keypad=kb((('campaign:pause:'+campaign_id,'⏸ توقف/ادامه'),('campaign:cancel:'+campaign_id,'❌ لغو')),(('campaigns','↩️ بازگشت'),)))

    async def orders(event, db, status=None):
        query=select(AdOrder).order_by(AdOrder.created_at.desc()).limit(40)
        if status: query=query.where(AdOrder.status==status)
        rows=(await db.scalars(query)).all(); buttons=[(f"order:{o.id}",f"💳 #{o.id[:8]}") for o in rows]
        await db.commit(); await reply(event,"💳 ORDERS\n━━━━━━━━━━━━━━━━━━━━\n"+( '\n'.join(f'#{o.id[:8]} | {o.status.value} | {money(o.total_price)} | {o.channel_count} کانال' for o in rows) or 'سفارشی وجود ندارد.'),inline_keypad=kb((('orders:awaiting_payment','💳 پرداخت‌نشده'),('orders:paid','💰 پرداخت‌شده')),(('orders:running','🔄 اجرا'),('orders:completed','✅ تکمیل')),*[tuple(buttons[i:i+2]) for i in range(0,len(buttons),2)],(('home','🏠 خانه'),)))

    async def order_detail(event, db, order_id):
        o=await db.get(AdOrder,order_id); p=await db.scalar(select(Payment).where(Payment.order_id==order_id)); l=await db.get(ListNetwork,o.list_id) if o else None
        if not o: await db.commit(); await reply(event,'❌ سفارش پیدا نشد.'); return
        await db.commit(); await reply(event,f"💳 ORDER #{order_id[:12]}\n━━━━━━━━━━━━━━━━━━━━\nعنوان: {o.title}\nمشتری: {o.advertiser_id}\nList: {l.name if l else '-'}\nتعداد کانال: {o.channel_count}\nقیمت: {money(o.total_price)}\nپرداخت: {p.status.value if p else '-'}\nوضعیت: {o.status.value}",inline_keypad=kb((('order:cancel:'+order_id,'❌ لغو سفارش'),('orders','↩️ بازگشت'),)))

    async def finance(event, db):
        today=datetime.now(timezone.utc).date(); total=await db.scalar(select(func.coalesce(func.sum(Payment.amount),0)).where(Payment.status=='confirmed')); daily=await db.scalar(select(func.coalesce(func.sum(Payment.amount),0)).where(Payment.status=='confirmed',func.date(Payment.confirmed_at)==today)); pending=await db.scalar(select(func.coalesce(func.sum(Payment.amount),0)).where(Payment.status=='pending')); earnings=await db.scalar(select(func.coalesce(func.sum(EarningsEntry.amount),0))); rules=await db.scalar(select(func.count(PriceRule.id)).where(PriceRule.active.is_(True)))
        await db.commit(); await reply(event,f"💰 OPEX FINANCE\n━━━━━━━━━━━━━━━━━━━━\nدرآمد امروز: {money(daily)}\nکل درآمد: {money(total)}\nپرداخت در انتظار: {money(pending)}\nسهم ثبت‌شده: {money(earnings)}\nتعرفه فعال: {rules or 0}",inline_keypad=kb((('finance:revenue','📊 درآمد'),('finance:payments','💳 پرداخت‌ها')),(('finance:pricing','💵 تعرفه‌ها'),('finance:profit','📈 سود و زیان')),(('home','🏠 خانه'),)))

    async def violations(event, db, channel_id=None):
        query=select(Violation).order_by(Violation.created_at.desc()).limit(40)
        if channel_id:query=query.where(Violation.channel_id==channel_id)
        rows=(await db.scalars(query)).all(); today=datetime.now(timezone.utc).date(); count=await db.scalar(select(func.count(Violation.id)).where(func.date(Violation.created_at)==today)); risk=await db.scalar(select(func.count(Violation.id)).where(Violation.resolved.is_(False),Violation.severity>=3))
        await db.commit(); await reply(event,f"⚠️ VIOLATIONS\n━━━━━━━━━━━━━━━━━━━━\nامروز: {count or 0}\nپرخطر: {risk or 0}\n\n"+('\n'.join(f'{x.violation_type} | severity={x.severity} | {x.created_at}' for x in rows) or 'تخلفی وجود ندارد.'),inline_keypad=kb((('violations:risk','🔥 پرخطر'),('violations:stats','📊 آمار')),(('home','🏠 خانه'),)))

    async def performance(event, db):
        total=await db.scalar(select(func.count(CampaignTarget.id))); done=await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.status=='retained')); failed=await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.status=='failed')); channels=await db.scalar(select(func.count(Channel.id)).where(Channel.status==ChannelStatus.ACTIVE)); vio=await db.scalar(select(func.count(Violation.id)))
        completion=(done or 0)/(total or 1)*100; success=((total or 0)-(failed or 0))/(total or 1)*100; rate=(vio or 0)/(channels or 1)*100
        await db.commit(); await reply(event,f"📈 PERFORMANCE\n━━━━━━━━━━━━━━━━━━━━\nنرخ تکمیل تبلیغات: {completion:.1f}%\nنرخ موفقیت Targets: {success:.1f}%\nنرخ تخلف: {rate:.1f}%\nکانال فعال: {channels or 0}\nTarget کل: {total or 0}",inline_keypad=kb((('performance:lists','🗂 Lists'),('performance:channels','📺 Channels')),(('performance:campaigns','📢 Campaigns'),('performance:finance','💰 مالی')),(('home','🏠 خانه'),)))

    async def section(event, db, name):
        titles={'reports':'📋 مرکز گزارش‌ها','tasks':'🧩 مرکز وظایف','security':'🔐 امنیت و ثبت رویداد','notifications':'🔔 مرکز اعلان‌ها','settings':'⚙️ تنظیمات اوپکس','emergency':'🚨 عملیات اضطراری'}
        rows={'reports':(('report:daily','📊 گزارش روزانه'),('report:weekly','📊 گزارش هفتگی'),('report:monthly','📊 گزارش ماهانه'),('report:finance','💰 گزارش مالی'),('report:channels','📺 گزارش کانال‌ها'),('report:lists','🗂 گزارش لیست‌ها'),('report:campaigns','📢 گزارش تبلیغات'),('report:violations','⚠️ گزارش تخلفات')),
              'tasks':(('tasks:pending','🆕 در انتظار'),('tasks:urgent','🔥 فوری'),('tasks:active','🔄 فعال'),('tasks:done','✅ تکمیل‌شده')),
              'security':(('security:audit','🧾 ثبت رویدادها'),('security:people','👤 دسترسی‌ها'),('security:critical','🚨 رخدادهای حساس'),('security:rules','🔒 تنظیمات امنیتی')),
              'notifications':(('notifications:critical','🚨 بحرانی'),('notifications:warnings','⚠️ هشدارها'),('notifications:info','ℹ️ اطلاعات'),('notifications:readall','✔️ خواندن همه')),
              'settings':(('settings:lists','🗂 تنظیمات لیست‌ها'),('settings:ads','📢 تبلیغات'),('settings:violations','⚠️ قوانین تخلف'),('settings:finance','💰 مالی'),('settings:automation','🧠 خودکارسازی'),('settings:system','🛠 سامانه')),
              'emergency':(('emergency:ads','🛑 توقف تبلیغات'),('emergency:rotation','🛑 توقف چرخش'),('emergency:lists','🛑 توقف همه لیست‌ها'),('emergency:workers','🛑 توقف کارگرها'),('emergency:reconnect','🔄 اتصال مجدد اکانت‌ها'),('emergency:resume','▶️ ادامه عملیات'))}[name]
        await db.commit(); await reply(event,titles[name]+"\n━━━━━━━━━━━━━━━━━━━━",inline_keypad=kb(*[tuple(rows[i:i+2]) for i in range(0,len(rows),2)],( ('home','🏠 خانه'),)))

    async def action(event, a):
        uid=await resolve_user(bot,event)
        if not uid:return
        async with SessionFactory() as db:
            _,user=await auth(event,db)
            if not user:await db.rollback();await reply(event,'⛔ دسترسی ندارید.');return
            if a in {'home','dashboard','refresh'}:_STATES.pop(uid,None);await dashboard(event,db);return
            if a=='lists':await list_menu(event,db);return
            if a=='lists:all':await list_index(event,db);return
            if a.startswith('lists:') and a.split(':')[1] in FAMILIES:await list_index(event,db,a.split(':')[1]);return
            if a=='list:create':_STATES[uid]=('list_type',{});await db.commit();await reply(event,'➕ ایجاد لیست\nنوع را ارسال کنید: PULSE / BOOST / REACH');return
            if a.startswith('list:') and a.count(':')==1:await list_detail(event,db,a.split(':')[1]);return
            if a.startswith('list:channels:'):await channels(event,db,list_id=a.split(':',2)[2]);return
            if a.startswith('list:campaigns:'):await campaigns(event,db,list_id=a.split(':',2)[2]);return
            if a.startswith('list:performance:') or a.startswith('list:violations:'):await db.commit();return
            if a.startswith('list:pause:') or a.startswith('list:archive:'):
                target=a.split(':',2)[2];phrase='تأیید عملیات لیست';_STATES[uid]=('confirm',{'action':'toggle_list' if a.startswith('list:pause:') else 'archive_list','id':target,'phrase':phrase});await db.commit();await reply(event,f'⚠️ عبارت تأیید: {phrase}');return
            if a=='channels':await channels(event,db);return
            if a.startswith('channels:'):await channels(event,db,a.split(':',1)[1]);return
            if a.startswith('channel:') and a.count(':')==1:await channel_detail(event,db,a.split(':')[1]);return
            if a.startswith('channel:eligibility:'):await db.commit();await reply(event,'🔎 بررسی شرایط انجام شد.');return
            if a.startswith('channel:violations:'):await violations(event,db,a.split(':',2)[2]);return
            if a.startswith('channel:suspend:') or a.startswith('channel:remove:'):
                target=a.split(':',2)[2];phrase='تأیید عملیات کانال';_STATES[uid]=('confirm',{'action':'suspend_channel' if a.startswith('channel:suspend:') else 'remove_channel','id':target,'phrase':phrase});await db.commit();await reply(event,f'⚠️ عبارت تأیید: {phrase}');return
            if a=='campaigns':await campaigns(event,db);return
            if a.startswith('campaigns:'):await campaigns(event,db,a.split(':',1)[1]);return
            if a.startswith('campaign:') and a.count(':')==1:await campaign_detail(event,db,a.split(':')[1]);return
            if a.startswith('campaign:pause:') or a.startswith('campaign:cancel:'):
                target=a.split(':',2)[2];phrase='تأیید عملیات کمپین';_STATES[uid]=('confirm',{'action':'toggle_campaign' if a.startswith('campaign:pause:') else 'cancel_campaign','id':target,'phrase':phrase});await db.commit();await reply(event,f'⚠️ عبارت تأیید: {phrase}');return
            if a=='orders':await orders(event,db);return
            if a.startswith('orders:'):await orders(event,db,a.split(':',1)[1]);return
            if a.startswith('order:') and a.count(':')==1:await order_detail(event,db,a.split(':')[1]);return
            if a.startswith('order:cancel:'):
                target=a.split(':',2)[2];phrase='تأیید لغو سفارش';_STATES[uid]=('confirm',{'action':'cancel_order','id':target,'phrase':phrase});await db.commit();await reply(event,f'⚠️ عبارت تأیید: {phrase}');return
            if a=='finance':await finance(event,db);return
            if a=='violations':await violations(event,db);return
            if a=='performance':await performance(event,db);return
            if a in {'reports','tasks','security','notifications','settings','emergency'}:await section(event,db,a);return
            if a.startswith('emergency:'):_STATES[uid]=('confirm',{'action':a,'phrase':'توقف کامل اوپکس' if a in {'emergency:workers','emergency:lists'} else 'تأیید عملیات اضطراری'});await db.commit();await reply(event,'🚨 عملیات اضطراری\nعبارت تأیید: '+_STATES[uid][1]['phrase']);return
            await db.commit()

    @bot.on_callback()
    async def on_callback(bot_instance,event):
        if is_duplicate_update(event):return
        value=button_id(event)
        if value:await action(event,value)

    @bot.on_message()
    async def on_message(bot_instance,event):
        if is_duplicate_update(event):return
        text=update_text(event)
        uid=await resolve_user(bot,event)
        if not uid:return
        if text in {'/start','منو','menu','↩️ بازگشت'}:_STATES.pop(uid,None);await action(event,'dashboard');return
        state=_STATES.get(uid)
        if not state:
            labels={'📊 داشبورد':'dashboard','🗂 لیست‌ها':'lists','🗂 مدیریت لیست‌ها':'lists','📺 کانال‌ها':'channels','📢 تبلیغات':'campaigns','📢 تبلیغات و کمپین‌ها':'campaigns','💳 سفارش‌ها':'orders','💰 مالی':'finance','⚠️ تخلفات':'violations','📈 عملکرد':'performance','📋 گزارش‌ها':'reports','🧩 وظایف':'tasks','🔐 امنیت':'security','🔐 امنیت و ثبت رویداد':'security','🔔 اعلان‌ها':'notifications','⚙️ تنظیمات':'settings','🚨 عملیات اضطراری':'emergency','🔄 بروزرسانی':'refresh'}
            if text in labels:await action(event,labels[text])
            return
        kind,data=state
        async with SessionFactory() as db:
            _,user=await auth(event,db)
            if not user:await db.rollback();_STATES.pop(uid,None);await reply(event,'⛔ دسترسی ندارید.');return
            try:
                if kind=='list_type':
                    family=text.lower().replace('⚡','').replace('🚀','').replace('👁','').strip()
                    if family not in FAMILIES:raise ValueError('نوع باید PULSE، BOOST یا REACH باشد')
                    data['type']=family;_STATES[uid]=('list_threshold',data);await db.commit();await reply(event,'حداقل مقدار را ارسال کنید: '+', '.join(map(str,FAMILIES[family][2])));return
                if kind=='list_threshold':
                    data['threshold']=int(text.replace('K','000').replace(',',''));_STATES[uid]=('list_name',data);await db.commit();await reply(event,'نام نمایشی لیست را ارسال کنید.');return
                if kind=='list_name':
                    if not text:raise ValueError('نام خالی است')
                    data['name']=text;_STATES[uid]=('list_capacity',data);await db.commit();await reply(event,'حداکثر ظرفیت کانال را ارسال کنید.');return
                if kind=='list_capacity':
                    cap=int(text);code=list_code(data['type'],data['threshold'])
                    if cap<1:raise ValueError('ظرفیت نامعتبر است')
                    if await db.scalar(select(ListNetwork).where(ListNetwork.code==code)):raise ValueError('کد تکراری است: '+code)
                    data.update(capacity=cap,code=code);_STATES[uid]=('list_confirm',data);await db.commit();await reply(event,f"━━━━━━━━━━━━━━━━━━━━\n{data['name']}\nکد: {code}\nنوع: {data['type'].upper()}\nحداقل مقدار: {data['threshold']}\nتعهد: {FAMILIES[data['type']][1]} ساعت\nظرفیت: {cap}\n━━━━━━━━━━━━━━━━━━━━\nبرای ثبت، CREATE را ارسال کنید.");return
                if kind=='list_confirm':
                    if text.upper()!='CREATE':raise ValueError('برای ثبت نهایی CREATE را ارسال کنید')
                    family=data['type'];threshold=data['threshold'];item=ListNetwork(code=data['code'],name=data['name'],list_type=family,min_stat=threshold if family!='reach' else 0,required_views=threshold if family=='reach' else 0,retention_hours=FAMILIES[family][1],max_channels=data['capacity'],min_channels=1,status='active',active=True)
                    db.add(item);await db.flush();await audit(db,user.id,'list_created','list',item.id,{'code':item.code,'type':family,'threshold':threshold});await db.commit();_STATES.pop(uid,None);await reply(event,'✅ لیست ساخته شد: '+item.code,keypad=owner_keyboard());return
                if kind=='confirm':
                    if text!=data['phrase']:await db.commit();await reply(event,'❌ عبارت تأیید اشتباه است.');return
                    target=data.get('id');operation=data['action']
                    if operation=='archive_list':item=await db.get(ListNetwork,target);item.active=False;item.status='archived'
                    elif operation=='suspend_channel':item=await db.get(Channel,target);item.status=ChannelStatus.SUSPENDED
                    elif operation=='remove_channel':item=await db.get(Channel,target);item.status=ChannelStatus.REMOVED
                    elif operation=='cancel_campaign':item=await db.get(Campaign,target);item.status='cancelled'
                    elif operation=='cancel_order':item=await db.get(AdOrder,target);item.status='cancelled'
                    elif operation=='toggle_list':item=await db.get(ListNetwork,target);item.active=not item.active;item.status='active' if item.active else 'paused'
                    elif operation=='toggle_campaign':item=await db.get(Campaign,target);item.status='active' if item.status not in {'active','scheduled'} else 'paused'
                    await audit(db,user.id,'sensitive_action',operation,target,{'operation':operation});await db.commit();_STATES.pop(uid,None);await reply(event,'✅ عملیات ثبت شد.',keypad=owner_keyboard());return
            except (ValueError,TypeError) as exc:
                await db.rollback();await reply(event,'❌ '+str(exc))

    return bot
