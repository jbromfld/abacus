"""User acknowledgements of monthly budget alerts; no financial records change."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .db import session
from .models import AlertDismissal
from .schemas import AlertDismissalIn

router = APIRouter(prefix="/api/alerts", tags=["alerts"])
DB = Annotated[Session, Depends(session)]


@router.get("/dismissals")
def list_dismissals(db: DB):
    return db.scalars(
        select(AlertDismissal).order_by(AlertDismissal.month, AlertDismissal.kind)
    ).all()


@router.post("/dismissals")
def dismiss_alert(data: AlertDismissalIn, db: DB):
    db.execute(
        insert(AlertDismissal)
        .values(**data.model_dump())
        .on_conflict_do_nothing(index_elements=["month", "kind"])
    )
    db.commit()
    return db.get(AlertDismissal, (data.month, data.kind))


@router.delete("/dismissals")
def restore_alerts(db: DB):
    result = db.execute(delete(AlertDismissal))
    db.commit()
    return {"restored": result.rowcount}
