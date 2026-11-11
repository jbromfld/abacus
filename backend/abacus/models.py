from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def uid():
    return str(uuid4())


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    monthly_guide: Mapped[int | None] = mapped_column(BigInteger)


class Settings(Base):
    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    model: Mapped[str] = mapped_column(String(200), default="")
    advisor_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    advisor_memory_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    savings_balance: Mapped[int | None] = mapped_column(BigInteger)
    savings_month: Mapped[str | None] = mapped_column(String(7))
    savings_floor: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0"
    )


class AlertDismissal(Base):
    __tablename__ = "alert_dismissals"
    month: Mapped[str] = mapped_column(String(7), primary_key=True)
    kind: Mapped[str] = mapped_column(String(24), primary_key=True)
    dismissed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    __table_args__ = (
        CheckConstraint(
            "kind IN ('forecast_deficit','actual_deficit')", name="alert_dismissal_kind"
        ),
    )


class PlanCategory(Base):
    __tablename__ = "plan_categories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(80), unique=True)


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160))
    amount: Mapped[int] = mapped_column(BigInteger)
    target_date: Mapped[date] = mapped_column(Date, index=True)
    category_id: Mapped[str | None] = mapped_column(
        ForeignKey("plan_categories.id", ondelete="SET NULL")
    )
    recurring_id: Mapped[str | None] = mapped_column(
        ForeignKey("recurring.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    __table_args__ = (CheckConstraint("amount > 0 AND amount <= 9000000000000"),)


class AnnualIncome(Base):
    __tablename__ = "annual_income"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    year: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(160))
    amount: Mapped[int] = mapped_column(BigInteger)
    included: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    __table_args__ = (
        CheckConstraint("year BETWEEN 1900 AND 9998"),
        CheckConstraint("amount > 0 AND amount <= 9000000000000"),
    )


class Recurring(Base):
    __tablename__ = "recurring"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(12))
    frequency: Mapped[str] = mapped_column(String(10))
    distribute_annual: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"))
    start_month: Mapped[str] = mapped_column(String(7))
    end_month: Mapped[str | None] = mapped_column(String(7))
    due_day: Mapped[int | None] = mapped_column(Integer)
    due_month: Mapped[int | None] = mapped_column(Integer)
    payment_tracking_start: Mapped[date | None] = mapped_column(Date)
    ach_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    ach_day: Mapped[int | None] = mapped_column(Integer)
    ach_start_month: Mapped[str | None] = mapped_column(String(7))
    ach_account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"))
    __table_args__ = (
        CheckConstraint("kind IN ('payable','receivable')"),
        CheckConstraint("frequency IN ('monthly','annual')"),
        CheckConstraint("kind != 'payable' OR category_id IS NOT NULL"),
        CheckConstraint("due_day BETWEEN 1 AND 31", name="recurring_due_day_range"),
        CheckConstraint("due_month BETWEEN 1 AND 12", name="recurring_due_month_range"),
    )


class AmountChange(Base):
    __tablename__ = "amount_changes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    recurring_id: Mapped[str] = mapped_column(
        ForeignKey("recurring.id", ondelete="CASCADE")
    )
    month: Mapped[str] = mapped_column(String(7))
    amount: Mapped[int] = mapped_column(BigInteger)
    override: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        UniqueConstraint("recurring_id", "month", "override"),
        CheckConstraint("amount > 0"),
    )


class BillPayment(Base):
    __tablename__ = "bill_payments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    recurring_id: Mapped[str] = mapped_column(
        ForeignKey("recurring.id", ondelete="CASCADE")
    )
    period: Mapped[str] = mapped_column(String(7))
    due_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[int] = mapped_column(BigInteger)
    paid_on: Mapped[date | None] = mapped_column(Date)
    __table_args__ = (
        UniqueConstraint("recurring_id", "period"),
        CheckConstraint("amount > 0"),
    )


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    stale_alert_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    csv_mapping: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class StatementImport(Base):
    __tablename__ = "imports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    period: Mapped[str] = mapped_column(String(7))
    file_hash: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="prepared")
    processing_token: Mapped[str | None] = mapped_column(String(36))
    error: Mapped[str] = mapped_column(String(2000), default="")
    source: Mapped[dict] = mapped_column(JSON)
    rows: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    __table_args__ = (UniqueConstraint("account_id", "file_hash"),)


class ImportPage(Base):
    __tablename__ = "import_pages"
    import_id: Mapped[str] = mapped_column(
        ForeignKey("imports.id", ondelete="CASCADE"), primary_key=True
    )
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    __table_args__ = (CheckConstraint("number > 0"),)


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    date: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str] = mapped_column(String(500))
    amount: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(16))
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    import_id: Mapped[str | None] = mapped_column(ForeignKey("imports.id"), index=True)
    csv_fingerprint: Mapped[str | None] = mapped_column(String(64))
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        Index("ix_transactions_account_date", "account_id", "date"),
        Index("ix_transactions_account_csv", "account_id", "csv_fingerprint"),
        CheckConstraint("amount > 0"),
        CheckConstraint("kind IN ('purchase','refund','fee','payment','transfer')"),
        CheckConstraint("kind IN ('payment','transfer') OR category_id IS NOT NULL"),
    )


class MonthStatus(Base):
    __tablename__ = "month_status"
    month: Mapped[str] = mapped_column(String(7), primary_key=True)
    complete: Mapped[bool] = mapped_column(Boolean, default=False)


class RecurringDebit(Base):
    """Keep occurrence identity even if its actual transaction is deleted."""

    __tablename__ = "recurring_debits"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    recurring_id: Mapped[str] = mapped_column(
        ForeignKey("recurring.id", ondelete="CASCADE")
    )
    month: Mapped[str] = mapped_column(String(7))
    transaction_id: Mapped[str | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL")
    )
    __table_args__ = (UniqueConstraint("recurring_id", "month"),)


class PayeeGroup(Base):
    __tablename__ = "payee_groups"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(16))
    __table_args__ = (CheckConstraint("kind IN ('purchase','refund','fee')"),)


class PayeeReview(Base):
    __tablename__ = "payee_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    snapshot: Mapped[list] = mapped_column(JSON, default=list)
    suggestions: Mapped[list] = mapped_column(JSON, default=list)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(String(500), default="")
    result: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class PayeeRule(Base):
    __tablename__ = "payee_rules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    payee: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(16))
    group_id: Mapped[str | None] = mapped_column(
        ForeignKey("payee_groups.id", ondelete="SET NULL"), index=True
    )
    category_id: Mapped[str] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE")
    )
    __table_args__ = (
        UniqueConstraint("payee", "kind"),
        CheckConstraint("kind IN ('purchase','refund','fee')"),
    )


@event.listens_for(Transaction, "before_insert")
@event.listens_for(Transaction, "before_update")
def update_csv_fingerprint(mapper, connection, target):
    from .source_keys import csv_fields_key, fingerprint

    key = csv_fields_key((target.provenance or {}).get("source"))
    target.csv_fingerprint = fingerprint(key) if key is not None else None
