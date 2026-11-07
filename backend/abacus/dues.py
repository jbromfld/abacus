"""Contractual bill schedules and explicit confirmations, independent of actuals."""
from collections import defaultdict
from datetime import date, timedelta
import calendar
import re
from sqlalchemy import select
from .models import Recurring, AmountChange, BillPayment, RecurringDebit, Transaction
from .budget import annual_due_month, effective_change, scheduled_amount, shift_month
from .card_alerts import local_today


def automatic_occurrence(item, period):
    return bool(item.ach_enabled and item.frequency == 'monthly' and item.ach_start_month and period >= item.ach_start_month)


def due_configuration(item):
    day = item.due_day or (item.ach_day if item.ach_enabled else None)
    tracking = item.payment_tracking_start
    if tracking is None and item.ach_enabled and item.ach_start_month:
        tracking = date.fromisoformat(item.ach_start_month+'-01')
    return day, tracking


def occurrence(item, changes, period):
    day, tracking = due_configuration(item)
    if item.kind != 'payable' or not day or not tracking:
        return None
    if item.frequency == 'annual':
        if not re.fullmatch(r'\d{4}', period):
            return None
        month = period + '-' + annual_due_month(item)
    else:
        if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', period):
            return None
        month = period
    year, number = map(int, month.split('-'))
    if not 1900 <= year <= 9998:
        return None
    due = date(year, number, min(day, calendar.monthrange(year, number)[1]))
    if month < item.start_month or (item.end_month and month > item.end_month) or due < tracking:
        return None
    change = effective_change(item, changes, month)
    if not change or change.amount <= 0:
        return None
    # Stored amounts are full yearly totals, even for distributed forecasts.
    return {'recurring_id':item.id, 'period':period, 'name':item.name,
            'category_id':item.category_id, 'due_date':due.isoformat(), 'amount':change.amount}


def upcoming_dues(db):
    today = local_today()
    through = today + timedelta(days=30)
    changes = defaultdict(list)
    for change in db.scalars(select(AmountChange)):
        changes[change.recurring_id].append(change)
    payments = {(p.recurring_id,p.period):p for p in db.scalars(select(BillPayment))}
    ach = {(r.recurring_id,r.month):transaction for r,transaction in db.execute(
        select(RecurringDebit,Transaction).join(Transaction,RecurringDebit.transaction_id == Transaction.id))}
    items = db.scalars(select(Recurring).where(Recurring.kind == 'payable').order_by(Recurring.name,Recurring.id)).all()
    by_id = {item.id:item for item in items}

    def decorate(row):
        payment = payments.get((row['recurring_id'],row['period']))
        automatic = automatic_occurrence(by_id[row['recurring_id']],row['period'])
        debit = ach.get((row['recurring_id'],row['period']))
        automatic = automatic or debit is not None
        confirmed = payment is not None and payment.paid_on is not None
        paid = bool(debit or confirmed)
        return {**row, 'amount':debit.amount if debit else payment.amount if confirmed else row['amount'], 'paid':paid,
                'paid_on':debit.date.isoformat() if debit else payment.paid_on.isoformat() if confirmed else None,
                'confirmed_due_date':payment.due_date.isoformat() if confirmed and not debit else None,
                'automatic':automatic, 'paid_source':'ach' if debit else 'manual' if confirmed else None,
                'ach_recorded':debit is not None,
                'status':'paid' if paid else 'automatic' if automatic else 'overdue' if row['due_date'] < today.isoformat() else 'today' if row['due_date'] == today.isoformat() else 'upcoming'}

    monthly, overdue, annual, missing, history = [], [], [], [], []
    for item in items:
        for (recurring_id,period), payment in payments.items():
            if recurring_id == item.id and payment.paid_on:
                if (recurring_id,period) in ach:
                    continue
                history.append({'recurring_id':item.id, 'period':period, 'name':item.name,
                    'category_id':item.category_id, 'due_date':payment.due_date.isoformat(),
                    'amount':payment.amount, 'paid':True, 'paid_on':payment.paid_on.isoformat(),
                    'confirmed_due_date':payment.due_date.isoformat(), 'ach_recorded':False,'status':'paid',
                    'automatic':automatic_occurrence(item,period),'paid_source':'manual'})
        for (recurring_id,period), transaction in ach.items():
            if recurring_id == item.id:
                row = occurrence(item,changes[item.id],period) or {'recurring_id':item.id,'period':period,
                    'name':item.name,'category_id':item.category_id,'due_date':transaction.date.isoformat(),'amount':transaction.amount}
                history.append(decorate(row))
        active = not item.end_month or item.end_month >= today.strftime('%Y-%m')
        day, tracking = due_configuration(item)
        configured = bool(day and tracking)
        if item.frequency == 'annual':
            if not active:
                continue
            budget_month = max(item.start_month,today.strftime('%Y-%m'))
            change = effective_change(item,changes[item.id],budget_month)
            summary = {'recurring_id':item.id,'name':item.name,'category_id':item.category_id,
                       'distribute_annual':item.distribute_annual, 'missing_due_date':False,
                       'allowance':not configured, 'annual_amount':change.amount if change else 0,
                       'monthly_allocation':scheduled_amount(item,changes[item.id],budget_month) if item.distribute_annual else None,
                       'next':None,'overdue':[], 'overdue_count':0}
            if configured:
                first_year = max(int(item.start_month[:4]), tracking.year)
                # Include tracked prior years, but never invent unpaid history.
                for year in range(first_year, today.year+1):
                    row = occurrence(item, changes[item.id], str(year))
                    if row and row['due_date'] < today.isoformat():
                        row = decorate(row)
                        if not row['paid']:
                            summary['overdue'].append(row)
                candidate_year = max(first_year, today.year)
                for year in range(candidate_year, min(candidate_year+2,9999)):
                    row = occurrence(item, changes[item.id], str(year))
                    if row and row['due_date'] >= today.isoformat():
                        summary['next'] = decorate(row)
                        break
                summary['overdue_count'] = len(summary['overdue'])
            annual.append(summary)
            continue
        if not configured:
            continue
        month = max(item.start_month, tracking.strftime('%Y-%m'))
        last = min(through.strftime('%Y-%m'), item.end_month or through.strftime('%Y-%m'))
        while month <= last:
            row = occurrence(item, changes[item.id], month)
            if row:
                row = decorate(row)
                if row['due_date'] < today.isoformat() and not row['paid'] and not row['automatic']:
                    overdue.append(row)
                elif today.isoformat() <= row['due_date'] <= through.isoformat():
                    monthly.append(row)
            if month == last:
                break
            month = shift_month(month, 1)
    order = lambda row:(row['due_date'],row['name'].casefold(),row['recurring_id'])
    return {'today':today.isoformat(), 'through':through.isoformat(),
            'monthly_upcoming':sorted(monthly,key=order), 'monthly_overdue':sorted(overdue,key=order),
            'annual':annual, 'missing_monthly':missing, 'missing_monthly_count':len(missing),
            'paid_history':sorted(history,key=lambda row:(row['paid_on'],row['due_date'],row['name']),reverse=True)}


def due_settings(data, previous=None):
    values = data.model_dump(exclude={'amount'})
    if values['kind'] == 'payable' and values['payment_tracking_start'] is None:
        values['payment_tracking_start'] = previous.payment_tracking_start if previous else None
        if values['payment_tracking_start'] is None and values['due_day']:
            values['payment_tracking_start'] = local_today()
    return values
