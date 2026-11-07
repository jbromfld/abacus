from contextlib import asynccontextmanager
from contextlib import suppress
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal
import asyncio
import logging
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, delete, update, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession
from .db import session, Session
from .models import Category, Account, Settings, Recurring, AmountChange, Purchase, Transaction, StatementImport, MonthStatus, PayeeRule
from .schemas import CategoryIn, AccountIn, CardMonitoringIn, RecurringCreate, RecurringIn, ChangeIn, PurchaseIn, TransactionIn, SettingsIn, MappingIn, CommitIn, CompleteIn, Month, PayeeRuleIn, AdvisorIn
from .budget import forecast, actual, shift_month
from .expenses import expense_breakdown, month_end, month_key
from .classification import apply_payee_rules, learn_labels
from .advisor import budget_context, answer_question
from .research import research_status
from .card_alerts import account_information
from .csv_profiles import apply_saved_mapping
from .ach import record_due
from .imports import prepare_file, executor, process_import, validate_rows, available_models, csv_rows

@asynccontextmanager
async def lifespan(app):
    with Session() as db:
        db.execute(update(StatementImport).where(StatementImport.status == 'processing').values(status='interrupted', error='Processing stopped when the app restarted. Retry this import.'))
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
            logging.getLogger(__name__).exception('ACH recording failed; will retry next minute')

app = FastAPI(title='Abacus', lifespan=lifespan)
DB = Annotated[DBSession, Depends(session)]

@app.middleware('http')
async def local_requests(request: Request, call_next):
    if request.url.hostname not in ('localhost', '127.0.0.1', '::1', 'testserver'):
        return JSONResponse({'detail': 'Abacus is local-only.'}, 403)
    origin = request.headers.get('origin')
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin and origin not in (str(request.base_url).rstrip('/'), 'http://127.0.0.1:5173', 'http://localhost:5173'):
        return JSONResponse({'detail': 'Cross-origin writes are disabled.'}, 403)
    return await call_next(request)

@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    return JSONResponse({'detail': 'This name/file already exists, or this record is still referenced. Update its references first.'}, 409)


def get(db, model, id):
    item = db.get(model, id)
    if item is None:
        raise HTTPException(404, 'Record not found.')
    return item


def category(db, id):
    if id:
        get(db, Category, id)


def save(db, item, data):
    for key, value in data.items():
        setattr(item, key, value)
    db.add(item); db.commit()
    return item

@app.get('/api/health')
def health(db: DB):
    db.execute(select(Settings.id)).first()
    return {'status': 'ok'}

@app.get('/api/settings')
def settings(db: DB):
    return get(db, Settings, 1)

@app.put('/api/settings')
def update_settings(data: SettingsIn, db: DB):
    setting = get(db, Settings, 1)
    if setting.currency != data.currency and any(db.scalar(select(func.count()).select_from(model)) for model in (Recurring, Purchase, Transaction, StatementImport)):
        raise HTTPException(409, 'Currency is fixed once budget entries or imports exist.')
    if data.advisor_enabled and not data.model:
        raise HTTPException(422, 'Choose a local model before enabling Budget advisor.')
    if data.model and (data.model != setting.model or (data.advisor_enabled and not setting.advisor_enabled)):
        try:
            if data.model not in available_models():
                raise HTTPException(422, 'Choose an installed local model.')
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, 'Cannot reach local Ollama. Start it and try again.')
    return save(db, setting, data.model_dump())

@app.get('/api/models')
def models():
    try:
        return {'models': available_models(), 'error': ''}
    except Exception:
        return {'models': [], 'error': 'Ollama is unavailable. Start it for Budget advisor or PDF extraction. CSV imports work without it.'}

@app.get('/api/advisor/research-status')
def advisor_research_status():
    return research_status()


@app.post('/api/advisor/chat')
def advisor_chat(data: AdvisorIn, db: DB):
    setting = get(db, Settings, 1)
    if not setting.advisor_enabled:
        raise HTTPException(409, 'Enable Budget advisor in Settings to use local chat.')
    if not setting.model:
        raise HTTPException(422, 'Choose an installed local model in Settings.')
    if data.purchase_id:
        get(db, Purchase, data.purchase_id)
    context = budget_context(db, data)
    model = setting.model
    # Release the read transaction before waiting for the optional local model.
    db.rollback()
    try:
        reply = answer_question(model, data, context)
    except Exception as exc:
        import httpx
        if isinstance(exc, httpx.TimeoutException):
            raise HTTPException(504, 'The local model exceeded the advisor time limit. Increase ADVISOR_TIMEOUT_SECONDS in .env (default 300), or choose a faster installed model in Settings. Your question can be retried and your budget is unchanged.')
        if isinstance(exc, ValueError):
            raise HTTPException(503, str(exc))
        raise HTTPException(503, 'Cannot get a reply from local Ollama. Check that it is running and the selected model is installed. Your budget is unchanged.')
    return {'reply': reply, 'context': context}


@app.get('/api/categories')
def categories(db: DB):
    return db.scalars(select(Category).order_by(Category.name)).all()

@app.post('/api/categories', status_code=201)
def create_category(data: CategoryIn, db: DB):
    return save(db, Category(), data.model_dump())

@app.put('/api/categories/{id}')
def edit_category(id: str, data: CategoryIn, db: DB):
    return save(db, get(db, Category, id), data.model_dump())

@app.delete('/api/categories/{id}')
def delete_category(id: str, db: DB):
    db.delete(get(db, Category, id)); db.commit()
    return {'ok': True}

@app.get('/api/accounts')
def accounts(db: DB):
    return account_information(db)

@app.post('/api/accounts', status_code=201)
def create_account(data: AccountIn, db: DB):
    return save(db, Account(), data.model_dump())

@app.put('/api/accounts/{id}')
def edit_account(id: str, data: AccountIn, db: DB):
    return save(db, get(db, Account, id), data.model_dump(exclude_unset=True))

@app.patch('/api/accounts/{id}/monitoring')
def monitor_account(id: str, data: CardMonitoringIn, db: DB):
    save(db, get(db, Account, id), data.model_dump())
    return next(account for account in account_information(db) if account['id'] == id)


@app.delete('/api/accounts/{id}')
def delete_account(id: str, db: DB):
    db.delete(get(db, Account, id)); db.commit()
    return {'ok': True}

@app.get('/api/recurring')
def recurring(db: DB):
    changes = db.scalars(select(AmountChange).order_by(AmountChange.month)).all()
    return [{**jsonable_encoder(r), 'changes': [jsonable_encoder(c) for c in changes if c.recurring_id == r.id]} for r in db.scalars(select(Recurring).order_by(Recurring.name)).all()]

@app.post('/api/recurring', status_code=201)
def create_recurring(data: RecurringCreate, db: DB):
    category(db, data.category_id)
    if data.ach_account_id:
        get(db, Account, data.ach_account_id)
    item = Recurring(**data.model_dump(exclude={'amount'}))
    db.add(item); db.flush()
    db.add(AmountChange(recurring_id=item.id, month=item.start_month, amount=data.amount, override=False))
    db.commit()
    record_due(db)
    return item

@app.post('/api/recurring/record-due')
def record_due_ach(db: DB):
    return {'added': record_due(db)}

@app.put('/api/recurring/{id}')
def edit_recurring(id: str, data: RecurringIn, db: DB):
    category(db, data.category_id)
    if data.ach_account_id:
        get(db, Account, data.ach_account_id)
    item = db.scalar(select(Recurring).where(Recurring.id == id).with_for_update())
    if not item:
        raise HTTPException(404, 'Record not found.')
    if data.start_month != item.start_month:
        defaults = db.scalars(select(AmountChange).where(
            AmountChange.recurring_id == id, AmountChange.override == False,
        ).order_by(AmountChange.month)).all()
        # Keep every existing change on its calendar date. Establish an initial
        # default at the new start, including when extending a schedule earlier.
        if not any(c.month == data.start_month for c in defaults):
            earlier = [c for c in defaults if c.month <= data.start_month]
            baseline = earlier[-1] if earlier else defaults[0]
            db.add(AmountChange(recurring_id=id, month=data.start_month,
                                amount=baseline.amount, override=False))
    save(db, item, data.model_dump())
    record_due(db)
    return item

@app.put('/api/recurring/{id}/amount')
def change_amount(id: str, data: ChangeIn, db: DB):
    item = get(db, Recurring, id)
    if data.month < item.start_month or (item.end_month and data.month > item.end_month):
        raise HTTPException(422, 'Choose a month within this schedule.')
    if (data.override and item.frequency == 'annual' and item.kind == 'payable'
            and not item.distribute_annual and data.month[5:] != item.start_month[5:]):
        raise HTTPException(422, 'A one-month override for this annual expense must use its due month.')
    change = db.scalar(select(AmountChange).where(AmountChange.recurring_id == id, AmountChange.month == data.month, AmountChange.override == data.override))
    return save(db, change or AmountChange(recurring_id=id), data.model_dump())

@app.delete('/api/recurring/{id}/amount/{change_id}')
def delete_change(id: str, change_id: str, db: DB):
    item = get(db, Recurring, id)
    change = get(db, AmountChange, change_id)
    if change.recurring_id != id:
        raise HTTPException(404, 'Change not found.')
    if not change.override and change.month == item.start_month:
        raise HTTPException(422, 'The initial default amount cannot be removed.')
    db.delete(change); db.commit()
    return {'ok': True}

@app.delete('/api/recurring/{id}')
def delete_recurring(id: str, db: DB):
    db.delete(get(db, Recurring, id)); db.commit()
    return {'ok': True}

@app.get('/api/purchases')
def purchases(db: DB):
    return db.scalars(select(Purchase).order_by(Purchase.month, Purchase.name)).all()

@app.post('/api/purchases', status_code=201)
def create_purchase(data: PurchaseIn, db: DB):
    category(db, data.category_id)
    return save(db, Purchase(), data.model_dump())

@app.put('/api/purchases/{id}')
def edit_purchase(id: str, data: PurchaseIn, db: DB):
    category(db, data.category_id)
    return save(db, get(db, Purchase, id), data.model_dump())

@app.delete('/api/purchases/{id}')
def delete_purchase(id: str, db: DB):
    db.delete(get(db, Purchase, id)); db.commit()
    return {'ok': True}

@app.get('/api/forecast')
def month_forecast(month: Month, db: DB, preview: str | None = None):
    if preview:
        p = get(db, Purchase, preview)
        if p.month != month:
            raise HTTPException(422, 'Preview month must match the purchase.')
    result = forecast(db, month, preview=preview)
    actuals = actual(db, month)
    return {**result, 'actual': actuals, 'actual_deficit': actuals['expenses'] > result['income']}

@app.get('/api/trends')
def trends(end: Month, db: DB, category_ids: Annotated[list[str] | None, Query()] = None):
    selected = set(category_ids) if category_ids else None
    for id in selected or []:
        category(db, id)
    points = []
    cats = db.scalars(select(Category)).all()
    for offset in range(-11, 1):
        month = shift_month(end, offset)
        f, a = forecast(db, month, selected), actual(db, month, selected)
        by_category = {}
        for c in cats:
            if selected is None or c.id in selected:
                ca = actual(db, month, {c.id})
                by_category[c.id] = {'actual': None if a['status'] == 'missing' else ca['expenses'], 'forecast': forecast(db, month, {c.id})['expenses']}
        points.append({'month': month, 'forecast': f['expenses'], 'income': forecast(db, month)['income'], 'actual': None if a['status'] == 'missing' else a['expenses'], 'status': a['status'], 'categories': by_category})
    return points

@app.get('/api/expenses/breakdown')
def breakdown(start: date, end: date, db: DB, basis: Literal['actual', 'forecast'] = 'actual'):
    if start > end:
        raise HTTPException(422, 'Choose an end date on or after the start date.')
    if start.year < 1900 or end.year > 9998:
        raise HTTPException(422, 'Choose dates between 1900 and 9998.')
    if basis == 'forecast' and (start.day != 1 or end != month_end(month_key(end))):
        raise HTTPException(422, 'Planned expenses use full calendar months; choose the first and last day of the month.')
    return expense_breakdown(db, start, end, basis)


@app.put('/api/months/{month}')
def complete(month: Month, data: CompleteIn, db: DB):
    return save(db, db.get(MonthStatus, month) or MonthStatus(month=month), data.model_dump())

@app.get('/api/transactions')
def transactions(db: DB, month: Month | None = None, q: str = '', category_id: str | None = None):
    query = select(Transaction)
    if month:
        query = query.where(Transaction.date >= date.fromisoformat(month+'-01'), Transaction.date < date.fromisoformat(shift_month(month, 1)+'-01'))
    if q:
        query = query.where(Transaction.description.icontains(q, autoescape=True))
    if category_id:
        query = query.where(Transaction.category_id == category_id)
    return db.scalars(query.order_by(Transaction.date.desc(), Transaction.id)).all()

@app.post('/api/transactions', status_code=201)
def create_transaction(data: TransactionIn, db: DB):
    category(db, data.category_id); get(db, Account, data.account_id)
    item = Transaction(provenance={'manual': True}, **data.model_dump())
    db.add(item)
    learn_labels(db, [data.model_dump()])
    db.commit()
    return item

@app.put('/api/transactions/{id}')
def edit_transaction(id: str, data: TransactionIn, db: DB):
    category(db, data.category_id); get(db, Account, data.account_id)
    item = get(db, Transaction, id)
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    learn_labels(db, [data.model_dump()])
    db.commit()
    return item

@app.delete('/api/transactions/{id}')
def delete_transaction(id: str, db: DB):
    db.delete(get(db, Transaction, id)); db.commit()
    return {'ok': True}


def import_view(job):
    source = job.source
    return {**jsonable_encoder(job), 'source': {'type': source.get('type'), 'headers': source.get('headers', []), 'preview': source.get('records', [])[:5], 'mapping': source.get('mapping'), 'mapping_warning': source.get('mapping_warning')}, 'commit_summary': source.get('commit_summary')}

@app.get('/api/imports')
def imports(db: DB):
    return [{'id': j.id, 'filename': j.filename, 'status': j.status, 'period': j.period, 'account_id': j.account_id, 'error': j.error} for j in db.scalars(select(StatementImport).order_by(StatementImport.created_at.desc())).all()]

@app.post('/api/imports', status_code=201)
async def prepare_import(db: DB, account_id: Annotated[str, Form()], period: Annotated[Month, Form()], file: Annotated[UploadFile, File()]):
    get(db, Account, account_id)
    data = await file.read(15 * 1024 * 1024 + 1)
    await file.close()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, 'Statements must be smaller than 15 MB.')
    digest = sha256(data).hexdigest()
    if db.scalar(select(StatementImport.id).where(StatementImport.account_id == account_id, StatementImport.file_hash == digest)):
        raise HTTPException(409, 'This exact file was already uploaded for this account. Open its existing import to review or retry.')
    try:
        source = await asyncio.to_thread(prepare_file, file.filename or '', data)
    except Exception as exc:
        raise HTTPException(422, str(exc)[:1000])
    job = StatementImport(account_id=account_id, period=period, filename=Path(file.filename or 'statement').name[:200], file_hash=digest, source=source, rows=[])
    db.add(job)
    db.flush()
    apply_saved_mapping(db, job)
    db.commit()
    return import_view(job)

@app.get('/api/payee-rules')
def payee_rules(db: DB):
    return db.scalars(select(PayeeRule).order_by(PayeeRule.payee, PayeeRule.kind)).all()

@app.put('/api/payee-rules/{id}')
def edit_payee_rule(id: str, data: PayeeRuleIn, db: DB):
    get(db, Category, data.category_id)
    return save(db, get(db, PayeeRule, id), data.model_dump())

@app.delete('/api/payee-rules/{id}')
def forget_payee_rule(id: str, db: DB):
    db.delete(get(db, PayeeRule, id)); db.commit()
    return {'ok': True}

@app.post('/api/imports/{id}/categorize')
def categorize_from_payees(id: str, db: DB):
    job = db.scalar(select(StatementImport).where(StatementImport.id == id).with_for_update())
    if not job:
        raise HTTPException(404, 'Import not found.')
    if job.status in ('processing', 'committed', 'undone'):
        raise HTTPException(409, 'This import cannot be categorized now.')
    from copy import deepcopy
    job.rows = validate_rows(db, apply_payee_rules(db, deepcopy(job.rows)), job.account_id)
    job.status, job.error = 'review', ''
    db.commit()
    return import_view(job)

@app.get('/api/imports/{id}')
def get_import(id: str, db: DB):
    return import_view(get(db, StatementImport, id))

@app.post('/api/imports/{id}/mapping/default')
def use_card_mapping(id: str, db: DB):
    job = db.scalar(select(StatementImport).where(StatementImport.id == id).with_for_update())
    if not job:
        raise HTTPException(404, 'Import not found.')
    apply_saved_mapping(db, job)
    db.commit()
    return import_view(job)


@app.put('/api/imports/{id}/mapping')
def mapping(id: str, data: MappingIn, db: DB):
    job = db.scalar(select(StatementImport).where(StatementImport.id == id).with_for_update())
    if not job:
        raise HTTPException(404, 'Import not found.')
    if job.status in ('processing', 'committed', 'undone') or job.source.get('type') != 'csv':
        raise HTTPException(409, 'This import cannot be mapped now.')
    try:
        rows = csv_rows(job.source, data.model_dump(), job.period, get(db, Settings, 1).currency)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    job.source = {**{k: v for k, v in job.source.items() if k != 'model_used'}, 'mapping': data.model_dump(), 'mapping_warning':''}
    get(db, Account, job.account_id).csv_mapping = data.model_dump()
    job.rows = validate_rows(db, apply_payee_rules(db, rows), job.account_id)
    job.status = 'review'; job.error = ''
    db.commit()
    return import_view(job)

@app.post('/api/imports/{id}/process')
def start_processing(id: str, db: DB):
    job = db.scalar(select(StatementImport).where(StatementImport.id == id).with_for_update())
    if not job:
        raise HTTPException(404, 'Import not found.')
    if job.status in ('processing', 'committed', 'undone'):
        raise HTTPException(409, 'This import cannot be processed now.')
    if job.source.get('type') == 'csv' and not job.source.get('mapping'):
        raise HTTPException(422, 'Map CSV columns first.')
    job.status, job.error = 'processing', ''
    db.commit()
    executor.submit(process_import, id)
    return import_view(job)

@app.put('/api/imports/{id}/review')
def review(id: str, data: CommitIn, db: DB):
    job = db.scalar(select(StatementImport).where(StatementImport.id == id).with_for_update())
    if not job:
        raise HTTPException(404, 'Import not found.')
    if job.status in ('processing', 'committed', 'undone'):
        raise HTTPException(409, 'This import cannot be edited now.')
    rows = []
    for row in data.rows:
        index = row.get('source_index')
        source = job.rows[index].get('source', {}) if isinstance(index, int) and 0 <= index < len(job.rows) else {'manual_review': True}
        rows.append({k: v for k, v in row.items() if k in ('date', 'description', 'amount', 'kind', 'category_id', 'selected')} | {'source': source, 'classification': job.rows[index].get('classification') if isinstance(index, int) and 0 <= index < len(job.rows) and row.get('category_id') == job.rows[index].get('category_id') and row.get('kind') == job.rows[index].get('kind') else 'manual'})
    job.rows = validate_rows(db, rows, job.account_id)
    job.status = 'review'; db.commit()
    return import_view(job)

@app.post('/api/imports/{id}/commit')
def commit_import(id: str, db: DB):
    job = db.scalar(select(StatementImport).where(StatementImport.id == id).with_for_update())
    if not job:
        raise HTTPException(404, 'Import not found.')
    if job.status not in ('review', 'failed', 'interrupted'):
        raise HTTPException(409, 'Review this import before saving.')
    # Serialize commits for one card: a concurrent overlapping import must see
    # the first commit's original CSV rows before it decides which rows to save.
    db.scalar(select(Account).where(Account.id == job.account_id).with_for_update())
    rows = validate_rows(db, job.rows, job.account_id)
    selected = [r for r in rows if r.get('selected', True) and not r.get('skip_duplicate')]
    skipped = sum(bool(r.get('skip_duplicate')) for r in rows)
    if (not selected and not skipped) or any(r['errors'] for r in selected):
        raise HTTPException(422, 'Select at least one valid row and resolve all selected row errors.')
    for row in selected:
        data = TransactionIn.model_validate({**row, 'account_id': job.account_id})
        db.add(Transaction(**data.model_dump(), import_id=id, provenance={'source': row.get('source', {}), 'original_review': row, 'model': job.source.get('model_used', '')}))
    learn_labels(db, selected)
    job.rows = rows; job.source = {'type': job.source['type'], 'mapping': job.source.get('mapping'), 'commit_summary': {'added': len(selected), 'skipped': skipped}}
    job.status, job.error = 'committed', ''
    db.commit()
    return import_view(job)

@app.delete('/api/imports/{id}')
def delete_import(id: str, db: DB):
    job = db.scalar(select(StatementImport).where(StatementImport.id == id).with_for_update())
    if not job:
        raise HTTPException(404, 'Import not found.')
    if job.status == 'processing':
        raise HTTPException(409, 'Wait for processing to finish before deleting this import.')
    if job.status == 'committed' or db.scalar(select(Transaction.id).where(Transaction.import_id == id).limit(1)):
        raise HTTPException(409, 'Undo this import before deleting it so its saved transactions are removed explicitly.')
    db.delete(job)
    db.commit()
    return {'ok': True}


@app.post('/api/imports/{id}/undo')
def undo_import(id: str, db: DB):
    job = db.scalar(select(StatementImport).where(StatementImport.id == id).with_for_update())
    if not job or job.status != 'committed':
        raise HTTPException(409, 'Only committed imports can be undone.')
    db.execute(delete(Transaction).where(Transaction.import_id == id))
    job.status = 'undone'; db.commit()
    return import_view(job)

FRONTEND = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
if FRONTEND.exists():
    app.mount('/assets', StaticFiles(directory=FRONTEND/'assets'), name='assets')
    @app.get('/')
    def index():
        return FileResponse(FRONTEND/'index.html')
