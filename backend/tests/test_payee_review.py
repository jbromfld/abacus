import json
from datetime import date

import pytest
from abacus import payee_review
from abacus.classification import apply_payee_rules, learn_labels
from abacus.models import (
    Category,
    PayeeGroup,
    PayeeRule,
    Settings,
    Transaction,
)
from sqlalchemy import func, select


@pytest.fixture
def aliases(db, category_id, monkeypatch):
    category2 = db.scalar(select(Category.id).where(Category.id != category_id))
    rows = [
        PayeeRule(payee="wholefds ann arbor", kind="purchase", category_id=category_id),
        PayeeRule(payee="whole foods detroit", kind="purchase", category_id=category2),
    ]
    db.add_all(rows)
    setting = db.get(Settings, 1)
    setting.model = "synthetic-local"
    db.commit()
    monkeypatch.setattr(payee_review.executor, "submit", lambda fn, *args: fn(*args))

    def model(_model, messages, **kwargs):
        records = json.loads(messages[-1]["content"])
        assert all(
            set(row) == {"id", "payee", "kind", "category_id", "category", "group_name"}
            for row in records
        )
        return json.dumps(
            {
                "groups": [
                    dict(
                        name="Whole Foods",
                        member_ids=[row["id"] for row in records],
                        category_id=None,
                        reason="Shared merchant spelling and location variants.",
                    )
                ]
            }
        )

    monkeypatch.setattr(payee_review, "chat_with_model", model)
    return rows


def preview(client):
    response = client.post("/api/payee-review/reviews")
    assert response.status_code == 202, response.text
    result = client.get("/api/payee-review/reviews/" + response.json()["id"]).json()
    assert result["status"] == "ready", result
    return result


def approval(review, category=None):
    group = review["suggestions"][0]
    return {
        "groups": [
            dict(
                suggestion_id=group["id"],
                name="Whole Foods",
                member_ids=group["member_ids"],
                category_id=category,
            )
        ]
    }


def test_preview_does_not_change_rules_and_apply_preserves_category_conflicts(
    client, db, aliases
):
    before = [(row.id, row.category_id) for row in aliases]
    review = preview(client)
    assert review["suggestions"][0]["category_conflict"]
    assert db.scalar(select(func.count()).select_from(PayeeGroup)) == 0
    assert all(row.group_id is None for row in db.scalars(select(PayeeRule)))
    assert [(row.id, row.category_id) for row in aliases] == before
    response = client.post(
        "/api/payee-review/reviews/" + review["id"] + "/apply", json=approval(review)
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "applied"
    db.expire_all()
    assert [(row.id, row.category_id) for row in aliases] == before
    assert len({row.group_id for row in aliases}) == 1 and aliases[0].group_id
    # An ambiguous canonical name must not force all purchases into one category.
    row = apply_payee_rules(db, [dict(description="Whole Foods", kind="purchase")])[0]
    assert row.get("category_id") is None
    exact = apply_payee_rules(
        db, [dict(description=aliases[1].payee, kind="purchase")]
    )[0]
    assert exact["category_id"] == aliases[1].category_id


def test_explicit_shared_category_affects_future_matching_only_and_apply_is_idempotent(
    client, db, aliases, account_id, category_id
):
    transaction = Transaction(
        date=date(2026, 11, 1),
        description=aliases[1].payee,
        amount=1234,
        kind="purchase",
        category_id=aliases[1].category_id,
        account_id=account_id,
        provenance={"original": "untouched"},
    )
    db.add(transaction)
    db.commit()
    before = (
        transaction.category_id,
        transaction.description,
        transaction.amount,
        transaction.provenance,
    )
    review = preview(client)
    payload = approval(review, category_id)
    for _ in range(2):
        response = client.post(
            "/api/payee-review/reviews/" + review["id"] + "/apply", json=payload
        )
        assert response.status_code == 200, response.text
    assert db.scalar(select(func.count()).select_from(PayeeGroup)) == 1
    db.expire_all()
    assert (
        transaction.category_id,
        transaction.description,
        transaction.amount,
        transaction.provenance,
    ) == before
    assert (
        apply_payee_rules(db, [dict(description="Whole Foods", kind="purchase")])[0][
            "category_id"
        ]
        == category_id
    )
    assert (
        apply_payee_rules(db, [dict(description="Whole Foods", kind="refund")])[0].get(
            "category_id"
        )
        is None
    )
    corrected = next(c.id for c in db.scalars(select(Category)) if c.id != category_id)
    learn_labels(
        db, [dict(description=aliases[0].payee, kind="purchase", category_id=corrected)]
    )
    db.commit()
    db.expire_all()
    assert aliases[0].group_id is not None
    assert (
        apply_payee_rules(db, [dict(description=aliases[0].payee, kind="purchase")])[0][
            "category_id"
        ]
        == corrected
    )
    assert (
        apply_payee_rules(db, [dict(description="Whole Foods", kind="purchase")])[
            0
        ].get("category_id")
        is None
    )


@pytest.mark.parametrize("change", ["edit", "forget"])
def test_stale_preview_is_rejected_atomically(client, db, aliases, category_id, change):
    review = preview(client)
    if change == "edit":
        client.put(
            "/api/payee-rules/" + aliases[1].id, json={"category_id": category_id}
        )
    else:
        client.delete("/api/payee-rules/" + aliases[1].id)
    response = client.post(
        "/api/payee-review/reviews/" + review["id"] + "/apply", json=approval(review)
    )
    assert response.status_code == 409, response.text
    assert db.scalar(select(func.count()).select_from(PayeeGroup)) == 0
    assert all(row.group_id is None for row in db.scalars(select(PayeeRule)))


def test_review_can_exclude_members_rename_and_ungroup_without_forgetting_aliases(
    client, db, aliases, category_id
):
    extra = PayeeRule(payee="wholefoods east", kind="purchase", category_id=category_id)
    db.add(extra)
    db.commit()
    review = preview(client)
    payload = approval(review)
    payload["groups"][0]["member_ids"] = [row.id for row in aliases]
    payload["groups"][0]["name"] = "Reviewed Whole Foods"
    response = client.post(
        "/api/payee-review/reviews/" + review["id"] + "/apply", json=payload
    )
    assert response.status_code == 200, response.text
    group_id = response.json()["result"]["group_ids"][0]
    assert (
        client.put(
            "/api/payee-review/groups/" + group_id, json={"name": "Whole Foods"}
        ).status_code
        == 200
    )
    assert client.delete("/api/payee-review/groups/" + group_id).status_code == 200
    db.expire_all()
    assert len(db.scalars(select(PayeeRule)).all()) == 3
    assert all(row.group_id is None for row in db.scalars(select(PayeeRule)))
    assert db.scalar(select(func.count()).select_from(PayeeGroup)) == 0


@pytest.mark.parametrize(
    "invalid", ["invented", "duplicate", "category", "regex", "mixed_kind"]
)
def test_invalid_model_proposals_never_change_memory(
    client, db, aliases, monkeypatch, invalid
):
    if invalid == "mixed_kind":
        aliases[1].kind = "refund"
        db.commit()
        # Force a deliberately malformed candidate to exercise the trust boundary.
        monkeypatch.setattr(
            payee_review, "candidate_batches", lambda records: [records]
        )

    def bad_model(_model, messages, **kwargs):
        ids = [row["id"] for row in json.loads(messages[-1]["content"])]
        result = dict(
            name="Invalid",
            member_ids=ids,
            category_id=None,
            reason="Untrusted proposal",
        )
        if invalid == "invented":
            result["member_ids"] = ["invented", ids[0]]
        if invalid == "duplicate":
            result["member_ids"] = [ids[0], ids[0]]
        if invalid == "category":
            result["category_id"] = "missing-category"
        if invalid == "regex":
            result["regex"] = ".*"
        return json.dumps({"groups": [result]})

    monkeypatch.setattr(payee_review, "chat_with_model", bad_model)
    started = client.post("/api/payee-review/reviews").json()
    result = client.get("/api/payee-review/reviews/" + started["id"]).json()
    assert result["status"] == "failed", result
    assert db.scalar(select(func.count()).select_from(PayeeGroup)) == 0
    assert all(row.group_id is None for row in db.scalars(select(PayeeRule)))


def test_cancelled_queued_review_is_not_executed(client, db, aliases, monkeypatch):
    monkeypatch.setattr(payee_review.executor, "submit", lambda *args: None)
    first = client.post("/api/payee-review/reviews").json()
    # Repeated start clicks reuse the same active job.
    assert client.post("/api/payee-review/reviews").json()["id"] == first["id"]
    cancelled = client.delete("/api/payee-review/reviews/" + first["id"])
    assert cancelled.json()["status"] == "cancelled"
    monkeypatch.setattr(
        payee_review,
        "chat_with_model",
        lambda *a, **k: pytest.fail("Cancelled review called a model"),
    )
    payee_review.run_review(first["id"], "synthetic-local")
    assert db.scalar(select(func.count()).select_from(PayeeGroup)) == 0
    assert (
        client.get("/api/payee-review/payees").json()["review"]["status"] == "cancelled"
    )


def test_reviewed_aliases_do_not_require_matching_json(client, db, aliases):
    from pathlib import Path

    import abacus.classification as classification

    assert not Path(classification.__file__).with_name("payee_matching.json").exists()
    assert client.get("/api/payee-review/payees").json()["total"] == 2


def test_candidates_are_bounded_and_do_not_mix_transaction_types():
    from abacus.payee_matching import candidate_batches

    rows = [
        dict(
            id=str(n),
            payee=f"Corner cafe #{n}",
            kind="purchase" if n % 2 else "refund",
            group_id=None,
            group_name=None,
        )
        for n in range(100)
    ]
    batches = candidate_batches(rows)
    assert batches and all(len(batch) <= 24 for batch in batches)
    assert all(len({row["kind"] for row in batch}) == 1 for batch in batches)
    assert {row["id"] for batch in batches for row in batch} == {
        row["id"] for row in rows
    }
