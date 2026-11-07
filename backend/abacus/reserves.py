"""Manual annual-bill reserve checks. Targets never change with balance updates."""
import calendar
from datetime import date, timedelta
from types import SimpleNamespace
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from .models import Settings, Recurring, AmountChange, ReservePlan, SavingsObservation
from .budget import scheduled_amount, effective_change, shift_month, annual_due_month
from .card_alerts import local_today


def dated(month, day):
    year, number = map(int,month.split('-'))
    return date(year,number,min(day,calendar.monthrange(year,number)[1]))


def schedule_snapshot(db):
    changes = db.scalars(select(AmountChange)).all()
    return [dict(id=r.id,name=r.name,kind=r.kind,frequency=r.frequency,
        start_month=r.start_month,end_month=r.end_month,due_day=r.due_day,due_month=r.due_month,
        distribute_annual=True,changes=[dict(recurring_id=c.recurring_id,month=c.month,amount=c.amount,override=c.override)
            for c in sorted(changes,key=lambda c:(c.month,c.override)) if c.recurring_id==r.id])
        for r in db.scalars(select(Recurring).where(Recurring.kind=='payable',Recurring.frequency=='annual',
            Recurring.distribute_annual==True,Recurring.due_day.is_not(None),Recurring.due_month.is_not(None))
            .order_by(Recurring.id)).all()]


def observe(db, amount, as_of):
    if as_of > local_today():raise ValueError('A recorded savings balance cannot be dated in the future.')
    statement=insert(SavingsObservation).values(amount=amount,as_of=as_of)
    db.execute(statement.on_conflict_do_update(index_elements=['as_of'],set_={'amount':amount}))
    plan=db.get(ReservePlan,1)
    if plan:plan.dismissed_until=None


def events_for(plan, end, day):
    """Credits are due at next month's checkpoint; payments assume due-date withdrawal."""
    schedules=[SimpleNamespace(**item) for item in plan.schedules]
    changes=[SimpleNamespace(**c) for item in plan.schedules for c in item['changes']]
    events=[]
    month=plan.start_date.strftime('%Y-%m')
    while month <= end.strftime('%Y-%m'):
        for item in schedules:
            amount=scheduled_amount(item,changes,month)
            if amount:
                events.append({'date':dated(shift_month(month,1),day),'kind':'allocation','name':item.name,'amount':amount,'month':month})
            if month<item.start_month or (item.end_month and month>item.end_month):continue
            if month[5:]==annual_due_month(item):
                change=effective_change(item,changes,month)
                if change:
                    events.append({'date':dated(month,item.due_day),'kind':'payment','name':item.name,'amount':change.amount,'month':month})
        month=shift_month(month,1)
    return sorted(events,key=lambda e:(e['date'],e['kind'],e['name']))


def flow(events, through):
    # Balances are checked before payments due on their as-of date. Same-day
    # payments are listed separately, so the target cannot silently assume paid.
    return sum(e['amount'] if e['kind']=='allocation' else -e['amount'] for e in events
        if (e['kind']=='allocation' and e['date']<=through) or (e['kind']=='payment' and e['date']<through))


def reserve_check(db):
    today=local_today()
    setting=db.get(Settings,1)
    current=schedule_snapshot(db)
    plan=db.get(ReservePlan,1)
    observations=db.scalars(select(SavingsObservation).where(SavingsObservation.as_of<=today)
        .order_by(SavingsObservation.as_of.desc()).limit(12)).all()
    result={'today':today,'enabled':setting.reserve_alerts_enabled,'checkpoint_day':setting.reserve_checkpoint_day,
        'eligible_bill_count':len(current),'plan':None,'observations':[{'amount':o.amount,'as_of':o.as_of} for o in observations],
        'status':'not_configured' if current else 'no_bills','dismissed':False}
    if plan is None:return result
    month=today.strftime('%Y-%m');day=setting.reserve_checkpoint_day
    this=dated(month,day)
    checkpoint=this if today>=this else dated(shift_month(month,-1),day)
    first=dated(shift_month(plan.start_date.strftime('%Y-%m'),1),day)
    if checkpoint<first:checkpoint=None
    next_check=max(first,dated(shift_month(month,1),day) if today>=this else this)
    # Plan history is frozen; schedule edits require explicit review/replacement.
    result['plan']={'amount':plan.amount,'start_date':plan.start_date,'schedules':plan.schedules,
        'schedule_changed':current!=plan.schedules,'dismissed_until':plan.dismissed_until}
    latest=db.scalar(select(SavingsObservation).where(SavingsObservation.as_of>=plan.start_date,SavingsObservation.as_of<=today)
        .order_by(SavingsObservation.as_of.desc()).limit(1))
    end=dated(shift_month(next_check.strftime('%Y-%m'),12),31)
    events=events_for(plan,end,day)
    target=lambda on: max(0,plan.amount+flow(events,on))
    fresh=latest is not None and (checkpoint is None or latest.as_of>=checkpoint)
    comparison_date=latest.as_of if fresh else today
    shortfall=max(0,target(comparison_date)-latest.amount) if fresh else None
    upcoming=[]
    for due in sorted({e['date'] for e in events if e['kind']=='payment' and today<=e['date']<=today+timedelta(days=30)}):
        bills=[e for e in events if e['kind']=='payment' and e['date']==due]
        total=sum(e['amount'] for e in bills)
        projected=latest.amount+flow(events,due)-flow(events,latest.as_of) if latest else None
        upcoming.append({'due_date':due,'bills':[{'name':e['name'],'amount':e['amount']} for e in bills],
            'amount':total,'projected_before_payment':projected,'shortfall':max(0,total-projected) if projected is not None else None,
            'assumes_future_allocations':any(e['kind']=='allocation' and latest.as_of<e['date']<=due for e in events) if latest else False})
    risk=any(row['shortfall'] for row in upcoming)
    status='needs_update' if not fresh else 'below_target' if shortfall else 'payment_risk' if risk else 'on_track' if checkpoint else 'scheduled'
    checkpoints=[]
    first_display=checkpoint or next_check
    for offset in range(12):
        check=dated(shift_month(first_display.strftime('%Y-%m'),offset),day)
        allocations=[e for e in events if e['kind']=='allocation' and e['date']==check]
        payments=[e for e in events if e['kind']=='payment' and e['date']<check]
        checkpoints.append({'date':check,'target':target(check),'allocation':sum(e['amount'] for e in allocations),
            'allocations':[{'name':e['name'],'amount':e['amount']} for e in allocations],
            'allocations_to_date':sum(e['amount'] for e in events if e['kind']=='allocation' and e['date']<=check),
            'payments_to_date':sum(e['amount'] for e in payments)})
    result.update(status=status,checkpoint=checkpoint,next_checkpoint=next_check,
        target=target(comparison_date),target_as_of=comparison_date,next_target=target(next_check),
        latest={'amount':latest.amount,'as_of':latest.as_of} if latest else None,
        fresh=fresh,shortfall=shortfall,upcoming=upcoming,checkpoints=checkpoints,
        dismissed=bool(plan.dismissed_until and today<plan.dismissed_until))
    return result
