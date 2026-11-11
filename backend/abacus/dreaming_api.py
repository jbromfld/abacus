from copy import deepcopy
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
    return {
        "enabled": setting.advisor_dreaming_enabled,
        "epoch": memory_epoch(),
        "jobs": [
            {
                "id": j.id,
                "state": j.state,
                "reason": j.reason,
                "groups": j.payload.get("groups", []),
            }
            for j in jobs
        ],
        "pending_review": sum(
            g.get("state") == "review"
            for j in jobs
            for g in j.payload.get("groups", [])
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
        groups = [dict(g) for g in job.payload["groups"]]
        group = next(
            (
                g
                for g in groups
                if g["operation_key"] == operation and g["state"] == "review"
            ),
            None,
        )
        if not group:
            raise HTTPException(404, "Proposal not found.")
        if data.note:
            group["note"] = data.note.model_dump(mode="json")
        try:
            dreaming.apply(db, job, group, reviewed=True)
        except MemoryError as exc:
            raise HTTPException(
                {"conflict": 409, "invalid": 422}.get(exc.code, 503), str(exc)
            ) from None
        job.payload = {"groups": deepcopy(groups)}
        job.state = (
            "review" if any(g["state"] == "review" for g in groups) else "completed"
        )
        db.commit()
    return read(db)


@router.post("/undo/{operation}")
def undo(operation: str, data: dict, db: DB):
    with dreaming.gate:
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
        for job in db.scalars(select(MemoryDream)):
            groups = [dict(g) for g in job.payload.get("groups", [])]
            for group in groups:
                if group["operation_key"] == operation:
                    group["state"] = "undone"
            job.payload = {"groups": deepcopy(groups)}
        db.commit()
    return read(db)


@router.post("/{id}/{operation}/skip")
def skip(id: str, operation: str, db: DB):
    with dreaming.gate:
        job = db.get(MemoryDream, id)
        if not job:
            raise HTTPException(404, "Review no longer exists.")
        groups = deepcopy(job.payload.get("groups", []))
        group = next(
            (
                g
                for g in groups
                if g["operation_key"] == operation and g["state"] == "review"
            ),
            None,
        )
        if group is None:
            raise HTTPException(409, "Proposal is no longer awaiting review.")
        group["state"] = "skipped"
        group.pop("evidence", None)
        job.payload = {"groups": groups}
        job.state = (
            "review" if any(g["state"] == "review" for g in groups) else "completed"
        )
        db.commit()
    return read(db)
