"""Expense breakdowns with signed refunds and separate forecast/actual totals."""

import calendar
from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import load_only

from .budget import ActualWindow, ForecastInputs, shift_month
from .models import Account, Category, Transaction


def month_key(day):
    return f"{day.year:04d}-{day.month:02d}"


def month_end(month):
    year, number = map(int, month.split("-"))
    return date(year, number, calendar.monthrange(year, number)[1])


MAX_BREAKDOWN_MONTHS = 120


def expense_breakdown(db, start, end, basis):
    count = (end.year - start.year) * 12 + end.month - start.month + 1
    if count > MAX_BREAKDOWN_MONTHS:
        raise ValueError(
            f"Choose a range of at most {MAX_BREAKDOWN_MONTHS} calendar months (10 years)."
        )
    first, last = month_key(start), month_key(end)
    inputs = ForecastInputs(db) if basis == "forecast" else None
    actuals = ActualWindow(db, first, last) if basis == "actual" else None
    categories = {c.id: c.name for c in db.scalars(select(Category)).all()}
    accounts = {a.id: a.name for a in db.scalars(select(Account)).all()}
    entries = []
    months = []
    current = first
    while current <= last:
        if basis == "forecast":
            for line in inputs.forecast(current)["lines"]:
                if line["kind"] == "payable":
                    entries.append(
                        {
                            "id": line["id"] + ":" + current,
                            "record_id": line["id"],
                            "date": None,
                            "month": current,
                            "description": line["name"],
                            "category_id": line["category_id"],
                            "category_name": categories.get(
                                line["category_id"], "Uncategorized"
                            ),
                            "kind": "recurring",
                            "amount": line["amount"],
                            "signed_amount": line["amount"],
                            "account_name": None,
                        }
                    )
            months.append(
                {"month": current, "status": "forecast", "partial_range": False}
            )
        else:
            state = actuals.actual(current)["status"]
            months.append(
                {
                    "month": current,
                    "status": state,
                    "partial_range": start > date.fromisoformat(current + "-01")
                    or end < month_end(current),
                }
            )
        if current == last:
            break
        current = shift_month(current, 1)
    if basis == "actual":
        rows = db.scalars(
            select(Transaction)
            .options(
                load_only(
                    Transaction.id,
                    Transaction.date,
                    Transaction.description,
                    Transaction.category_id,
                    Transaction.kind,
                    Transaction.amount,
                    Transaction.account_id,
                )
            )
            .where(
                Transaction.date >= start,
                Transaction.date <= end,
                Transaction.kind.in_(["purchase", "fee", "refund"]),
            )
            .order_by(Transaction.date.desc(), Transaction.id)
        ).all()
        entries = [
            {
                "id": r.id,
                "record_id": r.id,
                "date": r.date.isoformat(),
                "month": month_key(r.date),
                "description": r.description,
                "category_id": r.category_id,
                "category_name": categories.get(r.category_id, "Uncategorized"),
                "kind": r.kind,
                "amount": r.amount,
                "signed_amount": -r.amount if r.kind == "refund" else r.amount,
                "account_name": accounts.get(r.account_id),
            }
            for r in rows
        ]
    else:
        entries.sort(key=lambda e: (e["month"], e["description"]), reverse=True)
    grouped = defaultdict(
        lambda: {"charges": 0, "refunds": 0, "net": 0, "entry_count": 0}
    )
    for entry in entries:
        total = grouped[entry["category_id"]]
        total["charges" if entry["signed_amount"] > 0 else "refunds"] += entry["amount"]
        total["net"] += entry["signed_amount"]
        total["entry_count"] += 1
    breakdown = [
        dict(category_id=id, name=categories.get(id, "Uncategorized"), **totals)
        for id, totals in grouped.items()
    ]
    breakdown.sort(key=lambda c: (-abs(c["net"]), c["name"].casefold()))
    charges = sum(c["charges"] for c in breakdown)
    refunds = sum(c["refunds"] for c in breakdown)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "basis": basis,
        "charges": charges,
        "refunds": refunds,
        "net": charges - refunds,
        "entry_count": len(entries),
        "categories": breakdown,
        "entries": entries,
        "months": months,
    }
