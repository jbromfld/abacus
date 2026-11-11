"""Funding coverage and running cash use the same resolved obligations.

An allocation is a future contribution, never a second expense or a bank receipt.
"""

import calendar
from datetime import date

from .budget import annual_due_month, effective_change, scheduled_amount, shift_month
from .savings import cash_timing

PROJECTION_BASIS = (
    "Conditional running cash forecast from the recorded balance month, before that "
    "month's projected income, spending and savings contributions. Projected contributions "
    "are not included in the recorded balance. Full-month income is assumed; exact-day "
    "cash availability is unknown. Annual bills replace monthly allocations with one "
    "full payment; linked plans count once. Other plans are paid in their target month. "
    "Bill funding gaps use only their own budgeted contributions, without diverting money "
    "from other categories or goals. Months before the balance or beyond 10 years are unknown."
)


def annual_occurrence(item, changes, year, manual_date=None):
    if item.kind != "payable" or item.frequency != "annual":
        return None
    number = int(annual_due_month(item))
    due = date(
        year,
        number,
        min(
            item.due_day or calendar.monthrange(year, number)[1],
            calendar.monthrange(year, number)[1],
        ),
    )
    if not item.due_day and manual_date:
        due = manual_date
    period = due.strftime("%Y-%m")
    if period < item.start_month or (item.end_month and period > item.end_month):
        return None
    change = effective_change(item, changes, period)
    if not change:
        return None
    return dict(amount=change.amount, target_date=due.isoformat())


def funding_coverage(row, source, inputs, start, today):
    """Use this bill's allocation only, including the due month for dates after day 1."""
    first = max(start or today.strftime("%Y-%m"), today.strftime("%Y-%m"))
    target = date.fromisoformat(row["target_date"])
    last = target.strftime("%Y-%m")
    # Each annual cycle owns its contributions; never promise the same monthly
    # allocation to both this year's bill and next year's goal.
    if target.year > 1900:
        first = max(
            first,
            shift_month(
                f"{target.year - 1:04d}-{target.month:02d}", 0 if target.day == 1 else 1
            ),
        )
    contributions = []
    period = first
    while period <= last and target >= today:
        if period != last or target.day > 1:
            amount = (
                scheduled_amount(source, inputs.changes_by_schedule[source.id], period)
                if source.distribute_annual
                else 0
            )
            if amount:
                contributions.append(dict(month=period, amount=amount))
        period = shift_month(period, 1)
    expected = sum(c["amount"] for c in contributions)
    projected = row["set_aside"] + expected if row["set_aside"] is not None else None
    return dict(
        monthly_allocation=scheduled_amount(
            source, inputs.changes_by_schedule[source.id], first
        )
        if source.distribute_annual
        else 0,
        projected_contributions=expected,
        contributions=contributions,
        projected_funding=projected,
        funding_gap=max(0, row["amount"] - projected)
        if projected is not None
        else None,
    )


def cash_projection(inputs, setting, plans, start, months):
    """Return requested months; carry from the saved anchor, never backfill history."""
    opening = setting.savings_month
    last = shift_month(start, months - 1)
    schedules = [
        s for s in inputs.schedules if s.kind == "payable" and s.frequency == "annual"
    ]
    plans = [r for r in plans if r.get("source_active", True)]
    linked = {
        (r["recurring_id"], r["target_date"][:4]) for r in plans if r["recurring_id"]
    }
    points = {}
    balance = setting.savings_balance
    period = opening
    count = 0
    while balance is not None and period and period <= last and count < 120:
        values = inputs.forecast(period)
        expenses, _, _ = cash_timing(
            period, values["expenses"], schedules, inputs.changes
        )
        for source in schedules:
            if (source.id, period[:4]) in linked:
                original, _, _ = cash_timing(
                    period,
                    scheduled_amount(
                        source, inputs.changes_by_schedule[source.id], period
                    ),
                    [source],
                    inputs.changes,
                )
                expenses -= original
        payments = sum(r["amount"] for r in plans if r["target_date"][:7] == period)
        expenses += payments
        balance += values["income"] - expenses
        points[period] = dict(
            month=period,
            balance=balance,
            plan_payments=payments,
            cash_expenses=expenses,
            income_recorded=any(
                line["kind"] == "receivable" for line in values["lines"]
            ),
        )
        period = shift_month(period, 1)
        count += 1
    result = [
        points.get(
            shift_month(start, i),
            dict(
                month=shift_month(start, i),
                balance=None,
                plan_payments=0,
                cash_expenses=None,
                income_recorded=False,
            ),
        )
        for i in range(months)
    ]
    return dict(
        months=result,
        basis=PROJECTION_BASIS,
        income_complete=all(p["income_recorded"] for p in result)
        and all(p["income_recorded"] for p in points.values()),
    )
