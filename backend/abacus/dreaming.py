"""Optional Babar consumer: debounce, idle model adapter and scheduling handles.

Babar owns evidence, proposal policy and authorization checks. Nothing here
interprets model output or falls back to direct consolidation.
"""

from datetime import UTC, datetime, timedelta
from threading import Event, RLock

from sqlalchemy import delete, select

from .advisor_memory import MemoryError, memory_call, mutate_memory
from .db import Session
from .local_model import chat_with_model
from .model_activity import background_model
from .model_tracing import controller_event, model_workflow
from .models import MemoryDream, Settings

CAPABILITY = "dreaming-controller-v1"
gate = RLock()
_running = RLock()
_stopping = Event()


def start():
    _stopping.clear()


def stop():
    with gate:
        _stopping.set()


def enabled(setting):
    return (
        setting.advisor_dreaming_enabled
        and setting.advisor_memory_enabled
        and setting.advisor_enabled
        and bool(setting.model)
    )


def queue(db, immediate=False):
    if not enabled(db.get(Settings, 1, populate_existing=True)):
        return
    queued = db.scalar(
        select(MemoryDream)
        .where(MemoryDream.state == "queued")
        .order_by(MemoryDream.created_at)
    )
    due = datetime.now(UTC) + timedelta(seconds=0 if immediate else 60)
    if queued and not queued.payload:
        queued.due_at = due
    else:
        db.add(MemoryDream(due_at=due, payload={}))
    db.commit()


def _handles(groups):
    return [{"operation_key": g["operation_key"]} for g in groups]


def cancel(db, purge=False):
    setting = db.get(Settings, 1, populate_existing=True)
    for job in db.scalars(select(MemoryDream)):
        if job.state not in ("queued", "processing", "review"):
            continue
        if (
            job.payload.get("controller") == CAPABILITY
            and setting.advisor_memory_enabled
        ):
            for group in job.payload.get("groups", []):
                try:
                    memory_call(
                        True, "dream_cancel", operation_key=group["operation_key"]
                    )
                except MemoryError:
                    # Local cancellation is immediate; retry remote cleanup after reconnect.
                    pass
        job.state = "cancelled"
        job.payload = (
            {
                "controller": CAPABILITY,
                "groups": _handles(job.payload.get("groups", [])),
            }
            if job.payload.get("controller") == CAPABILITY
            else {}
        )
    if purge:
        db.execute(delete(MemoryDream))
    db.commit()


def apply(db, job, group, reviewed=False, note=None):
    if _stopping.is_set() or not enabled(db.get(Settings, 1, populate_existing=True)):
        raise MemoryError("conflict", "Dreaming is disabled or stopping.")
    if job.payload.get("controller") != CAPABILITY or job.state not in (
        "processing",
        "review",
    ):
        raise MemoryError("conflict", "Prepare a new Babar proposal first.")
    result = mutate_memory(
        "dream_commit",
        operation_key=group["operation_key"],
        reviewed=reviewed,
        note=note,
    )
    controller_event(job.id, group["operation_key"], "commit", result["state"])
    return result


def tick():
    if _stopping.is_set() or not _running.acquire(blocking=False):
        return
    try:
        run_pass()
    finally:
        _running.release()


@model_workflow("memory_dreaming")
def run_pass():
    with Session() as db:
        with gate:
            if not enabled(db.get(Settings, 1, populate_existing=True)):
                return
            # Retire legacy reviews even when there is no queued pass yet.
            retired = False
            for old in db.scalars(select(MemoryDream)):
                if old.payload and old.payload.get("controller") != CAPABILITY:
                    old.payload, old.state, old.reason = (
                        {},
                        "cancelled",
                        "Legacy proposal cancelled; prepare a fresh Babar review.",
                    )
                    retired = True
            if retired:
                db.commit()
                queue(db, immediate=True)
                return
            job = db.scalar(
                select(MemoryDream)
                .where(
                    MemoryDream.state.in_(["queued", "processing"]),
                    MemoryDream.due_at <= datetime.now(UTC),
                )
                .order_by(MemoryDream.created_at)
            )
            if not job:
                return
            identifier = job.id
            try:
                status = memory_call(True, "status")
                if CAPABILITY not in status.get("capabilities", []):
                    job.state, job.reason = (
                        "failed",
                        "Upgrade Babar for dreaming-controller-v1. Ordinary memory remains available.",
                    )
                    db.commit()
                    return
                for cancelled in db.scalars(
                    select(MemoryDream).where(MemoryDream.state == "cancelled")
                ):
                    if cancelled.payload.get("controller") == CAPABILITY:
                        for ref in cancelled.payload.get("groups", []):
                            try:
                                memory_call(
                                    True,
                                    "dream_cancel",
                                    operation_key=ref["operation_key"],
                                )
                            except MemoryError as exc:
                                if exc.code != "not_found":
                                    raise
                        cancelled.payload = {}
                if not job.payload:
                    prepared = memory_call(True, "dream_prepare", pass_key=identifier)
                    job.payload = {
                        "controller": CAPABILITY,
                        "groups": _handles(prepared["groups"]),
                    }
                    job.state = "processing"
                    db.commit()
                refs = list(job.payload["groups"])
            except MemoryError:
                job.reason = "Dreaming could not reach Babar. Saved memories are unchanged; retry after reconnecting."
                db.commit()
                return
        states = []
        for ref in refs:
            try:
                group = memory_call(
                    True, "dream_get", operation_key=ref["operation_key"]
                )
                if group["state"] == "prepared":
                    with gate:
                        setting = db.get(Settings, 1, populate_existing=True)
                        if not enabled(setting) or _stopping.is_set():
                            return
                        model = setting.model
                    with background_model() as idle:
                        if not idle:
                            return
                        request = group["model_request"]
                        raw = chat_with_model(
                            model, request["messages"], request["schema"]
                        )
                    with gate:
                        db.expire_all()
                        job = db.get(MemoryDream, identifier)
                        if (
                            not job
                            or job.state == "cancelled"
                            or _stopping.is_set()
                            or not enabled(db.get(Settings, 1, populate_existing=True))
                        ):
                            return
                        group = memory_call(
                            True,
                            "dream_evaluate",
                            operation_key=ref["operation_key"],
                            raw=raw,
                        )
                        controller_event(
                            identifier,
                            ref["operation_key"],
                            "validation",
                            group["state"],
                        )
                if group["state"] == "ready":
                    with gate:
                        db.expire_all()
                        job = db.get(MemoryDream, identifier)
                        group = apply(db, job, ref)
                states.append(group["state"])
            except Exception as exc:
                with gate:
                    db.expire_all()
                    job = db.get(MemoryDream, identifier)
                    if not job or job.state == "cancelled":
                        return
                    # The same handle is reconciled before retrying a possibly successful write.
                    if isinstance(exc, MemoryError) and exc.code in (
                        "conflict",
                        "invalid",
                        "not_found",
                    ):
                        job.state = "cancelled"
                        job.reason = "Babar rejected a stale or invalid proposal. Dream now to prepare fresh sources."
                    else:
                        job.reason = "Dreaming paused after a model or Babar error. Retry to reconcile the operation."
                    job.due_at = datetime.now(UTC) + timedelta(seconds=60)
                    db.commit()
                    return
        with gate:
            db.expire_all()
            job = db.get(MemoryDream, identifier)
            if (
                not job
                or job.state == "cancelled"
                or _stopping.is_set()
                or not enabled(db.get(Settings, 1, populate_existing=True))
            ):
                return
            job.state = "review" if "review" in states else "completed"
            job.reason = ""
            db.commit()
