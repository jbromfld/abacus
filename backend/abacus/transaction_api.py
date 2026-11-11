from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
)
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session as DBSession

from .api_helpers import category, get
from .classification import learn_labels
from .db import session
from .models import (
    Account,
    Transaction,
)
from .provenance import expanded_sources
from .schemas import (
    TransactionIn,
)

router = APIRouter()
DB = Annotated[DBSession, Depends(session)]


@router.get("/api/transactions/{id}")
def transaction_details(id: str, db: DB):
    item = get(db, Transaction, id)
    data = jsonable_encoder(item)
    value = dict(item.provenance)
    if item.import_id and isinstance(value.get("source"), dict):
        value["source"] = expanded_sources(db, item.import_id, [value["source"]])[0]
    data["provenance"] = value
    return data


@router.post("/api/transactions", status_code=201)
def create_transaction(data: TransactionIn, db: DB):
    category(db, data.category_id)
    get(db, Account, data.account_id)
    item = Transaction(provenance={"manual": True}, **data.model_dump())
    db.add(item)
    learn_labels(db, [data.model_dump()])
    db.commit()
    return item


@router.put("/api/transactions/{id}")
def edit_transaction(id: str, data: TransactionIn, db: DB):
    category(db, data.category_id)
    get(db, Account, data.account_id)
    item = get(db, Transaction, id)
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    learn_labels(db, [data.model_dump()])
    db.commit()
    return item


@router.delete("/api/transactions/{id}")
def delete_transaction(id: str, db: DB):
    db.delete(get(db, Transaction, id))
    db.commit()
    return {"ok": True}
