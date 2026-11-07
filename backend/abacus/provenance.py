"""Keep shared PDF text once; expand it only when explicitly reviewing sources."""

from copy import deepcopy

from sqlalchemy import select

from .models import ImportPage


def compact_pdf_rows(db, job, rows):
    if job.source.get("type") != "pdf":
        return rows
    pages = {
        p.number: p
        for p in db.scalars(select(ImportPage).where(ImportPage.import_id == job.id))
    }
    result = deepcopy(rows)
    for row in result:
        source = row.get("source", {})
        number = source.get("page")
        text = source.get("original")
        if type(number) is not int or not isinstance(text, str):
            continue
        existing = pages.get(number)
        if existing is not None and existing.text != text:
            continue
        if existing is None:
            pages[number] = ImportPage(import_id=job.id, number=number, text=text)
            db.add(pages[number])
        row["source"] = {
            key: value for key, value in source.items() if key != "original"
        }
    return result


def expanded_sources(db, import_id, sources):
    pages = None
    result = []
    for original in sources:
        source = dict(original)
        if type(source.get("page")) is int and "original" not in source:
            if pages is None:
                pages = {
                    p.number: p.text
                    for p in db.scalars(
                        select(ImportPage).where(ImportPage.import_id == import_id)
                    )
                }
            if source["page"] in pages:
                source["original"] = pages[source["page"]]
        result.append(source)
    return result
