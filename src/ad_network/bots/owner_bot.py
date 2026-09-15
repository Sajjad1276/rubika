import json
from datetime import datetime, timezone

from sqlalchemy import func, select

from ..core.campaigns import Campaign, CampaignTarget
from ..core.commerce import AdOrder, EarningsEntry, Payment, PriceRule
from ..core.config import Settings
from ..core.db import SessionFactory
from ..core.models import AuditLog, Channel, ChannelStatus, ListAccount, ListNetwork, Task, TaskStatus, User, UserRole, Violation
from ..core.roles import RoleService
from .common import button_id, inline_keyboard, is_duplicate_update, quick_keyboard, reply, resolve_user, update_text

_STATES: dict[str, tuple[str, dict]] = {}
FAMILIES = {
    "pulse": ("⚡ PULSE", 12, (100, 300, 500, 700)),
    "boost": ("🚀 BOOST", 6, (1000, 2000, 3000, 4000, 5000)),
    "reach": ("👁 REACH", 0, (50, 100, 200, 300, 500, 600)),
}
STATUS_LABELS = {"draft":"📝 پیش‌نویس","active":"🟢 فعال","paused":"⏸ متوقف","offline":"🔴 آفلاین","full":"🟡 تکمیل ظرفیت","maintenance":"🛠 تعمیرات","suspended":"🚫 تعلیق","archived":"📦 آرشیو"}


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


def _kb(*rows):
    return inline_keyboard(*rows)


def _money(v):
    return f"{int(v or 0):,}"


def _roles(user):
    try:
        value = json.loads(user.roles_json or "[]")
    except (json.JSONDecodeError, TypeError):
        return set()
    return set(value) if isinstance(value, list) else set()


def _type(value):
    return value if value in FAMILIES else "pulse"


def _code(kind, threshold):
    if kind == "pulse": return f"P12-{threshold}"
    if kind == "boost": return f"B6-{threshold // 1000}K"
    return f"V-{threshold}"


async def build_owner_bot(settings: Settings):
    from maxrubika import Bot
    bot = Bot(settings.owner_bot_token, timeout=30, max_retries=5)

    async def auth(event, db):
        uid = await resolve_user(bot, event)
        if not uid:
            return None, None
        roles = RoleService(db, settings)
        user = await roles.get_or_create_user(rubika_user_id=uid)
        if not roles.has(user, UserRole.OWNER, UserRole.SUPERVISOR):
            return uid, None
        return uid, user

    async def audit(db, actor, action, entity_type, entity_id, meta=None):
        db.add(AuditLog(actor_id=actor, action=action, entity_type=entity_type, entity_id=entity_id, metadata_json=json.dumps(meta or {}, ensure_ascii=False)))

    async def dashboard(event, db):
        al = await db.scalar(select(func.count(ListNetwork.id)).where(ListNetwork.active.is_(True)))
        ac = await db.scalar(select(func.count(Channel.id)).where(Channel.status == ChannelStatus.ACTIVE))
        pc = await db.scalar(select(func.count(Channel.id)).where(Channel.status == ChannelStatus.PENDING))
        camp = await db.scalar(select(func.count(Campaign.id)).where(Campaign.status.in_(["scheduled", "active"])))
        ads = await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.status.in_(["planned", "published", "running"])))
        po = await db.scalar(select(func.count(AdOrder.id)).where(AdOrder.status.in_(["draft", "awaiting_payment"])))
        today = datetime.now(timezone.utc).date()
        vio = await db.scalar(select(func.count(Violation.id)).where(func.date(Violation.created_at) == today))
        rev = await db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "confirmed", func.date(Payment.confirmed_at) == today))
        critical = await db.scalar(select(func.count(Violation.id)).where(Violation.resolved.is_(False), Violation.severity >= 3))
        await db.commit()
        await reply(event, "👑 OPEX CONTROL CENTER\n━━━━━━━━━━━━━━━━━━━━\n"
                    f"🟢 System: ACTIVE\n🗂 Lists: {al or 0}\n📺 Channels: {ac or 0}\n🕐 Pending Channels: {pc or 0}\n"
                    f"📢 Campaigns: {camp or 0}\n🚀 Running Ads: {ads or 0}\n💳 Pending Orders: {po or 0}\n⚠️ Violations Today: {vio or 0}\n"
                    f"💰 Revenue Today: {_money(rev)}\n🚨 Critical Alerts: {critical or 0}", keypad=owner_keyboard())

    async def lists(event, db):
        counts = {k: await db.scalar(select(func.count(ListNetwork.id)).where(ListNetwork.list_type == k, ListNetwork.active.is_(True))) for k in FAMILIES}
        await db.commit()
        await reply(event, "🗂 OPEX LISTS\n━━━━━━━━━━━━━━━━━━━━\n"
                    f"⚡ PULSE 12H: {counts['pulse'] or 0}\n🚀 BOOST 6H: {counts['boost'] or 0}\n👁 REACH VIEW: {counts['reach'] or 0}",
                    inline_keypad=_kb((('lists:pulse','⚡ PULSE'),('lists:boost','🚀 BOOST'),('lists:reach','👁 REACH')),
                                      (('list:create','➕ ایجاد لیست'),('lists:all','📋 همه لیست‌ها')),(('home','🏠 خانه'),)))

    async def list_index(event, db, kind=None, threshold=None):
        q = select(ListNetwork).order_by(ListNetwork.code)
        if kind: q = q.where(ListNetwork.list_type == kind)
        if threshold is not None: q = q.where(ListNetwork.required_views == threshold if kind == 'reach' else ListNetwork.min_stat == threshold)
        items = (await db.scalars(q.limit(50))).all()
        lines=[]; buttons=[]
        for x in items:
            n=await db.scalar(select(func.count(Channel.id)).where(Channel.list_id==x.id,Channel.status==ChannelStatus.ACTIVE))
            lines.append(f"{x.code} | {x.name} | {n or 0}/{x.max_channels} | {STATUS_LABELS.get(x.status,x.status)}")
            buttons.append((f"list:{x.id}",x.code))
        await db.commit()
        await reply(event,"🗂 LISTS\n━━━━━━━━━━━━━━━━━━━━\n"+("\n".join(lines) or "لیستی وجود ندارد."),inline_keypad=_kb(*[tuple(buttons[i:i+2]) for i in range(0,len(buttons),2)],(('list:create','➕ ایجاد'),('lists','↩️ بازگشت'))))

    async def list_detail(event, db, lid):
        x=await db.get(ListNetwork,lid)
        if not x: await db.commit(); await reply(event,"❌ لیست پیدا نشد.",inline_keypad=_kb((('lists','↩️ بازگشت'),))); return
        channels=await db.scalar(select(func.count(Channel.id)).where(Channel.list_id=lid,Channel.status==ChannelStatus.ACTIVE))
        campaigns=await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.list_id==lid,CampaignTarget.status.in_(['planned','published','running'])))
        violations=await db.scalar(select(func.count(Violation.id)).join(Channel,Channel.id==Violation.channel_id).where(Channel.list_id==lid))
        revenue=await db.scalar(select(func.coalesce(func.sum(EarningsEntry.amount),0)).where(EarningsEntry.list_id==lid))
        account=await db.scalar(select(ListAccount).where(ListAccount.list_id==lid,ListAccount.active.is_(True)).limit(1))
        req=x.required_views if x.list_type=='reach' else x.min_stat
        await db.commit()
        await reply(event,f"{FAMILIES[_type(x.list_type)][0]} {x.name}\n━━━━━━━━━━━━━━━━━━━━\nشناسه: {x.code}\nوضعیت: {STATUS_LABELS.get(x.status,x.status)}\n"
                    f"اکانت: {account.rubika_user_id if account else '-'}\nحداقل شرط: {req}\nنوع: {x.list_type.upper()}\nتعهد: {x.retention_hours} ساعت\n"
                    f"کانال‌ها: {channels or 0}/{x.max_channels}\nکمپین فعال: {campaigns or 0}\nتخلفات: {violations or 0}\nدرآمد: {_money(revenue)}",
                    inline_keypad=_kb((('list:channels:'+lid,'📺 کانال‌ها'),('list:campaigns:'+lid,'📢 تبلیغات')),
                                      (('list:performance:'+lid,'📊 عملکرد'),('list:violations:'+lid,'⚠️ تخلفات')),
                                      (('list:pause:'+lid,'⏸ توقف/فعال'),('list:archive:'+lid,'🗑 آرشیو')),(('lists','↩️ بازگشت'),)))

    async def channels(event, db, status=None, lid=None):
        q=select(Channel).order_by(Channel.created_at.desc()).limit(40)
        if status: q=q.where(Channel.status==status)
        if lid: q=q.where(Channel.list_id==lid)
        rows=(await db.scalars(q)).all(); text=[]; buttons=[]
        for c in rows:
            text.append(f"📺 {c.title or c.username or c.rubika_guid} | {c.status.value} | اعضا {c.member_count or 0} | V24 {c.views_24h} | تخلف {c.violation_count}")
            buttons.append((f"channel:{c.id", (c.title or c.rubika_guid)[:22]))
        await db.commit()
        await reply(event,"📺 OPEX CHANNELS\n━━━━━━━━━━━━━━━━━━━━\n"+("\n".join(text) or "کانالی وجود ندارد."),inline_keypad=_kb((('channels:active','🟢 فعال'),('channels:pending','🕐 انتظار')),(('channels:warning','⚠️ مشکل‌دار'),('channels:removed','🚫 حذف‌شده')),*[tuple(buttons[i:i+2]) for i in range(0,len(buttons),2)],(('home','🏠 خانه'),)))

    async def channel_detail(event, db, cid):
        c=await db.get(Channel,cid)
        if not c: await db.commit(); await reply(event,"❌ کانال پیدا نشد."); return
        l=await db.get(ListNetwork,c.list_id) if c.list_id else None
        ads=await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.channel_id==cid))
        await db.commit()
        await reply(event,f"📺 CHANNEL\n━━━━━━━━━━━━━━━━━━━━\nنام: {c.title or '-'}\nشناسه: {c.rubika_guid}\nUsername: @{c.username or '-'}\n"
                    f"List: {l.name if l else '-'}\nاعضا: {c.member_count or 0}\nView24h: {c.views_24h}\nوضعیت: {c.status.value}\nتبلیغات: {ads or 0}\nتخلفات: {c.violation_count}\n"
                    f"عضویت: {'🟢 واجد شرایط' if l and ((l.list_type=='reach' and c.views_24h>=l.required_views) or (l.list_type!='reach' and (c.member_count if l.list_type=='boost' else c.views_24h or 0)>=l.min_stat)) else '🔴 نیازمند بررسی'}",
                    inline_keypad=_kb((('channel:eligibility:'+cid,'🔎 بررسی شرایط'),('channel:violations:'+cid,'⚠️ تخلفات')),(('channel:suspend:'+cid,'⛔ تعلیق'),('channel:remove:'+cid,'🚫 حذف')),(('channels','↩️ بازگشت'),)))

    async def campaigns(event, db, status=None, lid=None):
        q=select(Campaign).order_by(Campaign.created_at.desc()).limit(40)
        if status:q=q.where(Campaign.status==status)
        if lid:q=q.join(CampaignTarget,CampaignTarget.campaign_id==Campaign.id).where(CampaignTarget.list_id==lid)
        rows=(await db.scalars(q)).unique().all(); text=[]; buttons=[]
        for c in rows:
            total=await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.campaign_id==c.id)); done=await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.campaign_id==c.id,CampaignTarget.status=='retained')); failed=await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.campaign_id==c.id,CampaignTarget.status=='failed'))
            text.append(f"📢 {c.title} | {c.status} | {done or 0}/{total or 0} | failed {failed or 0}"); buttons.append((f"campaign:{c.id}",c.title[:22]))
        await db.commit(); await reply(event,"📢 CAMPAIGNS\n━━━━━━━━━━━━━━━━━━━━\n"+("\n".join(text) or "کمپینی وجود ندارد."),inline_keypad=_kb((('campaigns:active','🟢 فعال'),('campaigns:queued','🕐 صف')),(('campaigns:completed','✅ تکمیل'),('campaigns:failed','❌ ناموفق')),*[tuple(buttons[i:i+2]) for i in range(0,len(buttons),2)],(('home','🏠 خانه'),)))

    async def campaign_detail(event, db, cid):
        c=await db.get(Campaign,cid)
        if not c: await db.commit(); await reply(event,"❌ کمپین پیدا نشد."); return
        total=await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.campaign_id==cid)); pub=await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.campaign_id==cid,CampaignTarget.published_at.is_not(None))); done=await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.campaign_id==cid,CampaignTarget.status=='retained')); failed=await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.campaign_id==cid,CampaignTarget.status=='failed'))
        await db.commit(); await reply(event,f"📢 CAMPAIGN\n━━━━━━━━━━━━━━━━━━━━\nعنوان: {c.title}\nشناسه: {c.id}\nوضعیت: {c.status}\nTarget: {total or 0}\nمنتشرشده: {pub or 0}\nتکمیل‌شده: {done or 0}\nناموفق: {failed or 0}\nتعهد: {c.retention_hours} ساعت",
            inline_keypad=_kb((('campaign:targets:'+cid,'🎯 Targets'),('campaign:performance:'+cid,'📊 عملکرد')),(('campaign:pause:'+cid,'⏸ توقف/ادامه'),('campaign:cancel:'+cid,'❌ لغو')),(('campaigns','↩️ بازگشت'),)))

    async def orders(event, db, status=None):
        q=select(AdOrder).order_by(AdOrder.created_at.desc()).limit(40)
        if status:q=q.where(AdOrder.status==status)
        rows=(await db.scalars(q)).all(); buttons=[]
        text=[f"#{o.id[:8]} | {o.status.value} | {_money(o.total_price)} | {o.channel_count} کانال" for o in rows]
        buttons=[(f"order:{o.id}",f"💳 #{o.id[:8]}") for o in rows]
        await db.commit(); await reply(event,"💳 ORDERS\n━━━━━━━━━━━━━━━━━━━━\n"+("\n".join(text) or "سفارشی وجود ندارد."),inline_keypad=_kb((('orders:awaiting_payment','💳 پرداخت‌نشده'),('orders:paid','💰 پرداخت‌شده')),(('orders:running','🔄 اجرا'),('orders:completed','✅ تکمیل')),*[tuple(buttons[i:i+2]) for i in range(0,len(buttons),2)],(('home','🏠 خانه'),)))

    async def order_detail(event, db, oid):
        o=await db.get(AdOrder,oid); p=await db.scalar(select(Payment).where(Payment.order_id==oid)); l=await db.get(ListNetwork,o.list_id) if o else None
        if not o: await db.commit(); await reply(event,"❌ سفارش پیدا نشد."); return
        await db.commit(); await reply(event,f"💳 ORDER #{oid[:12]}\n━━━━━━━━━━━━━━━━━━━━\nعنوان: {o.title}\nمشتری: {o.advertiser_id}\nList: {l.name if l else '-'}\nتعداد کانال: {o.channel_count}\nقیمت: {_money(o.total_price)}\nپرداخت: {p.status.value if p else '-'}\nوضعیت: {o.status.value}\nایجاد: {o.created_at}",inline_keypad=_kb((('order:payment:'+oid,'💰 پرداخت'),('order:campaign:'+oid,'📢 کمپین')),(('order:cancel:'+oid,'❌ لغو'),('orders','↩️ بازگشت'),)))

    async def finance(event, db):
        today=datetime.now(timezone.utc).date(); rev=await db.scalar(select(func.coalesce(func.sum(Payment.amount),0)).where(Payment.status=='confirmed')); today_rev=await db.scalar(select(func.coalesce(func.sum(Payment.amount),0)).where(Payment.status=='confirmed',func.date(Payment.confirmed_at)==today)); pending=await db.scalar(select(func.coalesce(func.sum(Payment.amount),0)).where(Payment.status=='pending')); earn=await db.scalar(select(func.coalesce(func.sum(EarningsEntry.amount),0))); rules=await db.scalar(select(func.count(PriceRule.id)).where(PriceRule.active.is_(True)))
        await db.commit(); await reply(event,f"💰 OPEX FINANCE\n━━━━━━━━━━━━━━━━━━━━\nدرآمد امروز: {_money(today_rev)}\nکل درآمد: {_money(rev)}\nپرداخت در انتظار: {_money(pending)}\nسهم ثبت‌شده: {_money(earn)}\nتعرفه فعال: {rules or 0}",inline_keypad=_kb((('finance:revenue','📊 درآمد'),('finance:payments','💳 پرداخت‌ها')),(('finance:pricing','💵 تعرفه‌ها'),('finance:profit','📈 سود و زیان')),(('home','🏠 خانه'),)))

    async def violations(event, db, cid=None):
        q=select(Violation).order_by(Violation.created_at.desc()).limit(40)
        if cid:q=q.where(Violation.channel_id==cid)
        rows=(await db.scalars(q)).all(); today=datetime.now(timezone.utc).date(); tc=await db.scalar(select(func.count(Violation.id)).where(func.date(Violation.created_at)==today)); risk=await db.scalar(select(func.count(Violation.id)).where(Violation.resolved.is_(False),Violation.severity>=3))
        await db.commit(); await reply(event,f"⚠️ VIOLATIONS\n━━━━━━━━━━━━━━━━━━━━\nامروز: {tc or 0}\nپرخطر: {risk or 0}\n\n"+('\n'.join(f'{x.violation_type} | severity={x.severity} | {x.created_at}' for x in rows) or 'تخلفی وجود ندارد.'),inline_keypad=_kb((('violations:new','🆕 جدید'),('violations:risk','🔥 پرخطر')),(('violations:stats','📊 آمار'),('home','🏠 خانه'))))

    async def performance(event, db):
        total=await db.scalar(select(func.count(CampaignTarget.id))); done=await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.status=='retained')); failed=await db.scalar(select(func.count(CampaignTarget.id)).where(CampaignTarget.status=='failed')); chans=await db.scalar(select(func.count(Channel.id)).where(Channel.status==ChannelStatus.ACTIVE)); vio=await db.scalar(select(func.count(Violation.id)))
        completion=(done or 0)/(total or 1)*100; success=((total or 0)-(failed or 0))/(total or 1)*100; vr=(vio or 0)/(chans or 1)*100
        await db.commit(); await reply(event,f"📈 PERFORMANCE\n━━━━━━━━━━━━━━━━━━━━\nنرخ تکمیل: {completion:.1f}%\nنرخ موفقیت Targets: {success:.1f}%\nنرخ تخلف: {vr:.1f}%\nکانال فعال: {chans or 0}\nTarget کل: {total or 0}",inline_keypad=_kb((('performance:lists','🗂 Lists'),('performance:channels','📺 Channels')),(('performance:campaigns','📢 Campaigns'),('performance:finance','💰 مالی')),(('home','🏠 خانه'),)))

    async def simple_menu(event, db, kind):
        data={
            'reports':("📋 REPORT CENTER",(("report:daily","📊 روزانه"),("report:weekly","📊 هفتگی"),("report:monthly","📊 ماهانه"),("report:finance","💰 مالی"),("report:channels","📺 کانال‌ها"),("report:lists","🗂 لیست‌ها"),("report:campaigns","📢 تبلیغات"),("report:violations","⚠️ تخلفات"))),
            'tasks':("🧩 TASK CENTER",(("tasks:pending","🆕 در انتظار"),("tasks:urgent","🔥 فوری"),("tasks:active","🔄 فعال"),("tasks:done","✅ تکمیل‌شده"))),
            'security':("🔐 SECURITY CENTER",(("security:audit","🧾 Audit Log"),("security:people","👤 دسترسی‌ها"),("security:critical","🚨 رخدادهای حساس"),("security:rules","🔒 تنظیمات امنیتی"))),
            'notifications':("🔔 NOTIFICATION CENTER",(("notifications:critical","🚨 بحرانی"),("notifications:warnings","⚠️ هشدارها"),("notifications:info","ℹ️ اطلاعات"),("notifications:readall","✔️ خواندن همه"))),
            'settings':("⚙️ OPEX SETTINGS",(("settings:lists","🗂 تنظیمات List"),("settings:ads","📢 تبلیغات"),("settings:violations","⚠️ قوانین تخلف"),("settings:finance","💰 مالی"),("settings:automation","🧠 Automation"),("settings:system","🛠 System"))),
            'emergency':("🚨 EMERGENCY CENTER",(("emergency:ads","🛑 توقف تبلیغات"),("emergency:rotation","🛑 توقف Rotation"),("emergency:lists","🛑 توقف همه Listها"),("emergency:workers","🛑 توقف Worker"),("emergency:reconnect","🔄 اتصال مجدد اکانت‌ها"),("emergency:resume","▶️ ادامه عملیات"))),
        }
        title, rows=data[kind]; await db.commit(); await reply(event,title+"\n━━━━━━━━━━━━━━━━━━━━\nکنترل OPEX از همین‌جا انجام می‌شود.",inline_keypad=_kb(*[tuple(rows[i:i+2]) for i in range(0,len(rows),2)],(('home','🏠 خانه'),)))

    async def action(event, a):
        async with SessionFactory() as db:
            uid,user=await auth(event,db)
            if not uid:return
            if not user: await db.rollback(); await reply(event,'⛔ دسترسی ندارید.'); return
            if a in {'home','back','dashboard','refresh'}: _STATES.pop(uid,None); await dashboard(event,db); return
            if a=='lists': await lists(event,db); return
            if a=='lists:all': await list_index(event,db); return
            if a.startswith('lists:') and a.split(':')[1] in FAMILIES: await list_index(event,db,a.split(':')[1]); return
            if a=='list:create': _STATES[uid]=('list_type',{}); await db.commit(); await reply(event,'➕ ایجاد List\nنوع را ارسال کنید: PULSE / BOOST / REACH'); return
            if a.startswith('list:') and a.count(':')==1: await list_detail(event,db,a.split(':')[1]); return
            if a.startswith('list:channels:'): await channels(event,db,lid=a.rsplit(':',1)[1]); return
            if a.startswith('list:campaigns:'): await campaigns(event,db,lid=a.rsplit(':',1)[1]); return
            if a.startswith('list:violations:'): await violations(event,db); return
            if a.startswith('list:performance:'): await performance(event,db); return
            if a.startswith('list:pause:'):
                x=await db.get(ListNetwork,a.rsplit(':',1)[1]);
                if x:x.active=not x.active;x.status='active' if x.active else 'paused';await audit(db,user.id,'list_toggled','list',x.id,{'active':x.active})
                await db.commit(); await reply(event,'✅ وضعیت List تغییر کرد.',inline_keypad=_kb((('lists','↩️ بازگشت'),))); return
            if a.startswith('list:archive:'):
                _STATES[uid]=('confirm',{'action':'archive_list','id':a.rsplit(':',1)[1],'phrase':'ARCHIVE LIST'}); await db.commit(); await reply(event,'⚠️ آرشیو List\nعبارت تأیید: ARCHIVE LIST'); return
            if a=='channels': await channels(event,db); return
            if a.startswith('channels:'): await channels(event,db,{'active':'active','pending':'pending','warning':'suspended','removed':'removed'}.get(a.split(':')[1])); return
            if a.startswith('channel:') and a.count(':')==1: await channel_detail(event,db,a.split(':')[1]); return
            if a.startswith('channel:violations:'): await violations(event,db,a.rsplit(':',1)[1]); return
            if a.startswith('channel:eligibility:'):
                c=await db.get(Channel,a.rsplit(':',1)[1]); l=await db.get(ListNetwork,c.list_id) if c and c.list_id else None
                ok=bool(c and l and ((l.list_type=='reach' and c.views_24h>=l.required_views) or (l.list_type=='boost' and (c.member_count or 0)>=l.min_stat) or (l.list_type=='pulse' and c.views_24h>=l.min_stat)))
                await db.commit(); await reply(event,'🟢 واجد شرایط' if ok else '🔴 واجد شرایط نیست',inline_keypad=_kb((('channels','↩️ کانال‌ها'),))); return
            if a.startswith('channel:suspend:') or a.startswith('channel:remove:'):
                _STATES[uid]=('confirm',{'action':'suspend_channel' if 'suspend' in a else 'remove_channel','id':a.rsplit(':',1)[1],'phrase':'CONFIRM CHANNEL'}); await db.commit(); await reply(event,'⚠️ عملیات حساس\nعبارت تأیید: CONFIRM CHANNEL'); return
            if a=='campaigns': await campaigns(event,db); return
            if a.startswith('campaigns:'): await campaigns(event,db,{'active':'active','queued':'scheduled','completed':'completed','failed':'failed'}.get(a.split(':')[1])); return
            if a.startswith('campaign:') and a.count(':')==1: await campaign_detail(event,db,a.split(':')[1]); return
            if a.startswith('campaign:pause:'):
                c=await db.get(Campaign,a.rsplit(':',1)[1]);
                if c:c.status='paused' if c.status in {'active','scheduled'} else 'active';await audit(db,user.id,'campaign_toggled','campaign',c.id,{'status':c.status})
                await db.commit(); await reply(event,'✅ وضعیت Campaign تغییر کرد.',inline_keypad=_kb((('campaigns','↩️ بازگشت'),))); return
            if a.startswith('campaign:cancel:'):
                _STATES[uid]=('confirm',{'action':'cancel_campaign','id':a.rsplit(':',1)[1],'phrase':'CANCEL CAMPAIGN'}); await db.commit(); await reply(event,'⚠️ لغو Campaign\nعبارت تأیید: CANCEL CAMPAIGN'); return
            if a=='orders': await orders(event,db); return
            if a.startswith('orders:'): await orders(event,db,{'awaiting_payment':'awaiting_payment','paid':'paid','running':'running','completed':'completed'}.get(a.split(':')[1])); return
            if a.startswith('order:') and a.count(':')==1: await order_detail(event,db,a.split(':')[1]); return
            if a.startswith('order:cancel:'):_STATES[uid]=('confirm',{'action':'cancel_order','id':a.rsplit(':',1)[1],'phrase':'CANCEL ORDER'});await db.commit();await reply(event,'⚠️ لغو Order\nعبارت تأیید: CANCEL ORDER');return
            if a=='finance' or a.startswith('finance:'): await finance(event,db); return
            if a=='violations' or a.startswith('violations:'): await violations(event,db); return
            if a=='performance' or a.startswith('performance:'): await performance(event,db); return
            if a in {'reports','tasks','security','notifications','settings','emergency'}: await simple_menu(event,db,a); return
            if a.startswith('report:') or a.startswith('tasks:') or a.startswith('security:') or a.startswith('notifications:') or a.startswith('settings:'): await simple_menu(event,db,a.split(':')[0]); return
            if a.startswith('emergency:'):
                _STATES[uid]=('confirm',{'action':a,'phrase':'STOP OPEX' if a in {'emergency:workers','emergency:lists'} else 'CONFIRM EMERGENCY'});await db.commit();await reply(event,'🚨 عملیات اضطراری\nعبارت تأیید: '+_STATES[uid][1]['phrase']);return
            await db.commit()

    @bot.on_callback()
    async def on_callback(bot_instance,event):
        if is_duplicate_update(event):return
        a=button_id(event)
        if a:await action(event,a)

    @bot.on_message()
    async def handle(bot_instance,event):
        if is_duplicate_update(event):return
        uid=await resolve_user(bot,event)
        if not uid:return
        text=update_text(event).strip()
        if text in {'/start','منو','menu','↩️ بازگشت'}:
            _STATES.pop(uid,None); await action(event,'dashboard'); return
        state=_STATES.get(uid)
        if not state:
            text_map={'📊 داشبورد':'dashboard','🗂 لیست‌ها':'lists','📺 کانال‌ها':'channels','📢 تبلیغات':'campaigns','💳 سفارش‌ها':'orders','💰 مالی':'finance','⚠️ تخلفات':'violations','📈 عملکرد':'performance','📋 گزارش‌ها':'reports','🧩 وظایف':'tasks','🔐 امنیت':'security','🔔 اعلان‌ها':'notifications','⚙️ تنظیمات':'settings','🚨 عملیات اضطراری':'emergency','🔄 بروزرسانی':'refresh'}
            if text in text_map: await action(event,text_map[text])
            return
        kind,data=state
        async with SessionFactory() as db:
            uid,user=await auth(event,db)
            if not user:await db.rollback();_STATES.pop(uid,None);await reply(event,'⛔ دسترسی ندارید.');return
            try:
                if kind=='list_type':
                    family=text.lower().replace('⚡','').replace('🚀','').replace('👁','').strip()
                    if family not in FAMILIES:raise ValueError('نوع List باید PULSE، BOOST یا REACH باشد')
                    data['type']=family;_STATES[uid]=('list_threshold',data);await db.commit();await reply(event,'حداقل مقدار را ارسال کنید: '+', '.join(map(str,FAMILIES[family][2])));return
                if kind=='list_threshold':
                    data['threshold']=int(text.replace('K','000').replace(',',''));_STATES[uid]=('list_name',data);await db.commit();await reply(event,'نام نمایشی List را ارسال کنید.');return
                if kind=='list_name':
                    if not text:raise ValueError('نام خالی است')
                    data['name']=text;_STATES[uid]=('list_capacity',data);await db.commit();await reply(event,'حداکثر ظرفیت کانال را ارسال کنید.');return
                if kind=='list_capacity':
                    cap=int(text);family=data['type'];threshold=data['threshold'];code=_code(family,threshold)
                    if cap<1:raise ValueError('ظرفیت نامعتبر است')
                    if await db.scalar(select(ListNetwork).where(ListNetwork.code==code)):raise ValueError('کد List تکراری است: '+code)
                    data['capacity']=cap;data['code']=code;_STATES[uid]=('list_confirm',data);await db.commit();await reply(event,f"━━━━━━━━━━━━━━━━━━━━\n{data['name']}\nCode: {code}\nType: {family.upper()}\nThreshold: {threshold}\nRetention: {FAMILIES[family][1]}h\nCapacity: {cap}\n━━━━━━━━━━━━━━━━━━━━\nبرای ثبت CREATE را ارسال کنید.");return
                if kind=='list_confirm':
                    if text.upper()!='CREATE':raise ValueError('برای ثبت نهایی CREATE را ارسال کنید')
                    family=data['type'];threshold=data['threshold'];x=ListNetwork(code=data['code'],name=data['name'],list_type=family,min_stat=threshold if family!='reach' else 0,required_views=threshold if family=='reach' else 0,retention_hours=FAMILIES[family][1],max_channels=data['capacity'],min_channels=1,status='active',active=True)
                    db.add(x);await db.flush();await audit(db,user.id,'list_created','list',x.id,{'code':x.code,'type':family,'threshold':threshold});await db.commit();_STATES.pop(uid,None);await reply(event,'✅ List ساخته شد: '+x.code,keypad=owner_keyboard());return
                if kind=='confirm':
                    if text.upper()!=data['phrase']:await db.commit();await reply(event,'❌ عبارت تأیید اشتباه است.');return
                    target=data['id'];a=data['action']
                    if a=='archive_list':x=await db.get(ListNetwork,target);x.active=False;x.status='archived';await audit(db,user.id,'list_archived','list',target)
                    elif a=='suspend_channel':x=await db.get(Channel,target);x.status=ChannelStatus.SUSPENDED;await audit(db,user.id,'channel_suspended','channel',target)
                    elif a=='remove_channel':x=await db.get(Channel,target);x.status=ChannelStatus.REMOVED;await audit(db,user.id,'channel_removed','channel',target)
                    elif a=='cancel_campaign':x=await db.get(Campaign,target);x.status='cancelled';await audit(db,user.id,'campaign_cancelled','campaign',target)
                    elif a=='cancel_order':x=await db.get(AdOrder,target);x.status='cancelled';await audit(db,user.id,'order_cancelled','order',target)
                    elif a.startswith('emergency:'):await audit(db,user.id,'emergency_action','system','opex',{'operation':a})
                    await db.commit();_STATES.pop(uid,None);await reply(event,'✅ عملیات ثبت شد.',keypad=owner_keyboard());return
            except (ValueError,TypeError) as exc:
                await db.rollback();await reply(event,'❌ '+str(exc))

    return bot
