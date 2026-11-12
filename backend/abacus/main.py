import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from datetime import date
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Literal

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from . import dreaming
from .ach import record_due
from .advisor import answer_question, budget_context
from .advisor_history import latest_spending_comparison
from .advisor_memory import (
    close_memory,
    invalidate_memory,
    memory_epoch,
    recalled_memory,
)
from .alert_api import router as alert_router
from .annual_income import router as annual_income_router
from .api_helpers import category, get, save
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
from .db import Session, read_only_session, session
from .dreaming_api import router as dreaming_router
from .dues import (
    automatic_occurrence,
    due_settings,
    local_today,
    occurrence,
    upcoming_dues,
)
from .expenses import expense_breakdown, month_end, month_key
from .funding import cash_projection
from .import_api import router as import_router
from .local_model import available_models
from .memory_api import router as memory_router
from .model_tracing import flush_model_traces
from .models import (
    Account,
    AmountChange,
    BillPayment,
    Category,
    MonthStatus,
    Plan,
    Recurring,
    RecurringDebit,
    Settings,
    StatementImport,
    Transaction,
)
from .payee_review import router as payee_review_router
from .planning import planning_summary
from .planning import router as planning_router
from .records_api import router as records_router
from .research import confirmation_for, plan_research, research_status
from .responses import AccountOut, CategoryOut, ForecastOut, SettingsOut
from .savings import project_savings, savings_settings
from .schemas import (
    AccountIn,
    AdvisorIn,
    BillPaymentIn,
    CardMonitoringIn,
    CategoryGuideIn,
    CategoryIn,
    ChangeIn,
    CompleteIn,
    Month,
    RecurringCreate,
    RecurringIn,
    ResearchPreviewIn,
    SavingsIn,
    SavingsProjectionIn,
    SettingsIn,
)
from .transaction_api import router as transaction_router


@asynccontextmanager
async def lifespan(app):
    dreaming.start()
    with Session() as db:
        from .models import PayeeReview

        db.execute(
            update(PayeeReview)
            .where(PayeeReview.status.in_(["queued", "running"]))
            .values(
                status="interrupted",
                error="Review interrupted by restart. Existing payees were not changed. Start another review.",
            )
        )
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

    async def dreaming_scheduler():
        while True:
            await asyncio.sleep(5)
            try:
                await asyncio.to_thread(dreaming.tick)
            except Exception:
                logging.getLogger(__name__).warning(
                    "Memory dreaming pass unavailable; will retry."
                )

    dream_task = asyncio.create_task(dreaming_scheduler())
    task = asyncio.create_task(ach_scheduler())
    try:
        yield
    finally:
        dreaming.stop()
        dream_task.cancel()
        with suppress(asyncio.CancelledError):
            await dream_task
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await asyncio.to_thread(close_memory)
        await asyncio.to_thread(flush_model_traces)


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


app = FastAPI(title="Abacus", version=version("abacus"), lifespan=lifespan)
app.include_router(records_router)
app.include_router(transaction_router)
app.include_router(import_router)
app.include_router(memory_router)
app.include_router(dreaming_router)
app.include_router(alert_router)
app.include_router(annual_income_router)
app.include_router(planning_router)
app.include_router(payee_review_router)
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


@app.get("/api/health")
def health(db: DB):
    db.execute(select(Settings.id)).first()
    return {"status": "ok"}


@app.get("/api/settings", response_model=SettingsOut)
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
                Plan,
                Transaction,
                StatementImport,
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
    memory_changed = (
        data.advisor_memory_enabled is not None
        and data.advisor_memory_enabled != setting.advisor_memory_enabled
    )
    with dreaming.gate:
        result = save(db, setting, data.model_dump(exclude_none=True))
        if not dreaming.enabled(setting):
            dreaming.cancel(db)
    if memory_changed:
        invalidate_memory()
        close_memory()
    return result


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
    memory_enabled = setting.advisor_memory_enabled
    epoch = memory_epoch()
    if memory_enabled and data.history and data.memory_epoch != epoch:
        raise HTTPException(
            409, "Advisor memory changed. Start a new conversation before continuing."
        )
    if data.plan_id:
        get(db, Plan, data.plan_id)
    try:
        context = budget_context(db, data)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    model = setting.model
    # Release the read transaction before waiting for the optional local model.
    db.rollback()
    context["advisor_memory"] = recalled_memory(memory_enabled, data)
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
    if memory_epoch() != epoch:
        raise HTTPException(
            409,
            "Advisor memory changed while answering. Start a new conversation and retry.",
        )
    if data.plan_id:
        current = next(
            (row for row in planning_summary(db)["plans"] if row["id"] == data.plan_id),
            None,
        )
        selected = context["selected_plan"]
        if current is None or any(
            [
                current["updated_at"] != selected["updated_at"],
                current["amount"] != selected["amount_minor"],
                current["target_date"] != selected["target_date"],
                current.get("funding_gap") != selected.get("funding_gap_minor"),
                current["status"] != selected["status"],
                current["set_aside"] != selected["set_aside_minor"],
            ]
        ):
            raise HTTPException(
                409,
                "This plan changed or was deleted while answering. Ask again using the current Planning item.",
            )
    return {
        "reply": reply,
        "reply_truncated": getattr(reply, "truncated", False),
        "context": context,
    }


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
    db.commit()
    return savings_settings(db)


@app.post("/api/savings/projection")
def preview_savings(data: SavingsProjectionIn, db: DB):
    try:
        return project_savings(db, data)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/categories", response_model=list[CategoryOut])
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


@app.get("/api/accounts", response_model=list[AccountOut])
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
    item = get(db, Recurring, id)
    # Retain the last resolved goal if its bill is removed and the FK unlinks it.
    linked = db.scalars(select(Plan).where(Plan.recurring_id == id)).all()
    if linked:
        resolved = {r["id"]: r for r in planning_summary(db)["plans"]}
        for plan in linked:
            row = resolved[plan.id]
            plan.amount = row["amount"]
            plan.target_date = date.fromisoformat(row["target_date"])
    db.delete(item)
    db.commit()
    return {"ok": True}


@app.get("/api/forecast", response_model=ForecastOut, response_model_exclude_unset=True)
def month_forecast(month: Month, db: DB):
    result = forecast(db, month)
    actuals = actual(db, month)
    return {
        **result,
        "actual": actuals,
        "actual_deficit": actuals["expenses"] > result["income"],
    }


@app.get("/api/forecasts")
def forecast_window(
    start: Month,
    db: DB,
    months: int = Query(default=12, ge=1, le=24),
    include_savings: bool = False,
):
    last = shift_month(start, months - 1)
    if last > "9998-12":
        raise HTTPException(422, "The forecast window must end by December 9998.")
    inputs = ForecastInputs(db)
    actuals = ActualWindow(db, start, last)
    setting = db.get(Settings, 1)
    savings = setting.savings_balance if include_savings else None
    funding = (
        planning_summary(db, inputs=inputs, include_projection=False)
        if include_savings
        else None
    )
    running = (
        cash_projection(inputs, setting, funding["plans"], start, months)
        if funding
        else None
    )
    result = []
    for offset in range(months):
        month = shift_month(start, offset)
        values = inputs.forecast(month)
        recorded = actuals.actual(month)
        point = running["months"][offset] if running else None
        due = (
            [
                r
                for r in funding["plans"]
                if r["target_date"][:7] == month and r.get("funding_gap") is not None
            ]
            if funding
            else []
        )
        result.append(
            {
                **values,
                "actual": recorded,
                "actual_deficit": recorded["expenses"] > values["income"],
                **(
                    {
                        "savings_balance": savings,
                        "remaining_with_savings": point["balance"],
                        "savings_adjusted_deficit": point["balance"] < 0
                        if point["balance"] is not None
                        else values["deficit"],
                        "projected_savings": point["balance"],
                        "cash_expenses": point["cash_expenses"],
                        "funding_gap": sum(r["funding_gap"] for r in due),
                        "annual_funding": due,
                        "projection_basis": running["basis"],
                        "income_complete": running["income_complete"],
                    }
                    if include_savings
                    else {}
                ),
            }
        )
    return result


@app.get("/api/spending/comparison")
def overview_spending_comparison(db: DB):
    today = local_today()
    return {
        "today": today.isoformat(),
        "comparison": latest_spending_comparison(db, today),
    }


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


FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")

    @app.get("/")
    def index():
        return FileResponse(FRONTEND / "index.html")
