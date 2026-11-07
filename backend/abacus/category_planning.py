"""Rolling recorded spending means and informational, non-expense guides."""
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import select
from .budget import shift_month
from .models import Category, Transaction, MonthStatus
from .card_alerts import local_today


def average(values):
    return int((Decimal(sum(values))/len(values)).quantize(Decimal('1'),rounding=ROUND_HALF_UP)) if values else None


def category_averages(db, end, category_ids=None):
    months = [shift_month(end,n) for n in range(-11,1)]
    if int(months[0].split('-')[0]) < 1900:
        raise ValueError('Choose an ending month of December 1900 or later for a full 12-month window.')
    start = date.fromisoformat(months[0]+'-01')
    # Exclusive end boundary supports December 9998 without constructing year 10000.
    finish = date.fromisoformat(shift_month(end,1)+'-01')
    rows = db.scalars(select(Transaction).where(Transaction.date>=start,Transaction.date<finish)).all()
    recorded = {row.date.strftime('%Y-%m') for row in rows}
    completed = {row.month for row in db.scalars(select(MonthStatus).where(MonthStatus.complete == True))}
    current = local_today().strftime('%Y-%m')
    eligible = [month for month in months if month<current and (month in recorded or month in completed)]
    partial = [month for month in eligible if month not in completed]
    totals = defaultdict(lambda:defaultdict(int))
    for row in rows:
        amount = -row.amount if row.kind=='refund' else row.amount if row.kind in ('purchase','fee') else 0
        if amount and row.category_id:
            totals[row.date.strftime('%Y-%m')][row.category_id] += amount
    categories = db.scalars(select(Category).order_by(Category.name)).all()
    stats = []
    for category in categories:
        mean = average([totals[month][category.id] for month in eligible])
        stats.append({'id':category.id,'name':category.name,'average':mean,
                      'suggested_guide':max(0,mean) if mean is not None else None,
                      'monthly_guide':category.monthly_guide,'sample_count':len(eligible),
                      'partial_month_count':len(partial)})
    selected = set(category_ids) if category_ids else {category.id for category in categories}
    overall = average([sum(amount for id,amount in totals[month].items() if id in selected) for month in eligible])
    return {'window_start':months[0],'window_end':end,'sample_count':len(eligible),
            'partial_month_count':len(partial),'included_months':eligible,
            'excluded_months':[month for month in months if month not in eligible],
            'average':overall,'categories':stats,
            'basis':'Recorded past months only, including incomplete months with a warning. Missing/current/future months are excluded; explicitly complete zero months count. Refunds reduce spending; payments and transfers are excluded. Category guides are informational and never added to expenses.'}
