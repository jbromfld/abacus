from datetime import date
from sqlalchemy import select
from .models import Recurring, AmountChange, Purchase, Transaction, MonthStatus


def shift_month(month, delta):
    year, m = map(int, month.split('-'))
    total = year * 12 + m - 1 + delta
    return f'{total // 12:04d}-{total % 12 + 1:02d}'


def annual_due_month(item):
    return f'{getattr(item, "due_month", None) or int(item.start_month[5:]):02d}' if item.kind == 'payable' else item.start_month[5:]


def effective_change(item, changes, month):
    applicable = [c for c in changes if c.recurring_id == item.id and ((c.override and c.month == month) or (not c.override and c.month <= month))]
    overrides = [c for c in applicable if c.override]
    defaults = [c for c in applicable if not c.override]
    return overrides[0] if overrides else max(defaults, key=lambda c: c.month) if defaults else None


def scheduled_amount(item, changes, month):
    if month < item.start_month or (item.end_month and month > item.end_month):
        return 0
    distribute = item.frequency == 'annual' and item.kind == 'payable' and item.distribute_annual
    if item.frequency == 'annual' and not distribute and month[5:] != annual_due_month(item):
        return 0
    change = effective_change(item, changes, month)
    if change is None:
        return 0
    if not distribute:
        return change.amount
    # Stored amounts remain annual totals. Spread integer minor units exactly
    # over a 12-month cycle anchored to this rate's effective month. An annual
    # rate override affects only the selected month's allocation.
    year, number = map(int, month.split('-'))
    anchor_year, anchor_number = map(int, change.month.split('-'))
    offset = ((year-anchor_year)*12 + number-anchor_number) % 12
    share, remainder = divmod(change.amount, 12)
    return share + (1 if offset < remainder else 0)


def forecast(db, month, category_ids=None, preview=None):
    changes = db.scalars(select(AmountChange)).all()
    lines = []
    for item in db.scalars(select(Recurring)).all():
        amount = scheduled_amount(item, changes, month)
        if amount and (category_ids is None or item.category_id in category_ids):
            lines.append(dict(id=item.id, name=item.name, amount=amount, kind=item.kind, category_id=item.category_id))
    for p in db.scalars(select(Purchase).where(Purchase.month == month)).all():
        if (p.included or p.id == preview) and (category_ids is None or p.category_id in category_ids):
            lines.append(dict(id=p.id, name=p.name, amount=p.amount, kind='payable', category_id=p.category_id))
    income = sum(x['amount'] for x in lines if x['kind'] == 'receivable')
    expenses = sum(x['amount'] for x in lines if x['kind'] == 'payable')
    return dict(month=month, income=income, expenses=expenses, remaining=income-expenses, deficit=expenses > income, lines=lines)


def actual(db, month, category_ids=None):
    start, end = date.fromisoformat(month + '-01'), date.fromisoformat(shift_month(month, 1) + '-01')
    rows = db.scalars(select(Transaction).where(Transaction.date >= start, Transaction.date < end)).all()
    filtered = [r for r in rows if category_ids is None or r.category_id in category_ids]
    expenses = sum(-r.amount if r.kind == 'refund' else r.amount if r.kind in ('purchase', 'fee') else 0 for r in filtered)
    status = db.get(MonthStatus, month)
    current = date.today().strftime('%Y-%m')
    state = 'partial' if month >= current else 'complete' if status and status.complete else 'partial' if rows else 'missing'
    return dict(expenses=expenses, status=state, marked_complete=bool(status and status.complete), transaction_count=len(filtered))
