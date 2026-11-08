import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.orm import load_only

from .ach import record_due
from .advisor import answer_question, budget_context
from .budget import (
    ActualWindow,
    ForecastInputs,
    actual,
    annual_due_month,
    forecast,
    shift_month,
)
from .card_alerts import account_information
from .category_planning import category_averages
from .classification import apply_payee_rules, learn_labels
from .csv_profiles import apply_saved_mapping
from .db import Session, read_only_session, session
from .dues import (
    automatic_occurrence,
    due_settings,
    local_today,
    occurrence,
    upcoming_dues,
)
from .expenses import expense_breakdown, month_end, month_key
from .imports import csv_rows, executor, prepare_file, process_import, validate_rows
from .local_model import available_models
from .models import (
    Account,
    AmountChange,
    BillEstimate,
    BillPayment,
    Category,
    MonthStatus,
    PayeeRule,
    Purchase,
    Recurring,
    RecurringDebit,
    ReservePlan,
    SavingsObservation,
    Settings,
    StatementImport,
    Transaction,
    uid,
)
from .provenance import compact_pdf_rows, expanded_sources
from .research import confirmation_for, plan_research, research_status
from .reserves import observe, reserve_check, schedule_snapshot
from .savings import project_savings, savings_settings
from .schemas import (
    AccountIn,
    AdvisorIn,
    BillEstimateIn,
    BillPaymentIn,
    CardMonitoringIn,
    CategoryGuideIn,
    CategoryIn,
    ChangeIn,
    CommitIn,
    CompleteIn,
    MappingIn,
    Month,
    PayeeRuleIn,
    ProcessImportIn,
    PurchaseIn,
    RecurringCreate,
    RecurringIn,
    ResearchPreviewIn,
    ReservePlanIn,
    SavingsIn,
    SavingsObservationIn,
    SavingsProjectionIn,
    SettingsIn,
    TransactionIn,
)


@asynccontextmanager
async def lifespan(app):
    with Session() as db:
        db.execute(
            update(StatementImport)
            .where(StatementImport.status == "processing")
            .values(
                status="interrupted",
                error="Processing stopped when the app restarted. Retry this import.",
            )
        )
        db.commit()
    await asyncio.to_thread(record_due_in_session)
    task = asyncio.create_task(ach_scheduler())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def record_due_in_session():
    with Session() as db:
        return record_due(db)


async def ach_scheduler():
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(record_due_in_session)
        except Exception:
            logging.getLogger(__name__).exception(
                "ACH recording failed; will retry next minute"
            )


app = FastAPI(title="Abacus", lifespan=lifespan)
DB = Annotated[DBSession, Depends(session)]
ReadOnlyDB = Annotated[DBSession, Depends(read_only_session)]


@app.middleware("http")
async def local_requests(request: Request, call_next):
    if request.url.hostname not in ("localhost", "127.0.0.1", "::1", "testserver"):
        return JSONResponse({"detail": "Abacus is local-only."}, 403)
    origin = request.headers.get("origin")
    if (
        request.method not in ("GET", "HEAD", "OPTIONS")
        and origin
        and origin
        not in (
            str(request.base_url).rstrip("/"),
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        )
    ):
        return JSONResponse({"detail": "Cross-origin writes are disabled."}, 403)
    return await call_next(request)


@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    return JSONResponse(
        {
            "detail": "This name/file already exists, or this record is still referenced. Update its references first."
        },
        409,
    )


def get(db, model, id):
    item = db.get(model, id)
    if item is None:
        raise HTTPException(404, "Record not found.")
    return item


def category(db, id):
    if id:
        get(db, Category, id)


def save(db, item, data):
    for key, value in data.items():
        setattr(item, key, value)
    db.add(item)
    db.commit()
    return item


@app.get("/api/health")
def health(db: DB):
    db.execute(select(Settings.id)).first()
    return {"status": "ok"}


@app.get("/api/settings")
def settings(db: DB):
    return get(db, Settings, 1)


@app.put("/api/settings")
def update_settings(data: SettingsIn, db: DB):
    setting = get(db, Settings, 1)
    if setting.currency != data.currency and (
        setting.savings_balance is not None
        or db.scalar(
            select(Category.id).where(Category.monthly_guide.is_not(None)).limit(1)
        )
        or any(
            db.scalar(select(func.count()).select_from(model))
            for model in (
                Recurring,
                Purchase,
                Transaction,
                StatementImport,
                BillEstimate,
                ReservePlan,
                SavingsObservation,
            )
        )
    ):
        raise HTTPException(
            409, "Currency is fixed once budget entries or imports exist."
        )
    if data.advisor_enabled and not data.model:
        raise HTTPException(422, "Choose a local model before enabling Budget advisor.")
    if data.model and (
        data.model != setting.model
        or (data.advisor_enabled and not setting.advisor_enabled)
    ):
        try:
            if data.model not in available_models():
                raise HTTPException(422, "Choose an installed local model.")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                503, "Cannot reach local Ollama. Start it and try again."
            )
    if (
        data.reserve_checkpoint_day is not None
        and data.reserve_checkpoint_day != setting.reserve_checkpoint_day
    ):
        plan = db.get(ReservePlan, 1)
        if plan:
            plan.dismissed_until = None
    return save(db, setting, data.model_dump(exclude_none=True))


@app.get("/api/models")
def models():
    try:
        return {"models": available_models(), "error": ""}
    except Exception:
        return {
            "models": [],
            "error": "Ollama is unavailable. Start it for Budget advisor or PDF extraction. CSV imports work without it.",
        }


@app.get("/api/advisor/research-status")
def advisor_research_status():
    return research_status()


@app.post("/api/advisor/research-preview")
def preview_research(data: ResearchPreviewIn):
    plan = plan_research(data.topic, local_today().isoformat())
    return {
        **plan.model_dump(),
        "topic": data.topic,
        "confirmation": confirmation_for(plan, data.topic),
    }


@app.post("/api/advisor/chat")
def advisor_chat(data: AdvisorIn, db: ReadOnlyDB):
    setting = get(db, Settings, 1)
    if not setting.advisor_enabled:
        raise HTTPException(409, "Enable Budget advisor in Settings to use local chat.")
    if not setting.model:
        raise HTTPException(422, "Choose an installed local model in Settings.")
    if data.purchase_id:
        get(db, Purchase, data.purchase_id)
    if data.bill_estimate_id:
        get(db, BillEstimate, data.bill_estimate_id)
    try:
        context = budget_context(db, data)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    model = setting.model
    # Release the read transaction before waiting for the optional local model.
    db.rollback()
    try:
        reply = answer_question(model, data, context)
    except Exception as exc:
        import httpx

        if isinstance(exc, httpx.TimeoutException):
            raise HTTPException(
                504,
                "The local model exceeded the advisor time limit. Increase ADVISOR_TIMEOUT_SECONDS in .env (default 300), or choose a faster installed model in Settings. Your question can be retried and your budget is unchanged.",
            )
        if isinstance(exc, ValueError):
            raise HTTPException(503, str(exc))
        raise HTTPException(
            503,
            "Cannot get a reply from local Ollama. Check that it is running and the selected model is installed. Your budget is unchanged.",
        )
    return {"reply": reply, "context": context}


@app.get("/api/savings")
def read_savings(db: DB):
    return savings_settings(db)


@app.put("/api/savings")
def save_savings(data: SavingsIn, db: DB):
    setting = get(db, Settings, 1)
    setting.savings_balance, setting.savings_month, setting.savings_floor = (
        data.amount,
        data.month,
        data.floor,
    )
    as_of = date.fromisoformat(data.month + "-01")
    if as_of <= local_today():
        observe(db, data.amount, as_of)
    db.commit()
    return savings_settings(db)


@app.get("/api/reserve-check")
def read_reserve_check(db: DB):
    return reserve_check(db)


@app.put("/api/reserve-check/plan")
def set_reserve_plan(data: ReservePlanIn, db: DB):
    start = date.fromisoformat(data.month + "-01")
    if start > local_today():
        raise HTTPException(
            422, "Start the reserve plan in the current month or earlier."
        )
    schedules = schedule_snapshot(db)
    if not schedules:
        raise HTTPException(
            422, "Configure at least one dated, distributed annual payable first."
        )
    item = db.get(ReservePlan, 1) or ReservePlan(id=1)
    item.amount, item.start_date, item.schedules, item.dismissed_until = (
        data.amount,
        start,
        schedules,
        None,
    )
    db.add(item)
    db.commit()
    return reserve_check(db)


@app.post("/api/reserve-check/balances")
def record_savings_balance(data: SavingsObservationIn, db: DB):
    try:
        observe(db, data.amount, data.as_of)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    db.commit()
    return reserve_check(db)


@app.post("/api/reserve-check/dismiss")
def dismiss_reserve_check(db: DB):
    result = reserve_check(db)
    item = get(db, ReservePlan, 1)
    item.dismissed_until = result["next_checkpoint"]
    db.commit()
    return reserve_check(db)


@app.post("/api/savings/projection")
def preview_savings(data: SavingsProjectionIn, db: DB):
    try:
        return project_savings(db, data)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/bill-estimates")
def bill_estimates(db: DB):
    return db.scalars(
        select(BillEstimate).order_by(BillEstimate.start_month, BillEstimate.name)
    ).all()


@app.post("/api/bill-estimates", status_code=201)
def create_bill_estimate(data: BillEstimateIn, db: DB):
    get(db, Category, data.category_id)
    return save(db, BillEstimate(), data.model_dump())


@app.put("/api/bill-estimates/{id}")
def edit_bill_estimate(id: str, data: BillEstimateIn, db: DB):
    item = get(db, BillEstimate, id)
    if item.included:
        raise HTTPException(
            409, "This estimate has been added. Edit its recurring bill instead."
        )
    get(db, Category, data.category_id)
    return save(db, item, data.model_dump())


@app.delete("/api/bill-estimates/{id}")
def delete_bill_estimate(id: str, db: DB):
    db.delete(get(db, BillEstimate, id))
    db.commit()
    return {"ok": True}


@app.post("/api/bill-estimates/{id}/include")
def include_bill_estimate(id: str, db: DB):
    item = db.scalar(
        select(BillEstimate).where(BillEstimate.id == id).with_for_update()
    )
    if item is None:
        raise HTTPException(404, "Bill estimate not found.")
    if item.included:
        raise HTTPException(
            409, "This estimate has already been added to recurring bills."
        )
    data = RecurringCreate(
        name=item.name,
        amount=item.amount,
        kind="payable",
        frequency="monthly",
        category_id=item.category_id,
        start_month=item.start_month,
        end_month=item.end_month,
        due_day=item.due_day,
    )
    recurring = Recurring(**due_settings(data))
    db.add(recurring)
    db.flush()
    db.add(
        AmountChange(
            recurring_id=recurring.id,
            month=recurring.start_month,
            amount=item.amount,
            override=False,
        )
    )
    item.included, item.recurring_id = True, recurring.id
    db.commit()
    return item


@app.get("/api/categories")
def categories(db: DB):
    return db.scalars(select(Category).order_by(Category.name)).all()


@app.patch("/api/categories/{id}/guide")
def category_guide(id: str, data: CategoryGuideIn, db: DB):
    return save(db, get(db, Category, id), data.model_dump())


@app.get("/api/spending/averages")
def spending_averages(
    end: Month, db: DB, category_ids: Annotated[list[str] | None, Query()] = None
):
    for id in category_ids or []:
        get(db, Category, id)
    try:
        return category_averages(db, end, category_ids)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.post("/api/categories", status_code=201)
def create_category(data: CategoryIn, db: DB):
    return save(db, Category(), data.model_dump())


@app.put("/api/categories/{id}")
def edit_category(id: str, data: CategoryIn, db: DB):
    return save(db, get(db, Category, id), data.model_dump())


@app.delete("/api/categories/{id}")
def delete_category(id: str, db: DB):
    db.delete(get(db, Category, id))
    db.commit()
    return {"ok": True}


@app.get("/api/accounts")
def accounts(db: DB):
    return account_information(db)


@app.post("/api/accounts", status_code=201)
def create_account(data: AccountIn, db: DB):
    return save(db, Account(), data.model_dump())


@app.put("/api/accounts/{id}")
def edit_account(id: str, data: AccountIn, db: DB):
    return save(db, get(db, Account, id), data.model_dump(exclude_unset=True))


@app.patch("/api/accounts/{id}/monitoring")
def monitor_account(id: str, data: CardMonitoringIn, db: DB):
    save(db, get(db, Account, id), data.model_dump())
    return next(account for account in account_information(db) if account["id"] == id)


@app.delete("/api/accounts/{id}")
def delete_account(id: str, db: DB):
    db.delete(get(db, Account, id))
    db.commit()
    return {"ok": True}


@app.get("/api/recurring")
def recurring(db: DB):
    changes = db.scalars(select(AmountChange).order_by(AmountChange.month)).all()
    return [
        {
            **jsonable_encoder(r),
            "changes": [jsonable_encoder(c) for c in changes if c.recurring_id == r.id],
        }
        for r in db.scalars(select(Recurring).order_by(Recurring.name)).all()
    ]


@app.post("/api/recurring", status_code=201)
def create_recurring(data: RecurringCreate, db: DB):
    category(db, data.category_id)
    if data.ach_account_id:
        get(db, Account, data.ach_account_id)
    item = Recurring(**due_settings(data))
    db.add(item)
    db.flush()
    db.add(
        AmountChange(
            recurring_id=item.id,
            month=item.start_month,
            amount=data.amount,
            override=False,
        )
    )
    db.commit()
    record_due(db)
    return item


@app.post("/api/recurring/record-due")
def record_due_ach(db: DB):
    return {"added": record_due(db)}


@app.get("/api/recurring/dues")
def bill_dues(db: DB):
    return upcoming_dues(db)


@app.put("/api/recurring/{id}/payments/{period}")
def confirm_bill_payment(id: str, period: str, data: BillPaymentIn, db: DB):
    item = db.scalar(select(Recurring).where(Recurring.id == id).with_for_update())
    if item is None:
        raise HTTPException(404, "Recurring account not found.")
    if item.kind != "payable":
        raise HTTPException(422, "Payment confirmations are for payables only.")
    payment = db.scalar(
        select(BillPayment).where(
            BillPayment.recurring_id == id, BillPayment.period == period
        )
    )
    changes = db.scalars(
        select(AmountChange).where(AmountChange.recurring_id == id)
    ).all()
    row = occurrence(item, changes, period)
    if not row and not payment:
        raise HTTPException(
            422,
            "Choose an occurrence within this bill’s active schedule and payment tracking period.",
        )
    if automatic_occurrence(item, period) or db.scalar(
        select(RecurringDebit.id).where(
            RecurringDebit.recurring_id == id,
            RecurringDebit.month == period,
            RecurringDebit.transaction_id.is_not(None),
        )
    ):
        raise HTTPException(
            409,
            "ACH payments are tracked automatically from their recorded debits. Edit the actual transaction or ACH schedule instead.",
        )
    if data.paid and data.paid_on and data.paid_on > local_today():
        raise HTTPException(422, "The paid date cannot be in the future.")
    if data.paid:
        if payment is None:
            payment = BillPayment(
                recurring_id=id,
                period=period,
                due_date=date.fromisoformat(row["due_date"]),
                amount=row["amount"],
            )
            db.add(payment)
        elif payment.paid_on is None and row:
            payment.due_date, payment.amount = (
                date.fromisoformat(row["due_date"]),
                row["amount"],
            )
        payment.paid_on = data.paid_on or payment.paid_on or local_today()
    elif payment:
        payment.paid_on = None
    db.commit()
    return {
        "recurring_id": id,
        "period": period,
        "paid": bool(payment and payment.paid_on),
        "paid_on": payment.paid_on if payment else None,
    }


@app.put("/api/recurring/{id}")
def edit_recurring(id: str, data: RecurringIn, db: DB):
    category(db, data.category_id)
    if data.ach_account_id:
        get(db, Account, data.ach_account_id)
    item = db.scalar(select(Recurring).where(Recurring.id == id).with_for_update())
    if not item:
        raise HTTPException(404, "Record not found.")
    if data.start_month != item.start_month:
        defaults = db.scalars(
            select(AmountChange)
            .where(
                AmountChange.recurring_id == id,
                AmountChange.override == False,
            )
            .order_by(AmountChange.month)
        ).all()
        # Keep every existing change on its calendar date. Establish an initial
        # default at the new start, including when extending a schedule earlier.
        if not any(c.month == data.start_month for c in defaults):
            earlier = [c for c in defaults if c.month <= data.start_month]
            baseline = earlier[-1] if earlier else defaults[0]
            db.add(
                AmountChange(
                    recurring_id=id,
                    month=data.start_month,
                    amount=baseline.amount,
                    override=False,
                )
            )
    save(db, item, due_settings(data, item))
    record_due(db)
    return item


@app.put("/api/recurring/{id}/amount")
def change_amount(id: str, data: ChangeIn, db: DB):
    item = get(db, Recurring, id)
    if data.month < item.start_month or (
        item.end_month and data.month > item.end_month
    ):
        raise HTTPException(422, "Choose a month within this schedule.")
    if (
        data.override
        and item.frequency == "annual"
        and item.kind == "payable"
        and not item.distribute_annual
        and data.month[5:] != annual_due_month(item)
    ):
        raise HTTPException(
            422, "A one-month override for this annual expense must use its due month."
        )
    change = db.scalar(
        select(AmountChange).where(
            AmountChange.recurring_id == id,
            AmountChange.month == data.month,
            AmountChange.override == data.override,
        )
    )
    return save(db, change or AmountChange(recurring_id=id), data.model_dump())


@app.delete("/api/recurring/{id}/amount/{change_id}")
def delete_change(id: str, change_id: str, db: DB):
    item = get(db, Recurring, id)
    change = get(db, AmountChange, change_id)
    if change.recurring_id != id:
        raise HTTPException(404, "Change not found.")
    if not change.override and change.month == item.start_month:
        raise HTTPException(422, "The initial default amount cannot be removed.")
    db.delete(change)
    db.commit()
    return {"ok": True}


@app.delete("/api/recurring/{id}")
def delete_recurring(id: str, db: DB):
    db.delete(get(db, Recurring, id))
    db.commit()
    return {"ok": True}


@app.get("/api/purchases")
def purchases(db: DB):
    return db.scalars(select(Purchase).order_by(Purchase.month, Purchase.name)).all()


@app.post("/api/purchases", status_code=201)
def create_purchase(data: PurchaseIn, db: DB):
    category(db, data.category_id)
    return save(db, Purchase(), data.model_dump())


@app.put("/api/purchases/{id}")
def edit_purchase(id: str, data: PurchaseIn, db: DB):
    category(db, data.category_id)
    return save(db, get(db, Purchase, id), data.model_dump())


@app.delete("/api/purchases/{id}")
def delete_purchase(id: str, db: DB):
    db.delete(get(db, Purchase, id))
    db.commit()
    return {"ok": True}


@app.get("/api/forecast")
def month_forecast(month: Month, db: DB, preview: str | None = None):
    if preview:
        p = get(db, Purchase, preview)
        if p.month != month:
            raise HTTPException(422, "Preview month must match the purchase.")
    result = forecast(db, month, preview=preview)
    actuals = actual(db, month)
    return {
        **result,
        "actual": actuals,
        "actual_deficit": actuals["expenses"] > result["income"],
    }


@app.get("/api/forecasts")
def forecast_window(start: Month, db: DB, months: int = Query(default=12, ge=1, le=24)):
    last = shift_month(start, months - 1)
    if last > "9998-12":
        raise HTTPException(422, "The forecast window must end by December 9998.")
    inputs = ForecastInputs(db)
    actuals = ActualWindow(db, start, last)
    result = []
    for offset in range(months):
        month = shift_month(start, offset)
        values = inputs.forecast(month)
        recorded = actuals.actual(month)
        result.append(
            {
                **values,
                "actual": recorded,
                "actual_deficit": recorded["expenses"] > values["income"],
            }
        )
    return result


@app.get("/api/trends")
def trends(
    end: Month, db: DB, category_ids: Annotated[list[str] | None, Query()] = None
):
    first = shift_month(end, -11)
    if first < "1900-01":
        raise HTTPException(
            422, "Choose December 1900 or later for a full 12-month window."
        )
    cats = db.scalars(select(Category)).all()
    selected = set(category_ids) if category_ids else None
    if selected and not selected <= {c.id for c in cats}:
        raise HTTPException(404, "Category not found.")
    inputs = ForecastInputs(db)
    actuals = ActualWindow(db, first, end)
    points = []
    for offset in range(12):
        month = shift_month(first, offset)
        values = inputs.forecast(month)
        recorded = actuals.actual(month, selected)
        totals = {}
        for line in values["lines"]:
            if line["kind"] == "payable":
                totals[line["category_id"]] = (
                    totals.get(line["category_id"], 0) + line["amount"]
                )
        by_category = {
            c.id: {
                "actual": None
                if recorded["status"] == "missing"
                else actuals.totals.get(month, {}).get(c.id, 0),
                "forecast": totals.get(c.id, 0),
            }
            for c in cats
            if selected is None or c.id in selected
        }
        points.append(
            {
                "month": month,
                "forecast": sum(
                    value
                    for key, value in totals.items()
                    if selected is None or key in selected
                ),
                "income": values["income"],
                "actual": None
                if recorded["status"] == "missing"
                else recorded["expenses"],
                "status": recorded["status"],
                "categories": by_category,
            }
        )
    return points


@app.get("/api/expenses/breakdown")
def breakdown(
    start: date, end: date, db: DB, basis: Literal["actual", "forecast"] = "actual"
):
    if start > end:
        raise HTTPException(422, "Choose an end date on or after the start date.")
    if start.year < 1900 or end.year > 9998:
        raise HTTPException(422, "Choose dates between 1900 and 9998.")
    if basis == "forecast" and (start.day != 1 or end != month_end(month_key(end))):
        raise HTTPException(
            422,
            "Planned expenses use full calendar months; choose the first and last day of the month.",
        )
    try:
        return expense_breakdown(db, start, end, basis)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.put("/api/months/{month}")
def complete(month: Month, data: CompleteIn, db: DB):
    return save(
        db, db.get(MonthStatus, month) or MonthStatus(month=month), data.model_dump()
    )


@app.get("/api/transactions")
def transactions(
    db: DB, month: Month | None = None, q: str = "", category_id: str | None = None
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
    rows = db.execute(query.order_by(Transaction.date.desc(), Transaction.id)).all()
    # Large statement provenance is available only from the detail endpoint.
    return [
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


@app.get("/api/transactions/{id}")
def transaction_details(id: str, db: DB):
    item = get(db, Transaction, id)
    data = jsonable_encoder(item)
    value = dict(item.provenance)
    if item.import_id and isinstance(value.get("source"), dict):
        value["source"] = expanded_sources(db, item.import_id, [value["source"]])[0]
    data["provenance"] = value
    return data


@app.post("/api/transactions", status_code=201)
def create_transaction(data: TransactionIn, db: DB):
    category(db, data.category_id)
    get(db, Account, data.account_id)
    item = Transaction(provenance={"manual": True}, **data.model_dump())
    db.add(item)
    learn_labels(db, [data.model_dump()])
    db.commit()
    return item


@app.put("/api/transactions/{id}")
def edit_transaction(id: str, data: TransactionIn, db: DB):
    category(db, data.category_id)
    get(db, Account, data.account_id)
    item = get(db, Transaction, id)
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    learn_labels(db, [data.model_dump()])
    db.commit()
    return item


@app.delete("/api/transactions/{id}")
def delete_transaction(id: str, db: DB):
    db.delete(get(db, Transaction, id))
    db.commit()
    return {"ok": True}


def import_view(job, db=None):
    source = job.source
    data = jsonable_encoder(job)
    if db is not None and source.get("type") == "pdf":
        sources = expanded_sources(db, job.id, [r.get("source", {}) for r in job.rows])
        data["rows"] = [
            {**row, "source": item}
            for row, item in zip(data["rows"], sources, strict=True)
        ]
    return {
        **data,
        "source": {
            "type": source.get("type"),
            "headers": source.get("headers", []),
            "preview": source.get("records", [])[:5],
            "mapping": source.get("mapping"),
            "mapping_warning": source.get("mapping_warning"),
        },
        "commit_summary": source.get("commit_summary"),
    }


@app.get("/api/imports")
def imports(db: DB):
    return [
        {
            "id": j.id,
            "filename": j.filename,
            "status": j.status,
            "period": j.period,
            "account_id": j.account_id,
            "error": j.error,
        }
        for j in db.scalars(
            select(StatementImport)
            .options(
                load_only(
                    StatementImport.id,
                    StatementImport.filename,
                    StatementImport.status,
                    StatementImport.period,
                    StatementImport.account_id,
                    StatementImport.error,
                )
            )
            .order_by(StatementImport.created_at.desc())
        ).all()
    ]


@app.post("/api/imports", status_code=201)
async def prepare_import(
    db: DB,
    account_id: Annotated[str, Form()],
    period: Annotated[Month, Form()],
    file: Annotated[UploadFile, File()],
):
    get(db, Account, account_id)
    data = await file.read(15 * 1024 * 1024 + 1)
    await file.close()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "Statements must be smaller than 15 MB.")
    digest = sha256(data).hexdigest()
    if db.scalar(
        select(StatementImport.id).where(
            StatementImport.account_id == account_id,
            StatementImport.file_hash == digest,
        )
    ):
        raise HTTPException(
            409,
            "This exact file was already uploaded for this account. Open its existing import to review or retry.",
        )
    try:
        source = await asyncio.to_thread(prepare_file, file.filename or "", data)
    except Exception as exc:
        raise HTTPException(422, str(exc)[:1000])
    job = StatementImport(
        account_id=account_id,
        period=period,
        filename=Path(file.filename or "statement").name[:200],
        file_hash=digest,
        source=source,
        rows=[],
    )
    db.add(job)
    db.flush()
    apply_saved_mapping(db, job)
    db.commit()
    return import_view(job, db)


@app.get("/api/payee-rules")
def payee_rules(db: DB):
    return db.scalars(select(PayeeRule).order_by(PayeeRule.payee, PayeeRule.kind)).all()


@app.put("/api/payee-rules/{id}")
def edit_payee_rule(id: str, data: PayeeRuleIn, db: DB):
    get(db, Category, data.category_id)
    return save(db, get(db, PayeeRule, id), data.model_dump())


@app.delete("/api/payee-rules/{id}")
def forget_payee_rule(id: str, db: DB):
    db.delete(get(db, PayeeRule, id))
    db.commit()
    return {"ok": True}


@app.post("/api/imports/{id}/categorize")
def categorize_from_payees(id: str, db: DB):
    job = db.scalar(
        select(StatementImport).where(StatementImport.id == id).with_for_update()
    )
    if not job:
        raise HTTPException(404, "Import not found.")
    if job.status in ("processing", "committed", "undone"):
        raise HTTPException(409, "This import cannot be categorized now.")
    from copy import deepcopy

    job.rows = validate_rows(
        db, apply_payee_rules(db, deepcopy(job.rows)), job.account_id
    )
    job.status, job.error = "review", ""
    db.commit()
    return import_view(job, db)


@app.get("/api/imports/{id}")
def get_import(id: str, db: DB):
    return import_view(get(db, StatementImport, id), db)


@app.post("/api/imports/{id}/mapping/default")
def use_card_mapping(id: str, db: DB):
    job = db.scalar(
        select(StatementImport).where(StatementImport.id == id).with_for_update()
    )
    if not job:
        raise HTTPException(404, "Import not found.")
    apply_saved_mapping(db, job)
    db.commit()
    return import_view(job, db)


@app.put("/api/imports/{id}/mapping")
def mapping(id: str, data: MappingIn, db: DB):
    job = db.scalar(
        select(StatementImport).where(StatementImport.id == id).with_for_update()
    )
    if not job:
        raise HTTPException(404, "Import not found.")
    if (
        job.status in ("processing", "committed", "undone")
        or job.source.get("type") != "csv"
    ):
        raise HTTPException(409, "This import cannot be mapped now.")
    try:
        rows = csv_rows(
            job.source, data.model_dump(), job.period, get(db, Settings, 1).currency
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    job.source = {
        **{k: v for k, v in job.source.items() if k != "model_used"},
        "mapping": data.model_dump(),
        "mapping_warning": "",
    }
    get(db, Account, job.account_id).csv_mapping = data.model_dump()
    job.rows = validate_rows(db, apply_payee_rules(db, rows), job.account_id)
    job.status = "review"
    job.error = ""
    db.commit()
    return import_view(job, db)


@app.post("/api/imports/{id}/process")
def start_processing(id: str, db: DB, data: ProcessImportIn | None = None):
    job = db.scalar(
        select(StatementImport).where(StatementImport.id == id).with_for_update()
    )
    if not job:
        raise HTTPException(404, "Import not found.")
    if job.status in ("processing", "committed", "undone"):
        raise HTTPException(409, "This import cannot be processed now.")
    if job.source.get("type") == "csv" and not job.source.get("mapping"):
        raise HTTPException(422, "Map CSV columns first.")
    if (
        job.source.get("type") == "pdf"
        and job.rows
        and not (data and data.replace_review)
    ):
        raise HTTPException(
            409,
            "Re-extraction replaces reviewed PDF rows. Confirm replacement explicitly.",
        )
    job.processing_token = uid()
    job.status, job.error = "processing", ""
    db.commit()
    executor.submit(process_import, id, job.processing_token)
    return import_view(job, db)


@app.put("/api/imports/{id}/review")
def review(id: str, data: CommitIn, db: DB):
    job = db.scalar(
        select(StatementImport).where(StatementImport.id == id).with_for_update()
    )
    if not job:
        raise HTTPException(404, "Import not found.")
    if job.status in ("processing", "committed", "undone"):
        raise HTTPException(409, "This import cannot be edited now.")
    rows = []
    for row in data.rows:
        index = row.get("source_index")
        source = (
            job.rows[index].get("source", {})
            if isinstance(index, int) and 0 <= index < len(job.rows)
            else {"manual_review": True}
        )
        rows.append(
            {
                k: v
                for k, v in row.items()
                if k
                in ("date", "description", "amount", "kind", "category_id", "selected")
            }
            | {
                "source": source,
                "classification": job.rows[index].get("classification")
                if isinstance(index, int)
                and 0 <= index < len(job.rows)
                and row.get("category_id") == job.rows[index].get("category_id")
                and row.get("kind") == job.rows[index].get("kind")
                else "manual",
            }
        )
    job.rows = validate_rows(db, rows, job.account_id)
    job.status = "review"
    db.commit()
    return import_view(job, db)


@app.post("/api/imports/{id}/commit")
def commit_import(id: str, db: DB):
    job = db.scalar(
        select(StatementImport).where(StatementImport.id == id).with_for_update()
    )
    if not job:
        raise HTTPException(404, "Import not found.")
    if job.status not in ("review", "failed", "interrupted"):
        raise HTTPException(409, "Review this import before saving.")
    # Serialize commits for one card: a concurrent overlapping import must see
    # the first commit's original CSV rows before it decides which rows to save.
    db.scalar(select(Account).where(Account.id == job.account_id).with_for_update())
    rows = validate_rows(db, job.rows, job.account_id)
    selected = [
        r for r in rows if r.get("selected", True) and not r.get("skip_duplicate")
    ]
    skipped = sum(bool(r.get("skip_duplicate")) for r in rows)
    if (not selected and not skipped) or any(r["errors"] for r in selected):
        raise HTTPException(
            422, "Select at least one valid row and resolve all selected row errors."
        )
    rows = compact_pdf_rows(db, job, rows)
    selected = [
        r for r in rows if r.get("selected", True) and not r.get("skip_duplicate")
    ]
    for row in selected:
        data = TransactionIn.model_validate({**row, "account_id": job.account_id})
        db.add(
            Transaction(
                **data.model_dump(),
                import_id=id,
                provenance={
                    "source": row.get("source", {}),
                    "original_review": {
                        key: value for key, value in row.items() if key != "source"
                    },
                    "model": job.source.get("model_used", ""),
                },
            )
        )
    learn_labels(db, selected)
    job.rows = rows
    job.source = {
        "type": job.source["type"],
        "mapping": job.source.get("mapping"),
        "commit_summary": {"added": len(selected), "skipped": skipped},
    }
    job.status, job.error = "committed", ""
    db.commit()
    return import_view(job, db)


@app.delete("/api/imports/{id}")
def delete_import(id: str, db: DB):
    job = db.scalar(
        select(StatementImport).where(StatementImport.id == id).with_for_update()
    )
    if not job:
        raise HTTPException(404, "Import not found.")
    if job.status == "processing":
        raise HTTPException(
            409, "Wait for processing to finish before deleting this import."
        )
    if job.status == "committed" or db.scalar(
        select(Transaction.id).where(Transaction.import_id == id).limit(1)
    ):
        raise HTTPException(
            409,
            "Undo this import before deleting it so its saved transactions are removed explicitly.",
        )
    db.delete(job)
    db.commit()
    return {"ok": True}


@app.post("/api/imports/{id}/undo")
def undo_import(id: str, db: DB):
    job = db.scalar(
        select(StatementImport).where(StatementImport.id == id).with_for_update()
    )
    if not job or job.status != "committed":
        raise HTTPException(409, "Only committed imports can be undone.")
    db.execute(delete(Transaction).where(Transaction.import_id == id))
    job.status = "undone"
    db.commit()
    return import_view(job, db)


FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")

    @app.get("/")
    def index():
        return FileResponse(FRONTEND / "index.html")
