"""Statement extraction proposes rows only; commit is a separate reviewed operation."""
import csv
from copy import deepcopy
import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
import pdfplumber
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from .db import Session
from .models import StatementImport, Category, Settings, Transaction
from .schemas import TransactionIn, Kind
from .local_model import ask_model, available_models, ollama_url
from .classification import apply_payee_rules, apply_description_defaults

executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='statement')
MAX_ROWS = 5000


class Extracted(BaseModel):
    date: str
    description: str
    amount: int = Field(ge=0, strict=True)
    kind: Kind
    page: int = Field(gt=0)

class Extraction(BaseModel):
    rows: list[Extracted] = Field(max_length=5000)


def prepare_file(filename, data):
    if filename.lower().endswith('.csv'):
        text = data.decode('utf-8-sig')
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=',;\t')
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        headers = reader.fieldnames
        if not headers or any(not h for h in headers) or len(set(headers)) != len(headers):
            raise ValueError('CSV needs unique, nonempty column headers.')
        rows = []
        for i, row in enumerate(reader):
            if i >= MAX_ROWS:
                raise ValueError('Statements are limited to 5,000 rows. Split this export first.')
            if None in row or any(v is None for v in row.values()):
                raise ValueError(f'CSV row {i+2} does not match its headers.')
            rows.append(row)
        if not rows:
            raise ValueError('The CSV has no transaction rows.')
        return {'type': 'csv', 'headers': headers, 'records': rows}
    if filename.lower().endswith('.pdf'):
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if len(pdf.pages) > 100:
                raise ValueError('Statements are limited to 100 pages.')
            pages = [{'page': i+1, 'text': p.extract_text() or ''} for i, p in enumerate(pdf.pages)]
            if not pages or any(not p['text'].strip() for p in pages):
                raise ValueError('This PDF contains scanned or empty pages. Export a text PDF or CSV; OCR is not supported.')
            if sum(len(p['text']) for p in pages) > 500_000:
                raise ValueError('Statement text is too large. Split this statement first.')
        return {'type': 'pdf', 'pages': pages}
    raise ValueError('Choose a CSV or a PDF with selectable text.')


def parse_amount(value, exponent=2, *, allow_zero=False):
    text = str(value).strip().replace(',', '')
    for symbol in ('$', '£', '€', '¥', 'CHF', 'USD', 'CAD', 'AUD'):
        text = text.replace(symbol, '').strip()
    if text.startswith('(') and text.endswith(')'):
        text = '-' + text[1:-1]
    try:
        number = Decimal(text)
        minor = number * (10 ** exponent)
        if not minor.is_finite() or minor != minor.to_integral_value() or (not minor and not allow_zero) or abs(minor) > 9_000_000_000_000:
            raise ValueError('Amount must be nonzero and match the currency precision.')
        return int(minor)
    except InvalidOperation as exc:
        raise ValueError('Amount could not be parsed.') from exc


def parse_date(value, fmt, period):
    if fmt != '%m/%d':
        return datetime.strptime(value.strip(), fmt).date().isoformat()
    # A December transaction on a January statement belongs to the previous year.
    year, month = map(int, period.split('-'))
    parsed = datetime.strptime(f'{year}/{value.strip()}', '%Y/%m/%d').date()
    candidates = [parsed.replace(year=y) for y in (year-1, year, year+1) if not (parsed.month == 2 and parsed.day == 29 and y % 4)]
    anchor = date(year, month, 1)
    return min(candidates, key=lambda d: abs((d-anchor).days)).isoformat()


def csv_rows(source, mapping, period, currency):
    headers = source['headers']
    for key in ('date_column', 'description_column', 'amount_column'):
        if mapping[key] not in headers:
            raise ValueError(f'Choose a valid {key.replace("_", " ")}.')
    rows = []
    for index, record in enumerate(source['records']):
        errors = []
        selected = True
        value = dict(date='', amount=0, description=record[mapping['description_column']].strip(), kind='purchase', category_id=None)
        try:
            value['date'] = parse_date(record[mapping['date_column']], mapping['date_format'], period)
        except (ValueError, TypeError):
            errors.append('Date could not be parsed; enter YYYY-MM-DD.')
        try:
            amount = parse_amount(record[mapping['amount_column']], 0 if currency == 'JPY' else 2, allow_zero=True)
            value['amount'] = abs(amount)
            selected = amount != 0
            # Card exports disagree on signs. Default to purchases unless the
            # user explicitly chooses a sign convention for charges and credits.
            positive_is = mapping.get('positive_is')
            if positive_is and amount != 0:
                value['kind'] = positive_is if amount > 0 else ('refund' if positive_is == 'purchase' else 'purchase')
        except ValueError as exc:
            errors.append(str(exc))
        rows.append({**value, 'selected': selected, 'errors': errors, 'source': {'row': index+2, 'original': record}})
    return apply_description_defaults(rows)


def csv_fields_key(source):
    """All original named CSV fields, with exact string values and no row number.

    Column order is irrelevant; case, whitespace, formatting, and unmapped
    columns remain significant. PDF source text and manual rows have no key.
    """
    original = source.get('original') if isinstance(source, dict) else None
    if not isinstance(original, dict) or not original or not all(isinstance(k, str) and isinstance(v, str) for k, v in original.items()):
        return None
    return json.dumps(original, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def validate_rows(db, rows, account_id):
    categories = set(db.scalars(select(Category.id)).all())
    seen = set()
    seen_csv = set()
    imported_csv = set()
    if any(csv_fields_key(row.get('source')) is not None for row in rows):
        for provenance in db.scalars(select(Transaction.provenance).where(Transaction.account_id == account_id, Transaction.import_id.is_not(None))).all():
            key = csv_fields_key(provenance.get('source', {}))
            if key is not None:
                imported_csv.add(key)
    result = []
    for row in rows:
        item = dict(row)
        raw_key = csv_fields_key(row.get('source'))
        item['skip_duplicate'] = raw_key is not None and raw_key in imported_csv
        item['duplicate'] = item['skip_duplicate'] or (raw_key is not None and raw_key in seen_csv)
        if raw_key is not None:
            seen_csv.add(raw_key)
        if item['skip_duplicate']:
            item['selected'] = False
        errors = []
        try:
            validated = TransactionIn.model_validate({**row, 'account_id': account_id})
            if validated.category_id and validated.category_id not in categories:
                errors.append('Select an existing category.')
            key = (validated.date, validated.description.casefold(), validated.amount, validated.kind)
            existing = None
            if raw_key is None:
                existing = db.scalar(select(Transaction.id).where(Transaction.account_id == account_id, Transaction.date == validated.date, Transaction.description.ilike(validated.description.replace('%', '\\%').replace('_', '\\_')), Transaction.amount == validated.amount, Transaction.kind == validated.kind).limit(1))
            item['duplicate'] = bool(item['duplicate'] or existing or key in seen)
            seen.add(key)
        except ValidationError as exc:
            errors.extend(f'{".".join(map(str, e["loc"]))}: {e["msg"]}' for e in exc.errors())
        item['errors'] = errors
        result.append(item)
    return result


def process_import(import_id):
    with Session() as db:
        job = db.get(StatementImport, import_id)
        if not job or job.status != 'processing':
            return
        settings = db.get(Settings, 1)
        model = settings.model
        job.source = {**job.source, 'model_used': model if job.source['type'] == 'pdf' else ''}
        rows = job.rows or []
        try:
            if job.source['type'] == 'csv':
                # CSV categorization is entirely local: remembered labels and manual review.
                rows = deepcopy(job.rows) or csv_rows(job.source, job.source['mapping'], job.period, settings.currency)
                apply_payee_rules(db, rows)
                job.rows = validate_rows(db, deepcopy(rows), job.account_id)
                db.commit()
            else:
                rows = []
                for page in job.source['pages']:
                    answer = Extraction.model_validate(ask_model(model, json.dumps({'task': 'Extract individual transactions, excluding summaries and balances. Return ISO dates and positive integer minor-unit amounts. Identify payment, transfer, refund, fee, purchase. Use the statement period to resolve years.', 'period': job.period, 'currency': settings.currency, 'minor_unit_digits': 0 if settings.currency == 'JPY' else 2, 'page': page}), Extraction.model_json_schema()))
                    for r in answer.rows:
                        if r.page != page['page']:
                            raise ValueError('Model returned a page reference outside the current page.')
                        rows.append({**r.model_dump(exclude={'page'}), 'selected': r.amount != 0, 'category_id': None, 'source': {'page': page['page'], 'original': page['text']}})
                    if len(rows) > MAX_ROWS:
                        raise ValueError('Statement exceeds 5,000 transactions.')
                if not rows:
                    raise ValueError('No transactions were extracted. Use a CSV export or add review rows manually.')
            job.rows = validate_rows(db, apply_payee_rules(db, rows), job.account_id)
            job.status, job.error = 'review', ''
        except Exception as exc:
            job.rows = validate_rows(db, rows, job.account_id)
            job.status = 'failed'
            job.error = f'Processing failed: {str(exc)[:1500]}. You can retry or correct the review rows manually.'
        db.commit()
