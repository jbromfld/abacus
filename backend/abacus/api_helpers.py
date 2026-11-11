from fastapi import HTTPException

from .models import Category


def get(db, model, id):
    item = db.get(model, id)
    if item is None:
        raise HTTPException(404, "Record not found.")
    return item


def category(db, id):
    if id:
        get(db, Category, id)


def save(db, item, data):
    for key, value in data.items():
        setattr(item, key, value)
    db.add(item)
    db.commit()
    return item
