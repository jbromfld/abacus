from datetime import date, datetime, timezone
from uuid import uuid4
from sqlalchemy import String, Integer, BigInteger, ForeignKey, Date, DateTime, JSON, Boolean, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def uid():
    return str(uuid4())

class Category(Base):
    __tablename__ = "categories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(80), unique=True)

class Settings(Base):
    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    model: Mapped[str] = mapped_column(String(200), default="")
    advisor_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

class Recurring(Base):
    __tablename__ = "recurring"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(12))
    frequency: Mapped[str] = mapped_column(String(10))
    distribute_annual: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"))
    start_month: Mapped[str] = mapped_column(String(7))
    end_month: Mapped[str | None] = mapped_column(String(7))
    ach_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    ach_day: Mapped[int | None] = mapped_column(Integer)
    ach_start_month: Mapped[str | None] = mapped_column(String(7))
    ach_account_id: Mapped[str | None] = mapped_column(ForeignKey('accounts.id'))
    __table_args__ = (CheckConstraint("kind IN ('payable','receivable')"), CheckConstraint("frequency IN ('monthly','annual')"), CheckConstraint("kind != 'payable' OR category_id IS NOT NULL"))

class AmountChange(Base):
    __tablename__ = "amount_changes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    recurring_id: Mapped[str] = mapped_column(ForeignKey("recurring.id", ondelete="CASCADE"))
    month: Mapped[str] = mapped_column(String(7))
    amount: Mapped[int] = mapped_column(BigInteger)
    override: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("recurring_id", "month", "override"), CheckConstraint("amount > 0"))

class Purchase(Base):
    __tablename__ = "purchases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160))
    amount: Mapped[int] = mapped_column(BigInteger)
    month: Mapped[str] = mapped_column(String(7))
    category_id: Mapped[str] = mapped_column(ForeignKey("categories.id"))
    notes: Mapped[str] = mapped_column(String(2000), default="")
    included: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (CheckConstraint("amount > 0"),)

class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    stale_alert_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    csv_mapping: Mapped[dict | None] = mapped_column(JSON, nullable=True)

class StatementImport(Base):
    __tablename__ = "imports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    period: Mapped[str] = mapped_column(String(7))
    file_hash: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="prepared")
    error: Mapped[str] = mapped_column(String(2000), default="")
    source: Mapped[dict] = mapped_column(JSON)
    rows: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("account_id", "file_hash"),)

class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    date: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str] = mapped_column(String(500))
    amount: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(16))
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    import_id: Mapped[str | None] = mapped_column(ForeignKey("imports.id"))
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (CheckConstraint("amount > 0"), CheckConstraint("kind IN ('purchase','refund','fee','payment','transfer')"), CheckConstraint("kind IN ('payment','transfer') OR category_id IS NOT NULL"))

class MonthStatus(Base):
    __tablename__ = "month_status"
    month: Mapped[str] = mapped_column(String(7), primary_key=True)
    complete: Mapped[bool] = mapped_column(Boolean, default=False)

class RecurringDebit(Base):
    """Keep occurrence identity even if its actual transaction is deleted."""
    __tablename__ = 'recurring_debits'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    recurring_id: Mapped[str] = mapped_column(ForeignKey('recurring.id', ondelete='CASCADE'))
    month: Mapped[str] = mapped_column(String(7))
    transaction_id: Mapped[str | None] = mapped_column(ForeignKey('transactions.id', ondelete='SET NULL'))
    __table_args__ = (UniqueConstraint('recurring_id', 'month'),)

class PayeeRule(Base):
    __tablename__ = 'payee_rules'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    payee: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(16))
    category_id: Mapped[str] = mapped_column(ForeignKey('categories.id', ondelete='CASCADE'))
    __table_args__ = (UniqueConstraint('payee', 'kind'), CheckConstraint("kind IN ('purchase','refund','fee')"))
