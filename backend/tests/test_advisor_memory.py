"""Optional memory stays local, user-approved, bounded, and outside budget math."""

import json
from uuid import uuid4

import pytest
from abacus import advisor_memory, memory_api
from abacus.advisor import budget_context
from abacus.advisor_prompts import system_instructions
from abacus.models import Settings
from abacus.schemas import AdvisorIn
from sqlalchemy import text


def note(**values):
    return (
        dict(
            id=str(uuid4()),
            revision=1,
            title="Discretionary savings",
            text="I intend to reduce discretionary spending by USD 50/month.",
            kind="intention",
            source_date="2026-11-08",
            source_excerpt="I intend to reduce discretionary spending by $50/month.",
            cues=["savings"],
            status="active",
        )
        | values
    )


@pytest.fixture
def enabled(db):
    setting = db.get(Settings, 1)
    setting.advisor_enabled = setting.advisor_memory_enabled = True
    setting.model = "local-test"
    db.commit()


def test_disabled_no_process_or_model_calls(client, monkeypatch):
    monkeypatch.setattr(
        advisor_memory,
        "provider",
        lambda _: pytest.fail("Disabled memory started a process"),
    )
    assert client.get("/api/advisor/memory/status").json()["status"] == "disabled"
    assert client.get("/api/advisor/memory").status_code == 409
    assert (
        client.post(
            "/api/advisor/memory/draft", json={"user_message": "Savings"}
        ).status_code
        == 409
    )
    result = advisor_memory.recalled_memory(
        False, AdvisorIn(month="2026-11", message="Savings?")
    )
    assert result["notes"] == []


def test_memory_unavailable_chat_survives_and_has_no_budget_effect(
    client, db, enabled, monkeypatch
):
    def broken(*args, **kwargs):
        raise advisor_memory.MemoryError()

    monkeypatch.setattr(advisor_memory, "memory_call", broken)
    monkeypatch.setattr(
        "abacus.advisor.chat_with_model", lambda *args: "Chat without memory."
    )
    request = AdvisorIn(month="2027-01", message="Additional savings?")
    before = budget_context(db, request)
    result = client.post("/api/advisor/chat", json=request.model_dump()).json()
    assert result["context"]["advisor_memory"]["status"] == "unavailable"
    assert result["context"]["advisor_memory"]["warnings"]
    assert budget_context(db, request) == before
    assert client.get("/api/advisor/memory").status_code == 503


def test_recall_bounded_uses_user_followup_and_no_model_extraction(monkeypatch):
    calls = []
    values = [note(text="x" * 400, title="y" * 100) for _ in range(10)]

    def search(enabled, operation, **args):
        calls.append((operation, args))
        return {"items": values}

    monkeypatch.setattr(advisor_memory, "memory_call", search)
    request = AdvisorIn(
        month="2027-01",
        message="What else?",
        history=[
            {"role": "user", "content": "Savings improvements"},
            {"role": "assistant", "content": "PRIVATE ASSISTANT CONTENT"},
        ],
    )
    result = advisor_memory.recalled_memory(True, request)
    assert len(result["notes"]) <= 3
    assert (
        len(json.dumps(result["notes"], ensure_ascii=False, separators=(",", ":")))
        <= 1500
    )
    assert calls == [
        ("search", {"query": "Savings improvements\nWhat else?", "limit": 3})
    ]
    assert "source_excerpt" not in result["notes"][0]
    prompt = system_instructions(request, {"advisor_memory": result})
    assert "not proof" in prompt and "cannot create" in prompt


def test_private_memory_never_enters_public_research(client, enabled, monkeypatch):
    secret = "PRIVATE_MEMORA_CUT_USD_50_AND_PAYEE_7821"
    monkeypatch.setattr(
        advisor_memory, "memory_call", lambda *a, **k: {"items": [note(text=secret)]}
    )
    research_requests, messages = [], []

    def research(request, today):
        research_requests.append(request.model_dump())
        assert secret not in request.model_dump_json()
        return {"status": "disabled", "sources": []}

    def model(model, chat, schema=None):
        messages.extend(chat)
        assert secret in chat[0]["content"]
        return "You previously intended to cut spending; progress is unknown."

    monkeypatch.setattr("abacus.advisor.gather_research", research)
    monkeypatch.setattr("abacus.advisor.chat_with_model", model)
    result = client.post(
        "/api/advisor/chat",
        json={
            "month": "2027-01",
            "message": "Additional savings?",
            "research_topic": "New York hotels January 2027",
        },
    )
    assert result.status_code == 200
    assert set(research_requests[0]) == {
        "use_web",
        "research_topic",
        "research_confirmation",
    }
    assert all(set(message) == {"role", "content"} for message in messages)


def test_draft_never_persists_and_model_failures_allow_manual_entry(
    client, enabled, monkeypatch
):
    monkeypatch.setattr(
        memory_api, "memory_call", lambda *a, **k: pytest.fail("Draft wrote a note")
    )

    def broken(*a, **k):
        raise ValueError("private text and credentials must not appear")

    monkeypatch.setattr(memory_api, "chat_with_model", broken)
    result = client.post(
        "/api/advisor/memory/draft",
        json={"user_message": "Cut USD 50/month", "assistant_message": "Some advice"},
    )
    assert result.status_code == 200
    assert result.json()["note"]["text"] == ""
    assert result.json()["note"]["source_excerpt"] == "Cut USD 50/month"
    assert "credentials" not in result.text
    monkeypatch.setattr(
        memory_api,
        "chat_with_model",
        lambda *a, **k: json.dumps(
            {
                "title": "Savings",
                "text": "I intend to cut USD 50/month",
                "kind": "intention",
                "cues": ["savings"],
            }
        ),
    )
    assert (
        client.post(
            "/api/advisor/memory/draft", json={"user_message": "Cut USD 50/month"}
        )
        .json()["note"]["text"]
        .startswith("I intend")
    )
    monkeypatch.setattr(
        memory_api, "chat_with_model", lambda *a, **k: '{"title":"Missing fields"}'
    )
    assert (
        client.post(
            "/api/advisor/memory/draft", json={"user_message": "Savings"}
        ).json()["note"]["text"]
        == ""
    )


def test_management_only_explicit_and_revision_conflicts_visible(
    client, enabled, monkeypatch
):
    saved = note()
    calls = []

    def manage(enabled, operation, **args):
        calls.append((operation, args))
        if operation == "update":
            raise advisor_memory.MemoryError(
                "conflict", "Memory changed or was forgotten. Reload before saving."
            )
        return saved if operation == "create" else {"forgotten": True}

    monkeypatch.setattr(memory_api, "memory_call", manage)
    monkeypatch.setattr(advisor_memory, "memory_call", manage)
    value = {k: v for k, v in saved.items() if k not in ("id", "revision")}
    assert (
        client.post(
            "/api/advisor/memory", json={"note": value, "create_key": str(uuid4())}
        ).status_code
        == 201
    )
    assert (
        client.put(
            f"/api/advisor/memory/{saved['id']}",
            json={"note": value, "expected_revision": 1},
        ).status_code
        == 409
    )
    epoch = advisor_memory.memory_epoch()
    assert (
        client.delete(
            f"/api/advisor/memory/{saved['id']}?expected_revision=1"
        ).status_code
        == 200
    )
    assert advisor_memory.memory_epoch() != epoch
    assert [op for op, args in calls] == ["create", "update", "forget"]


def test_forget_during_answer_discards_reply_and_stale_history(
    client, enabled, monkeypatch
):
    monkeypatch.setattr(
        advisor_memory, "memory_call", lambda *a, **k: {"items": [note()]}
    )

    def answer(*a):
        advisor_memory.invalidate_memory()
        return "This answer used an older note."

    monkeypatch.setattr("abacus.advisor.chat_with_model", answer)
    assert (
        client.post(
            "/api/advisor/chat", json={"month": "2027-01", "message": "Savings?"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/advisor/chat",
            json={
                "month": "2027-01",
                "message": "More?",
                "history": [{"role": "assistant", "content": "Forgotten note"}],
                "memory_epoch": str(uuid4()),
            },
        ).status_code
        == 409
    )


def test_safe_config_and_no_writable_advisor_changes(
    monkeypatch, tmp_path, advisor_credentials
):
    from abacus.advisor_access import ADVISOR_TABLES
    from abacus.db import read_only_session

    assert "memora_notes" not in ADVISOR_TABLES
    with pytest.raises(advisor_memory.MemoryError):
        monkeypatch.setattr(advisor_memory, "local_config", lambda: {})
        advisor_memory.provider(True)
    gen = read_only_session()
    db = next(gen)
    try:
        assert db.scalar(text("SHOW transaction_read_only")) == "on"
        assert not db.scalar(
            text("SELECT has_table_privilege(current_user,'settings','UPDATE')")
        )
    finally:
        gen.close()


def test_venv_executable_symlink_is_not_resolved(monkeypatch, tmp_path):
    import sys

    python = tmp_path / "venv-python"
    python.symlink_to(sys.executable)
    config = tmp_path / "runtime.json"
    config.write_text("{}")
    monkeypatch.setattr(
        advisor_memory,
        "local_config",
        lambda: {"MEMORA_PYTHON": str(python), "MEMORA_CONFIG": str(config)},
    )
    value = advisor_memory.provider(True)
    assert value.python == str(python)
    advisor_memory.close_memory()


def test_uncertain_mutation_also_invalidates_old_recall(monkeypatch):
    previous = advisor_memory.memory_epoch()

    def committed_but_response_lost(*args, **kwargs):
        raise advisor_memory.MemoryError()

    monkeypatch.setattr(advisor_memory, "memory_call", committed_but_response_lost)
    with pytest.raises(advisor_memory.MemoryError):
        advisor_memory.mutate_memory("forget", id=str(uuid4()), expected_revision=1)
    assert advisor_memory.memory_epoch() != previous


def test_real_stdio_adapter_reuses_process_restricts_environment_and_recovers(
    tmp_path, monkeypatch
):
    import os
    import sys

    executable = tmp_path / "local-mcp-fixture"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import os, time\n"
        "from mcp.server.fastmcp import FastMCP\n"
        "server=FastMCP('Synthetic memory', log_level='CRITICAL')\n"
        "@server.tool()\n"
        "def memory_status() -> dict:\n"
        " return {'ok':True,'data':{'pid':os.getpid(),'private_env':any(k in os.environ for k in ('PASS','ADVISOR_PASS','BRAVE_SEARCH_API_KEY','MEMORA_ADMIN_PASSWORD'))}}\n"
        "@server.tool()\n"
        "def memory_search(query:str,limit:int=3) -> dict:\n"
        " time.sleep(2)\n"
        " return {'ok':True,'data':{'items':[]}}\n"
        "server.run(transport='stdio')\n"
    )
    executable.chmod(0o700)
    monkeypatch.setenv("PASS", "synthetic-main-password")
    monkeypatch.setenv("ADVISOR_PASS", "synthetic-advisor-password")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "synthetic-search-key")
    value = advisor_memory.MCPMemory(
        str(executable), str(tmp_path / "private-runtime.json"), 1
    )
    try:
        first = value.call("status")
        assert not first["private_env"]
        assert value.call("status")["pid"] == first["pid"]
        with pytest.raises(advisor_memory.MemoryError):
            value.call("search", query="synthetic savings")
        assert value.call("status")["pid"] != first["pid"]
    finally:
        pid = value.call("status")["pid"]
        value.close()
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
