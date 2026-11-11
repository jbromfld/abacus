import io

import pytest
from abacus.imports import parse_amount, parse_date, prepare_file, process_import
from abacus.local_model import ollama_url
from abacus.models import Settings, StatementImport
from reportlab.pdfgen.canvas import Canvas

CSV = b"Date,Description,Amount\n2025-12-29,Grocer,12.50\n2025-12-30,Refund,-2.00\n2026-01-02,Card settlement,-10.50\n"
MAPPING = dict(
    date_column="Date",
    description_column="Description",
    amount_column="Amount",
    date_format="%Y-%m-%d",
    positive_is="purchase",
)


def prepare(client, account_id, data=CSV, filename="statement.csv"):
    response = client.post(
        "/api/imports",
        data={"account_id": account_id, "period": "2026-01"},
        files={"file": (filename, data)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def mapped(client, account_id):
    job = prepare(client, account_id)
    response = client.put("/api/imports/" + job["id"] + "/mapping", json=MAPPING)
    assert response.status_code == 200, response.text
    return response.json()


def test_csv_review_atomic_commit_duplicates_undo(client, account_id, category_id):
    job = mapped(client, account_id)
    assert len(job["rows"]) == 3
    assert job["rows"][0]["amount"] == 1250 and job["rows"][1]["kind"] == "refund"
    assert job["rows"][0]["source"]["original"]["Description"] == "Grocer"
    id = job["id"]
    assert client.post(f"/api/imports/{id}/commit").status_code == 422
    assert client.get("/api/transactions").json()["items"] == []
    rows = [
        {**r, "source_index": i, "category_id": category_id}
        for i, r in enumerate(job["rows"])
    ]
    rows[2]["kind"] = "payment"
    reviewed = client.put(f"/api/imports/{id}/review", json={"rows": rows})
    assert reviewed.status_code == 200
    assert not any(r["errors"] for r in reviewed.json()["rows"])
    committed = client.post(f"/api/imports/{id}/commit")
    assert committed.status_code == 200, committed.text
    assert len(client.get("/api/transactions").json()["items"]) == 3
    assert (
        client.get("/api/forecast?month=2025-12").json()["actual"]["expenses"] == 1050
    )
    assert client.post(f"/api/imports/{id}/commit").status_code == 409
    assert (
        client.post(
            "/api/imports",
            data={"account_id": account_id, "period": "2026-01"},
            files={"file": ("again.csv", CSV)},
        ).status_code
        == 409
    )
    job2 = prepare(client, account_id, CSV + b"2026-01-03,Book,5.00\n")
    job2 = client.put("/api/imports/" + job2["id"] + "/mapping", json=MAPPING).json()
    rows2 = [
        {**r, "source_index": i, "category_id": category_id}
        for i, r in enumerate(job2["rows"])
    ]
    reviewed2 = client.put(
        "/api/imports/" + job2["id"] + "/review", json={"rows": rows2}
    ).json()
    assert reviewed2["rows"][0]["duplicate"] and reviewed2["rows"][1]["duplicate"]
    assert client.post(f"/api/imports/{id}/undo").status_code == 200
    assert client.get("/api/transactions").json()["items"] == []
    assert client.post(f"/api/imports/{id}/undo").status_code == 409


def test_deselected_invalid_rows_do_not_block(client, account_id, category_id):
    job = mapped(client, account_id)
    rows = [
        {
            **r,
            "source_index": i,
            "selected": i == 0,
            "category_id": category_id if i == 0 else None,
        }
        for i, r in enumerate(job["rows"])
    ]
    client.put("/api/imports/" + job["id"] + "/review", json={"rows": rows})
    assert client.post("/api/imports/" + job["id"] + "/commit").status_code == 200
    assert len(client.get("/api/transactions").json()["items"]) == 1


def test_csv_invalid_dates_and_amounts_remain_reviewable(client, account_id):
    job = prepare(client, account_id, b"Date,Description,Amount\nbad,Shop,nope\n")
    job = client.put("/api/imports/" + job["id"] + "/mapping", json=MAPPING).json()
    assert job["rows"][0]["errors"]
    assert client.post("/api/imports/" + job["id"] + "/commit").status_code == 422


def test_csv_processing_never_calls_model(client, account_id, db, monkeypatch):
    job = mapped(client, account_id)

    def no_model(*args):
        raise AssertionError("CSV imports must not call Ollama")

    monkeypatch.setattr("abacus.imports.ask_model", no_model)
    saved = db.get(StatementImport, job["id"])
    saved.status = "processing"
    db.get(Settings, 1).model = "test-model"
    db.commit()
    process_import(job["id"])
    result = client.get("/api/imports/" + job["id"]).json()
    assert result["status"] == "review"
    assert [r["amount"] for r in result["rows"]] == [1250, 200, 1050]
    assert [r["kind"] for r in result["rows"]] == ["purchase", "refund", "refund"]
    assert all(r["category_id"] is None for r in result["rows"])
    assert client.get("/api/transactions").json()["items"] == []


@pytest.mark.parametrize(
    "response",
    [
        {"rows": [{"index": 0, "category_id": "invented", "kind": "purchase"}]},
        {"rows": "invalid"},
        {"rows": [{"index": 0, "category_id": None, "kind": "tool_call"}]},
    ],
)
def test_invalid_pdf_model_output_safe(client, account_id, db, monkeypatch, response):
    job = prepare(client, account_id, pdf_bytes("2025-12-29 Grocer 12.50"), "text.pdf")
    monkeypatch.setattr("abacus.imports.ask_model", lambda *args: response)
    saved = db.get(StatementImport, job["id"])
    saved.status = "processing"
    db.get(Settings, 1).model = "test-model"
    db.commit()
    process_import(job["id"])
    result = client.get("/api/imports/" + job["id"]).json()
    assert result["status"] == "failed" and result["error"]
    assert result["rows"] == []
    assert client.get("/api/transactions").json()["items"] == []


def test_pdf_model_unavailable_manual_recovery(client, account_id, db, monkeypatch):
    job = prepare(client, account_id, pdf_bytes("2025-12-29 Grocer 12.50"), "text.pdf")

    def fail(*args):
        raise RuntimeError("Ollama unavailable")

    monkeypatch.setattr("abacus.imports.ask_model", fail)
    saved = db.get(StatementImport, job["id"])
    saved.status = "processing"
    db.get(Settings, 1).model = "test-model"
    db.commit()
    process_import(job["id"])
    result = client.get("/api/imports/" + job["id"]).json()
    assert result["status"] == "failed" and result["rows"] == []
    assert len(mapped(client, account_id)["rows"]) == 3
    monkeypatch.setattr("abacus.main.available_models", fail)
    assert client.get("/api/models").json()["error"]


def pdf_bytes(text=None):
    output = io.BytesIO()
    canvas = Canvas(output)
    if text:
        canvas.drawString(50, 750, text)
    canvas.showPage()
    canvas.save()
    return output.getvalue()


def test_pdf_extracts_text_and_rejects_scans():
    source = prepare_file("test.pdf", pdf_bytes("2025-12-29 Grocery 12.50"))
    assert source["pages"][0]["page"] == 1 and "Grocery" in source["pages"][0]["text"]
    with pytest.raises(ValueError, match="scanned"):
        prepare_file("test.pdf", pdf_bytes())


def test_pdf_model_provenance_and_validation(
    client, account_id, category_id, db, monkeypatch
):
    job = prepare(client, account_id, pdf_bytes("12/29/2025 Grocer $12.50"), "text.pdf")
    monkeypatch.setattr(
        "abacus.imports.ask_model",
        lambda *args: {
            "rows": [
                dict(
                    date="2025-12-29",
                    description="Grocer",
                    amount=1250,
                    kind="purchase",
                    category_id=category_id,
                    page=1,
                )
            ]
        },
    )
    saved = db.get(StatementImport, job["id"])
    saved.status = "processing"
    db.get(Settings, 1).model = "test-model"
    db.commit()
    process_import(job["id"])
    result = client.get("/api/imports/" + job["id"]).json()
    assert result["status"] == "review" and result["rows"][0]["source"]["page"] == 1
    assert "Grocer" in result["rows"][0]["source"]["original"]
    assert result["rows"][0]["category_id"] is None  # PDF extraction does not classify.
    client.put(
        "/api/imports/" + job["id"] + "/review",
        json={
            "rows": [
                {**result["rows"][0], "source_index": 0, "category_id": category_id}
            ]
        },
    )
    assert client.post("/api/imports/" + job["id"] + "/commit").status_code == 200


def test_restart_interrupted_import(client, account_id, db):
    job = mapped(client, account_id)
    saved = db.get(StatementImport, job["id"])
    saved.status = "processing"
    db.get(Settings, 1).model = "test-model"
    db.commit()
    from abacus.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as new_client:
        assert (
            new_client.get("/api/imports/" + job["id"]).json()["status"]
            == "interrupted"
        )


@pytest.mark.parametrize(
    "text,expected", [("$1,200.51", 120051), ("(2.50)", -250), ("12.01", 1201)]
)
def test_amount_precision(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize("text", ["NaN", "0", "1.001", "garbage"])
def test_invalid_amounts(text):
    with pytest.raises(ValueError):
        parse_amount(text)


def test_year_boundary_date_inference_and_jpy():
    assert parse_date("12/29", "%m/%d", "2026-01") == "2025-12-29"
    assert parse_date("01/02", "%m/%d", "2025-12") == "2026-01-02"
    assert parse_amount("500", 0) == 500
    with pytest.raises(ValueError):
        parse_amount("500.5", 0)


@pytest.mark.parametrize(
    "url",
    [
        "https://api.example.com",
        "http://127.0.0.1.evil.invalid:11434",
        "http://user:pass@localhost:11434",
        "http://localhost:11434/proxy",
    ],
)
def test_loopback_only(monkeypatch, url):
    monkeypatch.setenv("OLLAMA_URL", url)
    with pytest.raises(ValueError):
        ollama_url()


def test_background_pdf_retry_and_manual_category(
    client, account_id, category_id, monkeypatch, db
):
    db.get(Settings, 1).model = "test-model"
    db.commit()
    csv = prepare(client, account_id)
    assert client.post("/api/imports/" + csv["id"] + "/process").status_code == 422
    job = prepare(client, account_id, pdf_bytes("2025-12-29 Grocer 12.50"), "text.pdf")

    class InlineExecutor:
        def submit(self, fn, *args):
            fn(*args)

    monkeypatch.setattr("abacus.import_api.executor", InlineExecutor())
    monkeypatch.setattr("abacus.imports.ask_model", lambda *args: {"rows": "invalid"})
    assert client.post("/api/imports/" + job["id"] + "/process").status_code == 200
    assert client.get("/api/imports/" + job["id"]).json()["status"] == "failed"
    monkeypatch.setattr(
        "abacus.imports.ask_model",
        lambda *args: {
            "rows": [
                dict(
                    date="2025-12-29",
                    description="Grocer",
                    amount=1250,
                    kind="purchase",
                    category_id=category_id,
                    page=1,
                )
            ]
        },
    )
    assert client.post("/api/imports/" + job["id"] + "/process").status_code == 200
    result = client.get("/api/imports/" + job["id"]).json()
    assert result["status"] == "review" and result["rows"][0]["category_id"] is None
    assert client.get("/api/transactions").json()["items"] == []
    assert client.post("/api/imports/" + job["id"] + "/commit").status_code == 422


@pytest.mark.parametrize("month", ["0000-01", "2026-13", "not-a-month", "9999-12"])
def test_invalid_forecast_month_is_validation_error(client, month):
    assert client.get("/api/forecast", params={"month": month}).status_code == 422


@pytest.mark.parametrize("explicit_default", [False, True])
def test_csv_defaults_to_purchase_for_either_amount_sign(
    client, account_id, explicit_default
):
    job = prepare(client, account_id)
    mapping = {k: v for k, v in MAPPING.items() if k != "positive_is"}
    if explicit_default:
        mapping["positive_is"] = None
    response = client.put("/api/imports/" + job["id"] + "/mapping", json=mapping)
    assert response.status_code == 200, response.text
    assert [r["kind"] for r in response.json()["rows"]] == [
        "purchase",
        "purchase",
        "purchase",
    ]
    assert [r["amount"] for r in response.json()["rows"]] == [1250, 200, 1050]


def test_csv_explicit_negative_charge_convention(client, account_id):
    job = prepare(client, account_id)
    response = client.put(
        "/api/imports/" + job["id"] + "/mapping",
        json={**MAPPING, "positive_is": "refund"},
    )
    assert response.status_code == 200
    assert [r["kind"] for r in response.json()["rows"]] == [
        "refund",
        "purchase",
        "purchase",
    ]


@pytest.mark.parametrize(
    "status", ["prepared", "review", "failed", "interrupted", "undone"]
)
def test_delete_import_allows_starting_over(client, account_id, db, status):
    job = mapped(client, account_id)
    saved = db.get(StatementImport, job["id"])
    saved.status = status
    db.commit()
    response = client.delete("/api/imports/" + job["id"])
    assert response.status_code == 200, response.text
    assert client.get("/api/imports/" + job["id"]).status_code == 404
    assert client.get("/api/imports").json()["items"] == []
    replacement = prepare(client, account_id)
    assert replacement["id"] != job["id"]


def test_delete_import_requires_undo_and_preserves_unrelated_transactions(
    client, account_id, category_id
):
    unrelated = client.post(
        "/api/transactions",
        json=dict(
            date="2026-01-10",
            description="Unrelated",
            amount=500,
            kind="purchase",
            category_id=category_id,
            account_id=account_id,
        ),
    ).json()
    job = mapped(client, account_id)
    rows = [
        {**r, "category_id": category_id, "source_index": i}
        for i, r in enumerate(job["rows"])
    ]
    assert (
        client.put(
            "/api/imports/" + job["id"] + "/review", json={"rows": rows}
        ).status_code
        == 200
    )
    assert client.post("/api/imports/" + job["id"] + "/commit").status_code == 200
    response = client.delete("/api/imports/" + job["id"])
    assert response.status_code == 409 and "Undo" in response.json()["detail"]
    assert len(client.get("/api/transactions").json()["items"]) == 4
    assert client.post("/api/imports/" + job["id"] + "/undo").status_code == 200
    assert client.delete("/api/imports/" + job["id"]).status_code == 200
    assert [t["id"] for t in client.get("/api/transactions").json()["items"]] == [
        unrelated["id"]
    ]
    replacement = prepare(client, account_id)
    assert (
        replacement["status"] == "review"
    )  # Card mapping survives deleting a statement.
    assert replacement["source"]["mapping"] == MAPPING


def test_delete_processing_import_is_blocked(client, account_id, db):
    job = mapped(client, account_id)
    saved = db.get(StatementImport, job["id"])
    saved.status = "processing"
    db.commit()
    assert client.delete("/api/imports/" + job["id"]).status_code == 409
    assert client.get("/api/imports/" + job["id"]).json()["status"] == "processing"


def test_delete_missing_import(client):
    assert client.delete("/api/imports/missing").status_code == 404


@pytest.mark.parametrize("amount", ["0.00", "-0.00", "$0.00", "(0.00)", "0"])
def test_csv_zero_amount_defaults_unselected_and_does_not_block_commit(
    client, account_id, category_id, amount
):
    content = f"Date,Description,Amount\n2025-12-01,Zero row,{amount}\n2025-12-02,Real expense,12.50\n".encode()
    job = prepare(client, account_id, content)
    job = client.put("/api/imports/" + job["id"] + "/mapping", json=MAPPING).json()
    assert job["rows"][0]["amount"] == 0 and job["rows"][0]["selected"] is False
    assert job["rows"][1]["amount"] == 1250 and job["rows"][1]["selected"] is True
    rows = [
        {**r, "source_index": i, "category_id": category_id}
        for i, r in enumerate(job["rows"])
    ]
    assert (
        client.put(
            "/api/imports/" + job["id"] + "/review", json={"rows": rows}
        ).status_code
        == 200
    )
    assert client.post("/api/imports/" + job["id"] + "/commit").status_code == 200
    transactions = client.get("/api/transactions").json()["items"]
    assert len(transactions) == 1 and transactions[0]["amount"] == 1250


def test_unparseable_csv_amount_is_not_silently_treated_as_zero(client, account_id):
    job = prepare(
        client,
        account_id,
        b"Date,Description,Amount\n2025-12-01,Bad amount,not-money\n",
    )
    job = client.put("/api/imports/" + job["id"] + "/mapping", json=MAPPING).json()
    assert job["rows"][0]["selected"] is True
    assert job["rows"][0]["errors"]
    assert client.post("/api/imports/" + job["id"] + "/commit").status_code == 422


def test_pdf_zero_amount_keeps_statement_reviewable(
    client, account_id, category_id, db, monkeypatch
):
    job = prepare(
        client,
        account_id,
        pdf_bytes("12/01/2025 Zero row 0.00 and expense 12.50"),
        "zero.pdf",
    )
    monkeypatch.setattr(
        "abacus.imports.ask_model",
        lambda *args: {
            "rows": [
                dict(
                    date="2025-12-01",
                    description="Zero row",
                    amount=0,
                    kind="purchase",
                    page=1,
                ),
                dict(
                    date="2025-12-02",
                    description="Real expense",
                    amount=1250,
                    kind="purchase",
                    page=1,
                ),
            ]
        },
    )
    saved = db.get(StatementImport, job["id"])
    saved.status = "processing"
    db.get(Settings, 1).model = "test-model"
    db.commit()
    process_import(job["id"])
    result = client.get("/api/imports/" + job["id"]).json()
    assert result["status"] == "review"
    assert result["rows"][0]["selected"] is False
    assert result["rows"][1]["selected"] is True
    rows = [
        {**r, "source_index": i, "category_id": category_id}
        for i, r in enumerate(result["rows"])
    ]
    client.put("/api/imports/" + job["id"] + "/review", json={"rows": rows})
    assert client.post("/api/imports/" + job["id"] + "/commit").status_code == 200
    assert len(client.get("/api/transactions").json()["items"]) == 1


def test_zero_row_can_be_corrected_and_selected(client, account_id, category_id):
    job = prepare(
        client, account_id, b"Date,Description,Amount\n2025-12-01,Correction,0.00\n"
    )
    job = client.put("/api/imports/" + job["id"] + "/mapping", json=MAPPING).json()
    row = {
        **job["rows"][0],
        "source_index": 0,
        "selected": True,
        "category_id": category_id,
    }
    client.put("/api/imports/" + job["id"] + "/review", json={"rows": [row]})
    assert client.post("/api/imports/" + job["id"] + "/commit").status_code == 422
    row["amount"] = 500
    client.put("/api/imports/" + job["id"] + "/review", json={"rows": [row]})
    assert client.post("/api/imports/" + job["id"] + "/commit").status_code == 200
    assert client.get("/api/transactions").json()["items"][0]["amount"] == 500
