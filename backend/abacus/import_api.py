import asyncio
from hashlib import sha256
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DBSession

from .api_helpers import get, save
from .classification import apply_payee_rules, learn_labels
from .csv_profiles import apply_saved_mapping
from .db import session
from .imports import csv_rows, executor, prepare_file, process_import, validate_rows
from .models import (
    Account,
    Category,
    PayeeRule,
    Settings,
    StatementImport,
    Transaction,
    uid,
)
from .provenance import compact_pdf_rows, expanded_sources
from .schemas import (
    CommitIn,
    MappingIn,
    Month,
    PayeeRuleIn,
    ProcessImportIn,
    TransactionIn,
)

router = APIRouter()
DB = Annotated[DBSession, Depends(session)]


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


@router.post("/api/imports", status_code=201)
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


@router.get("/api/payee-rules")
def payee_rules(db: DB):
    return db.scalars(select(PayeeRule).order_by(PayeeRule.payee, PayeeRule.kind)).all()


@router.put("/api/payee-rules/{id}")
def edit_payee_rule(id: str, data: PayeeRuleIn, db: DB):
    get(db, Category, data.category_id)
    return save(db, get(db, PayeeRule, id), data.model_dump())


@router.delete("/api/payee-rules/{id}")
def forget_payee_rule(id: str, db: DB):
    db.delete(get(db, PayeeRule, id))
    db.commit()
    return {"ok": True}


@router.post("/api/imports/{id}/categorize")
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


@router.get("/api/imports/{id}")
def get_import(id: str, db: DB):
    return import_view(get(db, StatementImport, id), db)


@router.post("/api/imports/{id}/mapping/default")
def use_card_mapping(id: str, db: DB):
    job = db.scalar(
        select(StatementImport).where(StatementImport.id == id).with_for_update()
    )
    if not job:
        raise HTTPException(404, "Import not found.")
    apply_saved_mapping(db, job)
    db.commit()
    return import_view(job, db)


@router.put("/api/imports/{id}/mapping")
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


@router.post("/api/imports/{id}/process")
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


@router.put("/api/imports/{id}/review")
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


@router.post("/api/imports/{id}/commit")
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


@router.delete("/api/imports/{id}")
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


@router.post("/api/imports/{id}/undo")
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
