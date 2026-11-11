"""Explicit yearly estimates, optionally allocated to calendar-month forecasts."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import session
from .models import AnnualIncome
from .schemas import Money, Name

router = APIRouter(prefix="/api/annual-income")
DB = Annotated[Session, Depends(session)]


class AnnualIncomeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    year: int = Field(ge=1900, le=9998, strict=True)
    name: Name
    amount: Money
    included: bool = False


def monthly_shares(amount):
    share, remainder = divmod(amount, 12)
    return [share + (number < remainder) for number in range(12)]


def allocated_income(item, month):
    if not item.included or int(month[:4]) != item.year:
        return 0
    return monthly_shares(item.amount)[int(month[5:]) - 1]


def source_summary(item):
    return dict(
        id=item.id,
        year=item.year,
        name=item.name,
        amount=item.amount,
        included=item.included,
        monthly_amounts=monthly_shares(item.amount),
    )


@router.get("")
def summary(db: DB, year: int = Query(ge=1900, le=9998)):
    items = db.scalars(
        select(AnnualIncome)
        .where(AnnualIncome.year == year)
        .order_by(AnnualIncome.name, AnnualIncome.id)
    ).all()
    return dict(
        year=year,
        total=sum(item.amount for item in items),
        included_total=sum(item.amount for item in items if item.included),
        monthly_amounts=[
            sum(allocated_income(item, f"{year:04d}-{number:02d}") for item in items)
            for number in range(1, 13)
        ],
        sources=[source_summary(item) for item in items],
    )


@router.post("", status_code=201)
def create(data: AnnualIncomeIn, db: DB):
    item = AnnualIncome(**data.model_dump())
    db.add(item)
    db.commit()
    return source_summary(item)


def find(db, id):
    item = db.get(AnnualIncome, id)
    if item is None:
        raise HTTPException(404, "Annual income estimate not found.")
    return item


@router.put("/{id}")
def edit(id: str, data: AnnualIncomeIn, db: DB):
    item = find(db, id)
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    db.commit()
    return source_summary(item)


@router.delete("/{id}")
def remove(id: str, db: DB):
    db.delete(find(db, id))
    db.commit()
    return {"ok": True}
