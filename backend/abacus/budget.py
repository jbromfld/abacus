from collections import defaultdict
from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.orm import load_only

from .annual_income import allocated_income
from .clock import local_today
from .models import (
    AmountChange,
    AnnualIncome,
    MonthStatus,
    Purchase,
    Recurring,
    Transaction,
)


def shift_month(month, delta):
    year, m = map(int, month.split("-"))
    total = year * 12 + m - 1 + delta
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def annual_due_month(item):
    return (
        f"{getattr(item, 'due_month', None) or int(item.start_month[5:]):02d}"
        if item.kind == "payable"
        else item.start_month[5:]
    )


def effective_change(item, changes, month):
    applicable = [
        c
        for c in changes
        if c.recurring_id == item.id
        and ((c.override and c.month == month) or (not c.override and c.month <= month))
    ]
    overrides = [c for c in applicable if c.override]
    defaults = [c for c in applicable if not c.override]
    return (
        overrides[0]
        if overrides
        else max(defaults, key=lambda c: c.month)
        if defaults
        else None
    )


def scheduled_amount(item, changes, month):
    if month < item.start_month or (item.end_month and month > item.end_month):
        return 0
    distribute = (
        item.frequency == "annual" and item.kind == "payable" and item.distribute_annual
    )
    if (
        item.frequency == "annual"
        and not distribute
        and month[5:] != annual_due_month(item)
    ):
        return 0
    change = effective_change(item, changes, month)
    if change is None:
        return 0
    if not distribute:
        return change.amount
    # Stored amounts remain annual totals. Spread integer minor units exactly
    # over a 12-month cycle anchored to this rate's effective month. An annual
    # rate override affects only the selected month's allocation.
    year, number = map(int, month.split("-"))
    anchor_year, anchor_number = map(int, change.month.split("-"))
    offset = ((year - anchor_year) * 12 + number - anchor_number) % 12
    share, remainder = divmod(change.amount, 12)
    return share + (1 if offset < remainder else 0)


def forecast(db, month, category_ids=None, preview=None, inputs=None):
    return (inputs or ForecastInputs(db)).forecast(month, category_ids, preview)


def actual(db, month, category_ids=None, window=None):
    return (window or ActualWindow(db, month, month)).actual(month, category_ids)


class ForecastInputs:
    """Immutable request-scoped inputs reused for every requested forecast month."""

    def __init__(self, db):
        self.changes = db.scalars(select(AmountChange)).all()
        self.schedules = db.scalars(select(Recurring)).all()
        self.annual_income = db.scalars(select(AnnualIncome)).all()
        self.purchases = db.scalars(
            select(Purchase).options(
                load_only(
                    Purchase.id,
                    Purchase.name,
                    Purchase.amount,
                    Purchase.month,
                    Purchase.category_id,
                    Purchase.included,
                )
            )
        ).all()
        self.changes_by_schedule = defaultdict(list)
        self.purchases_by_month = defaultdict(list)
        for item in self.changes:
            self.changes_by_schedule[item.recurring_id].append(item)
        for item in self.purchases:
            self.purchases_by_month[item.month].append(item)

    def forecast(self, month, category_ids=None, preview=None):
        lines = []
        for item in self.schedules:
            amount = scheduled_amount(item, self.changes_by_schedule[item.id], month)
            if amount and (category_ids is None or item.category_id in category_ids):
                lines.append(
                    dict(
                        id=item.id,
                        name=item.name,
                        amount=amount,
                        kind=item.kind,
                        category_id=item.category_id,
                    )
                )
        if category_ids is None:
            for item in self.annual_income:
                if amount := allocated_income(item, month):
                    lines.append(
                        dict(
                            id=item.id,
                            name=item.name,
                            amount=amount,
                            kind="receivable",
                            category_id=None,
                            source="annual_income_estimate",
                        )
                    )
        for item in self.purchases_by_month[month]:
            if (item.included or item.id == preview) and (
                category_ids is None or item.category_id in category_ids
            ):
                lines.append(
                    dict(
                        id=item.id,
                        name=item.name,
                        amount=item.amount,
                        kind="payable",
                        category_id=item.category_id,
                    )
                )
        income = sum(line["amount"] for line in lines if line["kind"] == "receivable")
        expenses = sum(line["amount"] for line in lines if line["kind"] == "payable")
        return dict(
            month=month,
            income=income,
            expenses=expenses,
            remaining=income - expenses,
            deficit=expenses > income,
            lines=lines,
        )


class ActualWindow:
    """Two bounded aggregate reads; no descriptions/provenance loaded for totals."""

    def __init__(self, db, first, last):
        start = date.fromisoformat(first + "-01")
        finish = date.fromisoformat(shift_month(last, 1) + "-01")
        month = func.date_trunc("month", Transaction.date)
        signed = case(
            (Transaction.kind == "refund", -Transaction.amount),
            (Transaction.kind.in_(["purchase", "fee"]), Transaction.amount),
            else_=0,
        )
        self.totals = defaultdict(dict)
        self.counts = defaultdict(dict)
        for period, category, spending, count in db.execute(
            select(month, Transaction.category_id, func.sum(signed), func.count())
            .where(Transaction.date >= start, Transaction.date < finish)
            .group_by(month, Transaction.category_id)
        ):
            key = period.strftime("%Y-%m")
            self.totals[key][category] = int(spending)
            self.counts[key][category] = count
        self.completed = {
            row.month
            for row in db.scalars(
                select(MonthStatus).where(
                    MonthStatus.month >= first,
                    MonthStatus.month <= last,
                    MonthStatus.complete == True,
                )
            )
        }
        self.current = local_today().strftime("%Y-%m")

    def actual(self, month, category_ids=None):
        recorded = month in self.counts
        status = (
            "partial"
            if month >= self.current
            else "complete"
            if month in self.completed
            else "partial"
            if recorded
            else "missing"
        )
        totals = self.totals.get(month, {})
        counts = self.counts.get(month, {})
        return dict(
            expenses=sum(
                value
                for key, value in totals.items()
                if category_ids is None or key in category_ids
            ),
            status=status,
            marked_complete=month in self.completed,
            transaction_count=sum(
                value
                for key, value in counts.items()
                if category_ids is None or key in category_ids
            ),
        )
