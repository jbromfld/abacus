"""Record assumed ACH debits locally, once per opted-in monthly schedule/month."""
import calendar
from datetime import date
from sqlalchemy import select
from .models import Recurring, RecurringDebit, Transaction, AmountChange
from .budget import scheduled_amount, shift_month


def today_local():
    return date.today()


def record_due(db, today=None):
    today = today or today_local()
    current = today.strftime('%Y-%m')
    count = 0
    # Serialize concurrent scheduler/API passes per schedule. A unique occurrence
    # constraint is a second guard. Never modify a previously recorded debit.
    schedules = db.scalars(select(Recurring).where(Recurring.ach_enabled == True)
                           .order_by(Recurring.id).with_for_update()).all()
    for item in schedules:
        if item.kind != 'payable' or item.frequency != 'monthly':
            continue
        month = max(item.start_month, item.ach_start_month)
        last = min(current, item.end_month or current)
        changes = db.scalars(select(AmountChange).where(AmountChange.recurring_id == item.id)).all()
        recorded = set(db.scalars(select(RecurringDebit.month).where(RecurringDebit.recurring_id == item.id)))
        while month <= last:
            year, number = map(int, month.split('-'))
            due = date(year, number, min(item.ach_day, calendar.monthrange(year, number)[1]))
            amount = scheduled_amount(item, changes, month)
            if due <= today and amount and month not in recorded:
                transaction = Transaction(date=due, description=item.name, amount=amount,
                    kind='purchase', category_id=item.category_id, account_id=item.ach_account_id,
                    provenance={'type':'scheduled_ach', 'recurring_id':item.id, 'month':month,
                                'note':'Automatically recorded from schedule; confirm against bank records.'})
                db.add(transaction)
                db.flush()
                db.add(RecurringDebit(recurring_id=item.id, month=month, transaction_id=transaction.id))
                count += 1
            month = shift_month(month, 1)
    db.commit()
    return count
