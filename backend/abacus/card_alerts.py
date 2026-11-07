"""Per-card freshness from dated records, independent of budget navigation."""
import calendar
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select, func
from .config import local_config
from .models import Account, Transaction, StatementImport


def local_today():
    return datetime.now(ZoneInfo(local_config().get('APP_TIMEZONE', 'America/Detroit'))).date()


def account_information(db):
    today = local_today()
    zone = ZoneInfo(local_config().get('APP_TIMEZONE', 'America/Detroit'))
    latest = dict(db.execute(select(Transaction.account_id, func.max(Transaction.date)).where(
        Transaction.date <= today,
    ).group_by(Transaction.account_id)).all())
    for account_id, period, uploaded in db.execute(select(
        StatementImport.account_id, StatementImport.period, StatementImport.created_at,
    ).where(StatementImport.status == 'committed')):
        # A reviewed statement establishes its cycle's information even if it
        # has no new purchases. Uploading an old cycle must not look current.
        if uploaded.tzinfo is None:
            uploaded = uploaded.replace(tzinfo=timezone.utc)
        uploaded_day = uploaded.astimezone(zone).date()
        first = date.fromisoformat(period+'-01')
        if first > min(today, uploaded_day):
            continue  # A future statement period cannot establish current coverage.
        last = date(first.year, first.month, calendar.monthrange(first.year, first.month)[1])
        through = min(last, uploaded_day, today)
        if account_id not in latest or through > latest[account_id]:
            latest[account_id] = through
    results = []
    for account in db.scalars(select(Account).order_by(Account.name)).all():
        through = latest.get(account.id)
        days = (today-through).days if through else None
        results.append({
            'id':account.id, 'name':account.name,
            'stale_alert_enabled':account.stale_alert_enabled, 'csv_mapping':account.csv_mapping,
            'last_information_date':through.isoformat() if through else None,
            'days_since_update':days,
            'stale':account.stale_alert_enabled and (days is None or days > 30),
        })
    return results
