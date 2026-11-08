"""Bounded transaction summaries for the local advisor; never used by web search."""

from collections import defaultdict
from datetime import date

from sqlalchemy import case, func, select

from .budget import ActualWindow, shift_month
from .category_planning import average
from .classification import normalize_payee
from .models import Account, Transaction
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
                "average_minor": average([v for v in values if v is not None]),
                "sample_count": sum(v is not None for v in values),
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
                "average_minor": average([v for v in values if v is not None]),
                "sample_count": sum(v is not None for v in values),
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


def spending_comparison(db, history):
    """Last two finished months, never forecast changes or card repayments."""
    months = history["months"][-2:]
    if len(months) < 2:
        return None
    previous, current = (row["month"] for row in months)
    statuses = {row["month"]: row["status"] for row in months}
    signed = case(
        (Transaction.kind == "refund", -Transaction.amount), else_=Transaction.amount
    )
    period = func.date_trunc("month", Transaction.date)
    rows = db.execute(
        select(period, Account.name, func.sum(signed))
        .join(Account, Transaction.account_id == Account.id)
        .where(
            Transaction.date >= date.fromisoformat(previous + "-01"),
            Transaction.date < date.fromisoformat(shift_month(current, 1) + "-01"),
            Transaction.kind.in_(["purchase", "fee", "refund"]),
        )
        .group_by(period, Account.name)
    )
    totals = defaultdict(dict)
    for month, name, amount in rows:
        totals[name][month.strftime("%Y-%m")] = int(amount)

    def change(name, values):
        before = None if statuses[previous] == "missing" else values.get(previous, 0)
        after = None if statuses[current] == "missing" else values.get(current, 0)
        return {
            "name": name,
            "previous_minor": before,
            "current_minor": after,
            "change_minor": None if before is None or after is None else after - before,
        }

    accounts = [change(name, values) for name, values in totals.items()]
    accounts.sort(
        key=lambda row: (-abs(row["change_minor"] or 0), row["name"].casefold())
    )
    categories = [
        change(
            row["category"],
            dict(zip((previous, current), row["monthly_net_minor"][-2:])),
        )
        for row in history["categories"]
    ]
    total = change(
        "All recorded spending",
        {
            month: sum(values.get(month, 0) for values in totals.values())
            for month in statuses
        },
    )
    return {
        "previous_month": previous,
        "month": current,
        "previous_status": statuses[previous],
        "current_status": statuses[current],
        "basis": "Recorded purchases and fees minus refunds, by transaction date. Payments and transfers excluded. Latest two finished months ending no later than the selected month; partial months may understate spending. Forecast edits are not spending changes. Account totals are not statement balances or card repayments.",
        "totals": total,
        "accounts": accounts,
        "categories": categories,
    }
