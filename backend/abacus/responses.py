"""Explicit contracts for core read endpoints."""

from datetime import date
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class Response(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(Response, Generic[T]):
    items: list[T]
    next_cursor: str | None


class TransactionOut(Response):
    id: str
    date: date
    description: str
    amount: int
    kind: str
    category_id: str | None
    account_id: str
    import_id: str | None
    provenance: dict[str, str]


class ImportSummaryOut(Response):
    id: str
    filename: str
    status: str
    period: str
    account_id: str
    error: str


class SettingsOut(Response):
    id: int
    currency: str
    model: str
    advisor_enabled: bool
    advisor_memory_enabled: bool
    savings_balance: int | None
    savings_month: str | None
    savings_floor: int


class CategoryOut(Response):
    id: str
    name: str
    monthly_guide: int | None


class AccountOut(Response):
    id: str
    name: str
    stale_alert_enabled: bool
    csv_mapping: dict[str, str | None] | None
    last_information_date: str | None
    days_since_update: int | None
    stale: bool


class ActualOut(Response):
    expenses: int
    status: str
    marked_complete: bool
    transaction_count: int


class ForecastLine(Response):
    id: str
    name: str
    amount: int
    kind: str
    category_id: str | None
    source: str | None = None


class ForecastOut(Response):
    month: str
    income: int
    expenses: int
    remaining: int
    deficit: bool
    lines: list[ForecastLine]
    actual: ActualOut
    actual_deficit: bool


class PlanSummaryOut(Response):
    model_config = ConfigDict(extra="allow")
    id: str
    name: str
    amount: int
    target_date: str
    category_id: str | None
    category: str | None
    recurring_id: str | None
    recurring_name: str | None
    updated_at: str
    paid: bool
    set_aside: int | None
    still_needed: int | None
    monthly_needed: int | None
    contribution_count: int
    status: str


class AnnualExpenseOut(Response):
    id: str
    name: str
    amount: int
    target_date: str
    date_from_bill: bool
    plan_id: str | None


class ProjectionPointOut(Response):
    month: str
    balance: int | None
    plan_payments: int
    cash_expenses: int | None
    income_recorded: bool


class CashProjectionOut(Response):
    months: list[ProjectionPointOut]
    basis: str
    income_complete: bool


class PlanningCategoryOut(Response):
    id: str
    name: str


class PlanningOut(Response):
    today: str
    savings: int | None
    savings_month: str | None
    floor: int
    available: int | None
    set_aside: int | None
    free_savings: int | None
    total_planned: int
    plans: list[PlanSummaryOut]
    categories: list[PlanningCategoryOut]
    annual_expenses: list[AnnualExpenseOut]
    projection: CashProjectionOut | None
    basis: str
