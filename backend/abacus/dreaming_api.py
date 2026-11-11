from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import dreaming
from .advisor_memory import MemoryError, memory_epoch, mutate_memory
from .db import session
from .memory_types import MemoryNoteIn
from .models import MemoryDream, Settings

router = APIRouter(prefix="/api/advisor/dreaming")
DB = Annotated[Session, Depends(session)]


class Preference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class Approval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: MemoryNoteIn | None = None


@router.get("")
def read(db: DB):
    setting = db.get(Settings, 1)
    jobs = db.scalars(
        select(MemoryDream).order_by(MemoryDream.created_at.desc()).limit(25)
    ).all()
    items = []
    for job in jobs:
        groups = []
        reason = job.reason
        if (
            setting.advisor_memory_enabled
            and job.state != "cancelled"
            and job.payload.get("controller") == dreaming.CAPABILITY
        ):
            try:
                for ref in job.payload.get("groups", []):
                    group = dreaming.memory_call(
                        True, "dream_get", operation_key=ref["operation_key"]
                    )
                    group.pop("model_request", None)
                    group.pop("proposal", None)
                    groups.append(group)
            except MemoryError:
                reason = (
                    "Dreaming details are unavailable. Refresh after Babar reconnects."
                )
        items.append(dict(id=job.id, state=job.state, reason=reason, groups=groups))
    return {
        "enabled": setting.advisor_dreaming_enabled,
        "epoch": memory_epoch(),
        "jobs": items,
        "pending_review": sum(
            g["state"] == "review" for j in items for g in j["groups"]
        ),
    }


@router.put("")
def preference(data: Preference, db: DB):
    with dreaming.gate:
        setting = db.get(Settings, 1)
        if data.enabled and not (
            setting.advisor_enabled and setting.advisor_memory_enabled and setting.model
        ):
            raise HTTPException(
                409, "Enable advisor memory and choose a local advisor model first."
            )
        setting.advisor_dreaming_enabled = data.enabled
        db.commit()
        if data.enabled:
            dreaming.queue(db)
        else:
            dreaming.cancel(db)
    return read(db)


@router.post("/run")
def run(db: DB):
    with dreaming.gate:
        if not dreaming.enabled(db.get(Settings, 1)):
            raise HTTPException(409, "Enable dreaming first.")
        dreaming.queue(db, immediate=True)
    return read(db)


@router.post("/{id}/{operation}/approve")
def approve(id: str, operation: str, data: Approval, db: DB):
    with dreaming.gate:
        job = db.get(MemoryDream, id)
        if not job or job.state != "review":
            raise HTTPException(409, "Review is no longer available.")
        group = next(
            (
                g
                for g in job.payload.get("groups", [])
                if g["operation_key"] == operation
            ),
            None,
        )
        if not group:
            raise HTTPException(404, "Proposal not found.")
        try:
            dreaming.apply(
                db,
                job,
                group,
                reviewed=True,
                note=data.note.model_dump(mode="json") if data.note else None,
            )
            states = [
                dreaming.memory_call(
                    True, "dream_get", operation_key=g["operation_key"]
                )["state"]
                for g in job.payload["groups"]
            ]
        except MemoryError as exc:
            raise HTTPException(
                {"conflict": 409, "invalid": 422}.get(exc.code, 503), str(exc)
            ) from None
        job.state = "review" if "review" in states else "completed"
        db.commit()

    return read(db)


@router.post("/undo/{operation}")
def undo(operation: str, data: dict, db: DB):
    with dreaming.gate:
        if not db.get(Settings, 1).advisor_memory_enabled:
            raise HTTPException(409, "Enable memory first.")
        try:
            mutate_memory(
                "undo_consolidation",
                operation_key=operation,
                expected_revision=int(data["expected_revision"]),
            )
        except (ValueError, KeyError):
            raise HTTPException(422, "Expected revision required.") from None
        except MemoryError as exc:
            raise HTTPException(
                {"conflict": 409, "invalid": 422}.get(exc.code, 503), str(exc)
            ) from None

    return read(db)


@router.post("/{id}/{operation}/skip")
def skip(id: str, operation: str, db: DB):
    with dreaming.gate:
        job = db.get(MemoryDream, id)
        if not job:
            raise HTTPException(404, "Review no longer exists.")
        group = next(
            (
                g
                for g in job.payload.get("groups", [])
                if g["operation_key"] == operation
            ),
            None,
        )
        if not group or job.payload.get("controller") != dreaming.CAPABILITY:
            raise HTTPException(409, "Proposal is no longer awaiting review.")
        if not db.get(Settings, 1).advisor_memory_enabled:
            raise HTTPException(409, "Enable memory first.")
        try:
            dreaming.memory_call(True, "dream_cancel", operation_key=operation)
            states = [
                dreaming.memory_call(
                    True, "dream_get", operation_key=g["operation_key"]
                )["state"]
                for g in job.payload["groups"]
            ]
        except MemoryError as exc:
            raise HTTPException(503, str(exc)) from None
        job.state = "review" if "review" in states else "completed"
        db.commit()

    return read(db)
