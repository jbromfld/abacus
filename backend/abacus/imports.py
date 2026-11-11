"""Statement extraction proposes rows only; commit is a separate reviewed operation."""

import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pdfplumber
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import Text, cast, func, select, tuple_
from sqlalchemy.dialects.postgresql import ARRAY

from .classification import apply_description_defaults, apply_payee_rules
from .db import Session
from .local_model import ask_model
from .model_tracing import model_workflow
from .models import Category, Settings, StatementImport, Transaction
from .schemas import Kind, TransactionIn
from .source_keys import csv_fields_key, fingerprint

executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="statement")
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
    if filename.lower().endswith(".csv"):
        text = data.decode("utf-8-sig")
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        headers = reader.fieldnames
        if (
            not headers
            or any(not h for h in headers)
            or len(set(headers)) != len(headers)
        ):
            raise ValueError("CSV needs unique, nonempty column headers.")
        rows = []
        for i, row in enumerate(reader):
            if i >= MAX_ROWS:
                raise ValueError(
                    "Statements are limited to 5,000 rows. Split this export first."
                )
            if None in row or any(v is None for v in row.values()):
                raise ValueError(f"CSV row {i + 2} does not match its headers.")
            rows.append(row)
        if not rows:
            raise ValueError("The CSV has no transaction rows.")
        return {"type": "csv", "headers": headers, "records": rows}
    if filename.lower().endswith(".pdf"):
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if len(pdf.pages) > 100:
                raise ValueError("Statements are limited to 100 pages.")
            pages = [
                {"page": i + 1, "text": p.extract_text() or ""}
                for i, p in enumerate(pdf.pages)
            ]
            if not pages or any(not p["text"].strip() for p in pages):
                raise ValueError(
                    "This PDF contains scanned or empty pages. Export a text PDF or CSV; OCR is not supported."
                )
            if sum(len(p["text"]) for p in pages) > 500_000:
                raise ValueError(
                    "Statement text is too large. Split this statement first."
                )
        return {"type": "pdf", "pages": pages}
    raise ValueError("Choose a CSV or a PDF with selectable text.")


def parse_amount(value, exponent=2, *, allow_zero=False):
    text = str(value).strip().replace(",", "")
    for symbol in ("$", "£", "€", "¥", "CHF", "USD", "CAD", "AUD"):
        text = text.replace(symbol, "").strip()
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        number = Decimal(text)
        minor = number * (10**exponent)
        if (
            not minor.is_finite()
            or minor != minor.to_integral_value()
            or (not minor and not allow_zero)
            or abs(minor) > 9_000_000_000_000
        ):
            raise ValueError("Amount must be nonzero and match the currency precision.")
        return int(minor)
    except InvalidOperation as exc:
        raise ValueError("Amount could not be parsed.") from exc


def parse_date(value, fmt, period):
    if fmt != "%m/%d":
        return datetime.strptime(value.strip(), fmt).date().isoformat()
    # A December transaction on a January statement belongs to the previous year.
    year, month = map(int, period.split("-"))
    parsed = datetime.strptime(f"{year}/{value.strip()}", "%Y/%m/%d").date()
    candidates = [
        parsed.replace(year=y)
        for y in (year - 1, year, year + 1)
        if not (parsed.month == 2 and parsed.day == 29 and y % 4)
    ]
    anchor = date(year, month, 1)
    return min(candidates, key=lambda d: abs((d - anchor).days)).isoformat()


def csv_rows(source, mapping, period, currency):
    headers = source["headers"]
    for key in ("date_column", "description_column", "amount_column"):
        if mapping[key] not in headers:
            raise ValueError(f"Choose a valid {key.replace('_', ' ')}.")
    rows = []
    for index, record in enumerate(source["records"]):
        errors = []
        selected = True
        value = dict(
            date="",
            amount=0,
            description=record[mapping["description_column"]].strip(),
            kind="purchase",
            category_id=None,
        )
        try:
            value["date"] = parse_date(
                record[mapping["date_column"]], mapping["date_format"], period
            )
        except (ValueError, TypeError):
            errors.append("Date could not be parsed; enter YYYY-MM-DD.")
        try:
            amount = parse_amount(
                record[mapping["amount_column"]],
                0 if currency == "JPY" else 2,
                allow_zero=True,
            )
            value["amount"] = abs(amount)
            selected = amount != 0
            # Card exports disagree on signs. Default to purchases unless the
            # user explicitly chooses a sign convention for charges and credits.
            positive_is = mapping.get("positive_is")
            if positive_is and amount != 0:
                value["kind"] = (
                    positive_is
                    if amount > 0
                    else ("refund" if positive_is == "purchase" else "purchase")
                )
        except ValueError as exc:
            errors.append(str(exc))
        rows.append(
            {
                **value,
                "selected": selected,
                "errors": errors,
                "source": {"row": index + 2, "original": record},
            }
        )
    return apply_description_defaults(rows)


def validate_rows(db, rows, account_id):
    categories = set(db.scalars(select(Category.id)).all())
    seen = set()
    seen_csv = set()
    imported_csv = set()
    raw_keys = {
        key for row in rows if (key := csv_fields_key(row.get("source"))) is not None
    }

    hashes = sorted({fingerprint(key) for key in raw_keys})
    for offset in range(0, len(hashes), 500):
        for provenance in db.scalars(
            select(Transaction.provenance).where(
                Transaction.account_id == account_id,
                Transaction.import_id.is_not(None),
                Transaction.csv_fingerprint.in_(hashes[offset : offset + 500]),
            )
        ):
            key = csv_fields_key(provenance.get("source", {}))
            if key in raw_keys:
                imported_csv.add(key)
    # Narrow candidates using indexed account/date plus amount/type. Keep the
    # database's case-insensitive matching semantics rather than Python casefold.
    candidates = set()
    for row in rows:
        if csv_fields_key(row.get("source")) is not None:
            continue
        try:
            value = TransactionIn.model_validate({**row, "account_id": account_id})
            candidates.add((value.date, value.amount, value.kind))
        except ValidationError:
            pass
    existing_keys = set()
    candidates = sorted(candidates)
    for offset in range(0, len(candidates), 500):
        matches = db.execute(
            select(
                Transaction.date,
                func.lower(Transaction.description).label("description"),
                Transaction.amount,
                Transaction.kind,
            ).where(
                Transaction.account_id == account_id,
                tuple_(Transaction.date, Transaction.amount, Transaction.kind).in_(
                    candidates[offset : offset + 500]
                ),
            )
        ).all()
        existing_keys.update(tuple(m) for m in matches)
    description_values = sorted(
        {
            str(r.get("description", "")).strip()
            for r in rows
            if csv_fields_key(r.get("source")) is None
        }
    )
    normalized = {}
    for offset in range(0, len(description_values), 500):
        values = description_values[offset : offset + 500]
        normalized.update(
            db.execute(
                select(
                    func.unnest(cast(values, ARRAY(Text))),
                    func.lower(func.unnest(cast(values, ARRAY(Text)))),
                )
            ).all()
        )
    result = []
    for row in rows:
        item = dict(row)
        raw_key = csv_fields_key(row.get("source"))
        item["skip_duplicate"] = raw_key is not None and raw_key in imported_csv
        item["duplicate"] = item["skip_duplicate"] or (
            raw_key is not None and raw_key in seen_csv
        )
        if raw_key is not None:
            seen_csv.add(raw_key)
        if item["skip_duplicate"]:
            item["selected"] = False
        errors = []
        try:
            validated = TransactionIn.model_validate({**row, "account_id": account_id})
            if validated.category_id and validated.category_id not in categories:
                errors.append("Select an existing category.")
            key = (
                validated.date,
                validated.description.casefold(),
                validated.amount,
                validated.kind,
            )
            existing = (
                raw_key is None
                and (
                    validated.date,
                    normalized.get(validated.description, validated.description),
                    validated.amount,
                    validated.kind,
                )
                in existing_keys
            )
            item["duplicate"] = bool(item["duplicate"] or existing or key in seen)
            seen.add(key)
        except ValidationError as exc:
            errors.extend(
                f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()
            )
        item["errors"] = errors
        result.append(item)
    return result


@model_workflow("statement_import")
def process_import(import_id, token=None):
    # Release the database connection while the local model works.
    with Session() as db:
        job = db.get(StatementImport, import_id)
        if not job or job.status != "processing":
            return
        if token is not None and token != job.processing_token:
            return
        expected_token = token or job.processing_token
        source = deepcopy(job.source)
        previous = deepcopy(job.rows or [])
        period = job.period
        account_id = job.account_id
        settings = db.get(Settings, 1)
        model = settings.model
        currency = settings.currency
    candidates = []
    failure = None
    try:
        if source["type"] == "csv":
            candidates = deepcopy(previous) or csv_rows(
                source, source["mapping"], period, currency
            )
        else:
            for page in source["pages"]:
                answer = Extraction.model_validate(
                    ask_model(
                        model,
                        json.dumps(
                            {
                                "task": "Extract individual transactions, excluding summaries and balances. Return ISO dates and positive integer minor-unit amounts. Identify payment, transfer, refund, fee, purchase. Use the statement period to resolve years.",
                                "period": period,
                                "currency": currency,
                                "minor_unit_digits": 0 if currency == "JPY" else 2,
                                "page": page,
                            }
                        ),
                        Extraction.model_json_schema(),
                    )
                )
                for row in answer.rows:
                    if row.page != page["page"]:
                        raise ValueError(
                            "Model returned a page reference outside the current page."
                        )
                    candidates.append(
                        {
                            **row.model_dump(exclude={"page"}),
                            "selected": row.amount != 0,
                            "category_id": None,
                            "source": {"page": page["page"], "original": page["text"]},
                        }
                    )
                if len(candidates) > MAX_ROWS:
                    raise ValueError("Statement exceeds 5,000 transactions.")
            if not candidates:
                raise ValueError(
                    "No transactions were extracted. Use a CSV export or add review rows manually."
                )
    except Exception as exc:
        failure = f"Processing failed: {str(exc)[:1500]}. You can retry or correct the review rows manually."
    with Session() as db:
        job = db.scalar(
            select(StatementImport)
            .where(StatementImport.id == import_id)
            .with_for_update()
        )
        if (
            not job
            or job.status != "processing"
            or job.processing_token != expected_token
        ):
            return
        rows = previous if failure and previous else candidates
        job.rows = validate_rows(
            db,
            rows if failure and previous else apply_payee_rules(db, rows),
            account_id,
        )
        job.source = {
            **job.source,
            "model_used": model if source["type"] == "pdf" else "",
        }
        job.status, job.error = ("failed", failure) if failure else ("review", "")
        job.processing_token = None
        db.commit()
