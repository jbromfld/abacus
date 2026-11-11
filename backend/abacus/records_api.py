"""Bounded transaction and import history reads."""

import base64
import json
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, load_only

from .budget import shift_month
from .db import session
from .models import RecurringDebit, StatementImport, Transaction
from .responses import ImportSummaryOut, Page, TransactionOut
from .schemas import Month

router = APIRouter()
DB = Annotated[Session, Depends(session)]


def cursor_value(cursor, parse):
    try:
        value, identifier = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        if not isinstance(identifier, str) or len(identifier) > 36:
            raise ValueError()
        return parse(value), identifier
    except Exception:
        raise HTTPException(422, "Invalid page cursor.") from None


def page_cursor(value, identifier):
    return base64.urlsafe_b64encode(
        json.dumps([value.isoformat(), identifier]).encode()
    ).decode()


@router.get("/api/transactions", response_model=Page[TransactionOut])
def transactions(
    db: DB,
    month: Month | None = None,
    q: str = "",
    category_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    cursor: str | None = None,
):
    query = (
        select(Transaction, RecurringDebit.id)
        .outerjoin(RecurringDebit, RecurringDebit.transaction_id == Transaction.id)
        .options(
            load_only(
                Transaction.id,
                Transaction.date,
                Transaction.description,
                Transaction.amount,
                Transaction.kind,
                Transaction.category_id,
                Transaction.account_id,
                Transaction.import_id,
            )
        )
    )
    if month:
        query = query.where(
            Transaction.date >= date.fromisoformat(month + "-01"),
            Transaction.date < date.fromisoformat(shift_month(month, 1) + "-01"),
        )
    if q:
        query = query.where(Transaction.description.icontains(q, autoescape=True))
    if category_id:
        query = query.where(Transaction.category_id == category_id)
    if cursor:
        day, identifier = cursor_value(cursor, date.fromisoformat)
        query = query.where(
            or_(
                Transaction.date < day,
                and_(Transaction.date == day, Transaction.id > identifier),
            )
        )
    rows = db.execute(
        query.order_by(Transaction.date.desc(), Transaction.id).limit(limit + 1)
    ).all()
    more = len(rows) > limit
    rows = rows[:limit]
    # Large statement provenance is available only from the detail endpoint.
    items = [
        dict(
            id=r.id,
            date=r.date,
            description=r.description,
            amount=r.amount,
            kind=r.kind,
            category_id=r.category_id,
            account_id=r.account_id,
            import_id=r.import_id,
            provenance={"type": "scheduled_ach"} if debit_id else {},
        )
        for r, debit_id in rows
    ]

    return {
        "items": items,
        "next_cursor": page_cursor(rows[-1][0].date, rows[-1][0].id) if more else None,
    }


@router.get("/api/imports", response_model=Page[ImportSummaryOut])
def imports(
    db: DB, limit: int = Query(default=100, ge=1, le=200), cursor: str | None = None
):
    query = select(StatementImport).options(
        load_only(
            StatementImport.id,
            StatementImport.filename,
            StatementImport.status,
            StatementImport.period,
            StatementImport.account_id,
            StatementImport.error,
            StatementImport.created_at,
        )
    )
    if cursor:
        created, identifier = cursor_value(cursor, datetime.fromisoformat)
        query = query.where(
            or_(
                StatementImport.created_at < created,
                and_(
                    StatementImport.created_at == created,
                    StatementImport.id > identifier,
                ),
            )
        )
    rows = db.scalars(
        query.order_by(StatementImport.created_at.desc(), StatementImport.id).limit(
            limit + 1
        )
    ).all()
    more = len(rows) > limit
    rows = rows[:limit]
    return {
        "items": [
            dict(
                id=j.id,
                filename=j.filename,
                status=j.status,
                period=j.period,
                account_id=j.account_id,
                error=j.error,
            )
            for j in rows
        ],
        "next_cursor": page_cursor(rows[-1].created_at, rows[-1].id) if more else None,
    }
