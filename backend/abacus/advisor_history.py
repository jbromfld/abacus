"""Bounded transaction summaries for the local advisor; never used by web search."""

from collections import defaultdict
from datetime import date

from sqlalchemy import case, func, select

from .budget import ActualWindow, shift_month
from .classification import normalize_payee
from .models import Transaction
from .payee_matching import load_matching_config

MAX_PAYEES = 20


def spending_history(db, selected_month, today, categories):
    """Compare finished calendar months; preserve missing/incomplete-data evidence."""
    current = today.strftime("%Y-%m")
    end = min(selected_month, shift_month(current, -1))
    first = max("1900-01", shift_month(end, -11))
    months = []
    month = first
    while month <= end:
        months.append(month)
        month = shift_month(month, 1)
    actuals = ActualWindow(db, first, end)
    statuses = {month: actuals.actual(month)["status"] for month in months}
    names = {category.id: category.name for category in categories}

    def series(totals):
        return [
            None if statuses[month] == "missing" else totals.get(month, 0)
            for month in months
        ]

    def comparisons(values):
        result = []
        for count in (2, 3):
            if len(months) < count:
                continue
            amounts = values[-count:]
            available = all(value is not None for value in amounts)
            result.append(
                {
                    "months": count,
                    "from_month": months[-count],
                    "to_month": end,
                    "first_month_minor": amounts[0],
                    "last_month_minor": amounts[-1],
                    "change_minor": amounts[-1] - amounts[0] if available else None,
                    "partial_month_count": sum(
                        statuses[month] == "partial" for month in months[-count:]
                    ),
                    "missing_month_count": sum(
                        statuses[month] == "missing" for month in months[-count:]
                    ),
                }
            )
        return result

    category_rows = []
    for category_id in sorted(names, key=names.get):
        values = series(
            {
                month: actuals.totals.get(month, {}).get(category_id, 0)
                for month in months
            }
        )
        category_rows.append(
            {
                "category": names[category_id],
                "monthly_net_minor": values,
                "comparisons": comparisons(values),
            }
        )

    period = func.date_trunc("month", Transaction.date)
    signed = case(
        (Transaction.kind == "refund", -Transaction.amount), else_=Transaction.amount
    )
    # Aggregate in PostgreSQL before normalizing variants. Never read card IDs,
    # import provenance, source statements, or individual transaction identities.
    rows = db.execute(
        select(
            period, Transaction.description, Transaction.category_id, func.sum(signed)
        )
        .where(
            Transaction.date >= date.fromisoformat(first + "-01"),
            Transaction.date < date.fromisoformat(shift_month(end, 1) + "-01"),
            Transaction.kind.in_(["purchase", "fee", "refund"]),
        )
        .group_by(period, Transaction.description, Transaction.category_id)
    )
    patterns, _, _ = load_matching_config()
    payees = defaultdict(lambda: defaultdict(int))
    for month, description, category_id, amount in rows:
        name = normalize_payee(description, patterns) or "Unspecified payee"
        payees[(name, category_id)][month.strftime("%Y-%m")] += int(amount)
    payee_rows = []
    for (payee, category_id), totals in payees.items():
        values = series(totals)
        payee_rows.append(
            {
                "payee": payee,
                "category": names.get(category_id, "Uncategorized"),
                "monthly_net_minor": values,
                "comparisons": comparisons(values),
            }
        )

    def rank(row):
        changes = [
            value["change_minor"]
            for value in row["comparisons"]
            if value["change_minor"] is not None
        ]
        return (
            -max([0, *changes]),
            -sum(value or 0 for value in row["monthly_net_minor"][-3:]),
            row["payee"],
            row["category"],
        )

    payee_rows.sort(key=rank)
    return {
        "start_month": first,
        "end_month": end,
        "months": [{"month": month, "status": statuses[month]} for month in months],
        "basis": "Recorded net spending by transaction date. Refunds reduce spending; card payments and transfers are excluded. Changes compare the first and last month in each 2- or 3-month window, not sums. Current/future months are excluded. Missing months are unknown, and partial months can understate spending.",
        "categories": category_rows,
        "payees": payee_rows[:MAX_PAYEES],
        "payee_limit": MAX_PAYEES,
        "additional_payees_omitted": max(0, len(payee_rows) - MAX_PAYEES),
        "payee_selection": "Largest recorded increases over the latest 2/3 months, then latest 3-month net spending. Payee normalization groups store numbers and reference variants; names are transaction labels, not verified merchant identities.",
    }
