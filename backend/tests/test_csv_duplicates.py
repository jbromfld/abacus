from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from abacus.models import Category
from sqlalchemy import select
from test_imports import MAPPING, prepare


def review_csv(client, account, category, content):
    job = prepare(client, account, content)
    mapped = client.put("/api/imports/" + job["id"] + "/mapping", json=MAPPING)
    assert mapped.status_code == 200, mapped.text
    rows = [
        {**row, "source_index": i, "category_id": category}
        for i, row in enumerate(mapped.json()["rows"])
    ]
    response = client.put("/api/imports/" + job["id"] + "/review", json={"rows": rows})
    assert response.status_code == 200, response.text
    return response.json()


def commit(client, job):
    response = client.post("/api/imports/" + job["id"] + "/commit")
    assert response.status_code == 200, response.text
    return response.json()


TOLLS = b"Date,Description,Amount,Reference\n2025-12-01,Bridge toll,5.00,bridge\n2025-12-01,Bridge toll,5.00,bridge\n"


def test_same_file_repeats_are_flagged_and_both_saved(client, account_id, category_id):
    job = review_csv(client, account_id, category_id, TOLLS)
    assert not job["rows"][0]["duplicate"] and job["rows"][1]["duplicate"]
    assert all(row["selected"] and not row["skip_duplicate"] for row in job["rows"])
    result = commit(client, job)
    assert result["commit_summary"] == {"added": 2, "skipped": 0}
    assert len(client.get("/api/transactions").json()) == 2


def test_overlapping_import_skips_all_exact_matches_even_if_checked(
    client, account_id, category_id
):
    first = commit(client, review_csv(client, account_id, category_id, TOLLS))
    # Different bytes/line endings permit a separate import; CSV field values match.
    overlap = review_csv(client, account_id, category_id, TOLLS.replace(b"\n", b"\r\n"))
    assert all(row["skip_duplicate"] and not row["selected"] for row in overlap["rows"])
    forced = [
        {**row, "selected": True, "source_index": i}
        for i, row in enumerate(overlap["rows"])
    ]
    response = client.put(
        "/api/imports/" + overlap["id"] + "/review", json={"rows": forced}
    )
    assert all(not row["selected"] for row in response.json()["rows"])
    result = commit(client, overlap)
    assert result["commit_summary"] == {"added": 0, "skipped": 2}
    assert len(client.get("/api/transactions").json()) == 2
    assert client.post("/api/imports/" + overlap["id"] + "/undo").status_code == 200
    remaining = client.get("/api/transactions").json()
    assert len(remaining) == 2 and all(t["import_id"] == first["id"] for t in remaining)


def test_partial_overlap_skips_known_rows_and_saves_new_repeats(
    client, account_id, category_id
):
    first = b"Date,Description,Amount,Reference\n2025-12-01,Bridge toll,5.00,bridge\n"
    commit(client, review_csv(client, account_id, category_id, first))
    content = TOLLS + b"2025-12-02,Coffee,3.00,cafe\n2025-12-02,Coffee,3.00,cafe\n"
    job = review_csv(client, account_id, category_id, content)
    result = commit(client, job)
    assert result["commit_summary"] == {"added": 2, "skipped": 2}
    assert len(client.get("/api/transactions").json()) == 3


def test_all_csv_columns_must_equal_including_unmapped_values(
    client, account_id, category_id
):
    first = b"Date,Description,Amount,Reference\n2025-12-01,Bridge toll,5.00,outbound\n"
    commit(client, review_csv(client, account_id, category_id, first))
    changed = first.replace(b"outbound", b"inbound")
    job = review_csv(client, account_id, category_id, changed)
    assert not job["rows"][0]["skip_duplicate"]
    assert commit(client, job)["commit_summary"]["added"] == 1
    assert len(client.get("/api/transactions").json()) == 2


def test_column_order_is_ignored_but_original_values_are_exact(
    client, account_id, category_id
):
    first = b"Date,Description,Amount,Reference\n2025-12-01,Bridge toll,5.00,bridge\n"
    commit(client, review_csv(client, account_id, category_id, first))
    reordered = (
        b"Reference,Amount,Description,Date\nbridge,5.00,Bridge toll,2025-12-01\n"
    )
    assert commit(client, review_csv(client, account_id, category_id, reordered))[
        "commit_summary"
    ] == {"added": 0, "skipped": 1}
    for suffix, description, amount in [
        ("whitespace", "Bridge toll ", "5.00"),
        ("case", "bridge toll", "5.00"),
        ("format", "Bridge toll", "5.0"),
    ]:
        content = f"Date,Description,Amount,Reference\n2025-12-01,{description},{amount},bridge\n".encode()
        assert (
            commit(client, review_csv(client, account_id, category_id, content))[
                "commit_summary"
            ]["added"]
            == 1
        ), suffix
    assert len(client.get("/api/transactions").json()) == 4


def test_different_cards_do_not_skip_and_saved_edits_are_not_overwritten(
    client, account_id, category_id, db
):
    content = b"Date,Description,Amount\n2025-12-01,Grocer,12.50\n"
    commit(client, review_csv(client, account_id, category_id, content))
    transaction = client.get("/api/transactions").json()[0]
    other = db.scalar(select(Category.id).where(Category.id != category_id))
    client.put(
        "/api/transactions/" + transaction["id"],
        json={
            **transaction,
            "category_id": other,
            "description": "Corrected payee",
            "amount": 1500,
        },
    )
    overlap = commit(
        client,
        review_csv(client, account_id, category_id, content.replace(b"\n", b"\r\n")),
    )
    assert overlap["commit_summary"]["skipped"] == 1
    saved = client.get("/api/transactions").json()[0]
    assert (
        saved["category_id"] == other
        and saved["amount"] == 1500
        and saved["description"] == "Corrected payee"
    )
    account2 = client.post("/api/accounts", json={"name": "Other card"}).json()["id"]
    assert (
        commit(client, review_csv(client, account2, category_id, content))[
            "commit_summary"
        ]["added"]
        == 1
    )
    assert len(client.get("/api/transactions").json()) == 2


def test_skip_rechecked_at_commit_for_stale_reviews(client, account_id, category_id):
    content = b"Date,Description,Amount\n2025-12-01,Grocer,12.50\n"
    first = review_csv(client, account_id, category_id, content)
    second = review_csv(
        client, account_id, category_id, content.replace(b"\n", b"\r\n")
    )
    assert not second["rows"][0]["skip_duplicate"]
    assert commit(client, first)["commit_summary"]["added"] == 1
    assert commit(client, second)["commit_summary"] == {"added": 0, "skipped": 1}
    assert len(client.get("/api/transactions").json()) == 1


def test_concurrent_overlapping_commits_are_serialized_per_card(
    client, account_id, category_id
):
    content = b"Date,Description,Amount\n2025-12-01,Grocer,12.50\n"
    first = review_csv(client, account_id, category_id, content)
    second = review_csv(
        client, account_id, category_id, content.replace(b"\n", b"\r\n")
    )
    barrier = Barrier(2)

    def save(job):
        barrier.wait(timeout=10)
        return commit(client, job)["commit_summary"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(save, [first, second]))
    assert sum(o["added"] for o in outcomes) == 1
    assert sum(o["skipped"] for o in outcomes) == 1
    assert len(client.get("/api/transactions").json()) == 1


def test_duplicate_validation_queries_are_batched(db, account_id, category_id):
    from datetime import date

    from abacus.db import engine
    from abacus.imports import validate_rows
    from abacus.models import Transaction
    from sqlalchemy import event

    db.add(
        Transaction(
            date=date(2026, 1, 2),
            description="Literal 100%_Store",
            amount=100,
            kind="purchase",
            category_id=category_id,
            account_id=account_id,
        )
    )
    db.commit()
    statements = []

    def count(connection, cursor, statement, parameters, context, many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        rows = validate_rows(
            db,
            [
                dict(
                    date="2026-01-02",
                    description="literal 100%_store",
                    amount=100,
                    kind="purchase",
                    category_id=category_id,
                )
                for _ in range(5000)
            ],
            account_id,
        )
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert rows[0]["duplicate"]
    assert all(row["duplicate"] for row in rows)
    assert len(statements) <= 4
