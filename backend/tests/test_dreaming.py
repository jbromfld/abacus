import json
from datetime import UTC, datetime
from uuid import uuid4

from abacus import dreaming
from abacus.db import Session
from abacus.models import MemoryDream, Settings
from sqlalchemy import select


def sources():
    return [
        dict(
            id=str(uuid4()),
            revision=1,
            title="Savings",
            text="I intend to cut discretionary spending.",
            kind="intention",
            status="active",
            source_date="2026-11-10",
            source_excerpt="I intend to cut discretionary spending.",
            cues=["savings"],
        )
        for _ in range(2)
    ]


def enable(db):
    setting = db.get(Settings, 1)
    setting.advisor_enabled = setting.advisor_memory_enabled = (
        setting.advisor_dreaming_enabled
    ) = True
    setting.model = "synthetic"
    db.commit()


def test_default_off_and_preconditions(client, db):
    assert client.get("/api/advisor/dreaming").json()["enabled"] is False
    assert client.post("/api/advisor/dreaming/run").status_code == 409
    assert (
        client.put("/api/advisor/dreaming", json={"enabled": True}).status_code == 409
    )


def setup_calls(monkeypatch, evidence):
    commits = []

    def call(enabled, operation, **kwargs):
        if operation == "status":
            return {"capabilities": ["dreaming-v1"]}
        if operation == "dream_candidates":
            return {"groups": [{"sources": evidence}]}
        if operation == "get":
            return next(s for s in evidence if s["id"] == kwargs["id"])
        if operation == "consolidation_status":
            return {"found": False}
        raise AssertionError(operation)

    monkeypatch.setattr(dreaming, "memory_call", call)
    monkeypatch.setattr(
        dreaming,
        "mutate_memory",
        lambda operation, **kwargs: (
            commits.append(kwargs) or {"id": "combined", "revision": 1}
        ),
    )
    monkeypatch.setattr(
        dreaming,
        "chat_with_model",
        lambda *args: json.dumps(
            dict(
                title="Savings",
                text="Summary",
                compatible=True,
                conflicts=[],
                preserved_facts=[s["text"] for s in evidence],
                source_ids=[s["id"] for s in evidence],
            )
        ),
    )
    return commits


def test_duplicate_commits_once_and_does_not_recursively_queue(db, monkeypatch):
    enable(db)
    evidence = sources()
    commits = setup_calls(monkeypatch, evidence)
    dreaming.queue(db, immediate=True)
    dreaming.tick()
    dreaming.tick()
    db.expire_all()
    jobs = db.scalars(select(MemoryDream)).all()
    assert len(jobs) == 1 and jobs[0].state == "completed"
    assert len(commits) == 1 and commits[0]["note"]["text"] == evidence[0]["text"]
    assert "evidence" not in jobs[0].payload["groups"][0]


def test_questions_and_complementary_facts_require_review(db, monkeypatch):
    enable(db)
    evidence = sources()
    evidence[0].update(
        source_excerpt="What could I reduce?",
        kind="decision",
        text="Entertainment USD 213.59 over two months; do not change car payments.",
    )
    evidence[1].update(
        kind="decision", text="Review groceries; do not change the mortgage."
    )
    commits = setup_calls(monkeypatch, evidence)
    dreaming.queue(db, immediate=True)
    dreaming.tick()
    db.expire_all()
    job = db.scalar(select(MemoryDream))
    assert job.state == "review"
    assert not commits
    assert job.payload["groups"][0]["reasons"]


def test_disabling_during_model_call_prevents_commit(db, monkeypatch):
    enable(db)
    commits = setup_calls(monkeypatch, sources())

    def disable(*args):
        with Session() as other:
            other.get(Settings, 1).advisor_dreaming_enabled = False
            other.commit()
            dreaming.cancel(other)
        return "{}"

    monkeypatch.setattr(dreaming, "chat_with_model", disable)
    dreaming.queue(db, immediate=True)
    dreaming.tick()
    assert not commits
    db.expire_all()
    assert db.scalar(select(MemoryDream)).state == "cancelled"


def test_resume_reconciles_a_lost_commit_before_running_model(db, monkeypatch):
    enable(db)
    job = MemoryDream(
        state="processing",
        due_at=datetime.now(UTC),
        payload={
            "groups": [
                {
                    "operation_key": str(uuid4()),
                    "sources": [],
                    "state": "ready",
                    "note": {},
                }
            ]
        },
    )
    db.add(job)
    db.commit()
    monkeypatch.setattr(
        dreaming,
        "memory_call",
        lambda *args, **kwargs: {"found": True, "id": "canonical"},
    )
    monkeypatch.setattr(
        dreaming,
        "chat_with_model",
        lambda *args: (_ for _ in ()).throw(AssertionError("Must reconcile first")),
    )
    dreaming.tick()
    db.expire_all()
    assert db.get(MemoryDream, job.id).payload["groups"][0]["state"] == "committed"


def test_manual_memory_mutation_queues_and_forgetting_purges_jobs(db, monkeypatch):
    from abacus.memory_api import invoke

    enable(db)
    monkeypatch.setattr(
        "abacus.memory_api.mutate_memory", lambda *args, **kwargs: {"id": "synthetic"}
    )
    invoke("create", note={}, create_key=str(uuid4()))
    assert db.scalar(select(MemoryDream)).state == "queued"
    invoke("forget", id=str(uuid4()), expected_revision=1)
    db.expire_all()
    assert db.scalar(select(MemoryDream)) is None


def test_approval_disabled_and_source_revisions_are_not_overridden(
    client, db, monkeypatch
):
    enable(db)
    evidence = sources()
    evidence[1]["text"] = "I intend to save USD 30 each month."
    setup_calls(monkeypatch, evidence)
    dreaming.queue(db, immediate=True)
    dreaming.tick()
    db.expire_all()
    job = db.scalar(select(MemoryDream))
    group = job.payload["groups"][0]
    assert group["sources"] == [{"id": s["id"], "revision": 1} for s in evidence]
    response = client.put("/api/advisor/dreaming", json={"enabled": False})
    assert response.status_code == 200
    response = client.post(
        f"/api/advisor/dreaming/{job.id}/{group['operation_key']}/approve", json={}
    )
    assert response.status_code == 409


def test_shutdown_prevents_a_late_model_result_from_committing(db, monkeypatch):
    enable(db)
    evidence = sources()
    commits = setup_calls(monkeypatch, evidence)
    original = dreaming.chat_with_model

    def stop_during_generation(*args):
        result = original(*args)
        dreaming.stop()
        return result

    monkeypatch.setattr(dreaming, "chat_with_model", stop_during_generation)
    dreaming.queue(db, immediate=True)
    dreaming.tick()
    assert not commits
    db.expire_all()
    assert db.scalar(select(MemoryDream)).state == "processing"
    dreaming.start()


def test_compatible_complements_keep_every_original_word(db, monkeypatch):
    enable(db)
    evidence = sources()
    evidence[1]["text"] = "I intend to review unnecessary subscriptions."
    commits = setup_calls(monkeypatch, evidence)
    dreaming.queue(db, immediate=True)
    dreaming.tick()
    assert len(commits) == 1
    text = commits[0]["note"]["text"]
    assert all(source["text"] in text for source in evidence)
    assert len(text) <= 400
