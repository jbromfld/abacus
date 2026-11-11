"""Consumer integration tests. Semantic policy is tested by Babar, not duplicated."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from abacus import dreaming
from abacus.advisor_memory import MemoryError
from abacus.models import MemoryDream, Settings
from sqlalchemy import select


def enable(db):
    setting = db.get(Settings, 1)
    setting.advisor_enabled = setting.advisor_memory_enabled = (
        setting.advisor_dreaming_enabled
    ) = True
    setting.model = "synthetic"
    db.commit()


@pytest.fixture
def controller(monkeypatch):
    class Controller:
        capability = True
        calls = []
        commits = 0
        state = "prepared"
        fail_after_commit = False
        operation = str(uuid4())

        def call(self, enabled, operation, **arguments):
            self.calls.append((operation, arguments))
            if operation == "status":
                return {
                    "capabilities": [dreaming.CAPABILITY]
                    if self.capability
                    else ["dreaming-v1"]
                }
            if operation == "dream_prepare":
                return {"groups": [{"operation_key": self.operation}]}
            if operation == "dream_get":
                return dict(
                    operation_key=self.operation,
                    state=self.state,
                    model_request={
                        "messages": [
                            {"role": "user", "content": "Babar-owned request"}
                        ],
                        "schema": {"type": "object"},
                    },
                    evidence=[{"text": "Synthetic source"}],
                    note={"text": "Synthetic summary"},
                    reasons=[],
                )
            if operation == "dream_evaluate":
                assert arguments["raw"] == "uninterpreted model response"
                self.state = "ready"
                return {"state": self.state}
            if operation == "dream_commit":
                self.commits += 1
                self.state = "committed"
                if self.fail_after_commit:
                    raise MemoryError()
                return {"state": self.state}
            if operation == "dream_cancel":
                self.state = "cancelled"
                return {"state": self.state}
            raise AssertionError(f"Unexpected authority: {operation}")

    fake = Controller()
    monkeypatch.setattr(dreaming, "memory_call", fake.call)
    monkeypatch.setattr(
        dreaming,
        "mutate_memory",
        lambda operation, **kwargs: fake.call(True, operation, **kwargs),
    )
    monkeypatch.setattr(
        dreaming, "chat_with_model", lambda *args: "uninterpreted model response"
    )
    return fake


def test_default_off_and_preconditions(client, db, controller):
    assert client.get("/api/advisor/dreaming").json()["enabled"] is False
    dreaming.tick()
    assert not controller.calls
    assert client.post("/api/advisor/dreaming/run").status_code == 409
    assert (
        client.put("/api/advisor/dreaming", json={"enabled": True}).status_code == 409
    )


def test_consumer_only_keeps_handles_and_does_not_recursively_queue(db, controller):
    enable(db)
    dreaming.queue(db, immediate=True)
    dreaming.tick()
    dreaming.tick()
    db.expire_all()
    jobs = db.scalars(select(MemoryDream)).all()
    assert len(jobs) == 1 and jobs[0].state == "completed"
    assert controller.commits == 1
    assert jobs[0].payload == {
        "controller": dreaming.CAPABILITY,
        "groups": [{"operation_key": controller.operation}],
    }
    assert all(op != "consolidate" for op, _ in controller.calls)


@pytest.mark.parametrize(
    "field", ["advisor_memory_enabled", "advisor_dreaming_enabled", "advisor_enabled"]
)
def test_disabled_features_do_not_contact_babar(db, controller, field):
    enable(db)
    setattr(db.get(Settings, 1), field, False)
    db.commit()
    dreaming.queue(db, immediate=True)
    dreaming.tick()
    assert not controller.calls


def test_old_capability_only_disables_dreaming(db, controller):
    enable(db)
    controller.capability = False
    dreaming.queue(db, immediate=True)
    dreaming.tick()
    db.expire_all()
    job = db.scalar(select(MemoryDream))
    assert job.state == "failed" and "Upgrade Babar" in job.reason
    assert db.get(Settings, 1).advisor_memory_enabled
    assert [op for op, _ in controller.calls] == ["status"]


@pytest.mark.parametrize("action", ["disable", "stop"])
def test_late_model_response_cannot_commit(db, controller, monkeypatch, action):
    enable(db)
    dreaming.queue(db, immediate=True)

    def change(*args):
        if action == "stop":
            dreaming.stop()
        else:
            with dreaming.Session() as other:
                other.get(Settings, 1).advisor_dreaming_enabled = False
                other.commit()
                dreaming.cancel(other)
        return "uninterpreted model response"

    monkeypatch.setattr(dreaming, "chat_with_model", change)
    dreaming.tick()
    assert controller.commits == 0
    assert not any(op == "dream_evaluate" for op, _ in controller.calls)
    dreaming.start()


def test_lost_commit_reply_is_reconciled_without_second_write(db, controller):
    enable(db)
    controller.fail_after_commit = True
    dreaming.queue(db, immediate=True)
    dreaming.tick()
    assert controller.commits == 1
    db.expire_all()
    db.scalar(select(MemoryDream)).due_at = datetime.now(UTC)
    db.commit()  # Simulate the bounded retry delay elapsing.
    dreaming.tick()
    db.expire_all()
    assert controller.commits == 1
    assert db.scalar(select(MemoryDream)).state == "completed"


def test_undone_operation_does_not_recommit(db, controller):
    enable(db)
    controller.state = "undone"
    dreaming.queue(db, immediate=True)
    dreaming.tick()
    assert controller.commits == 0


def test_legacy_snapshots_are_cancelled_without_applying(db, controller):
    enable(db)
    job = MemoryDream(
        state="processing",
        due_at=datetime.now(UTC),
        payload={
            "groups": [
                {
                    "operation_key": str(uuid4()),
                    "state": "ready",
                    "evidence": [{"text": "private"}],
                }
            ]
        },
    )
    db.add(job)
    db.commit()
    dreaming.tick()
    db.expire_all()
    assert db.get(MemoryDream, job.id).state == "cancelled"
    assert db.get(MemoryDream, job.id).payload == {}
    assert controller.commits == 0


def test_memory_disabled_status_does_not_hydrate_or_start_babar(client, db, controller):
    db.add(
        MemoryDream(
            state="review",
            due_at=datetime.now(UTC),
            payload={
                "controller": dreaming.CAPABILITY,
                "groups": [{"operation_key": controller.operation}],
            },
        )
    )
    db.commit()
    result = client.get("/api/advisor/dreaming").json()
    assert result["jobs"][0]["groups"] == []
    assert not controller.calls


def test_review_ui_hydrates_babar_data_without_local_copies(client, db, controller):
    enable(db)
    controller.state = "review"
    job = MemoryDream(
        state="review",
        due_at=datetime.now(UTC),
        payload={
            "controller": dreaming.CAPABILITY,
            "groups": [{"operation_key": controller.operation}],
        },
    )
    db.add(job)
    db.commit()
    result = client.get("/api/advisor/dreaming").json()
    assert result["pending_review"] == 1
    assert "model_request" not in result["jobs"][0]["groups"][0]
    response = client.post(
        f"/api/advisor/dreaming/{job.id}/{controller.operation}/approve", json={}
    )
    assert response.status_code == 200
    assert controller.commits == 1
    db.expire_all()
    assert "evidence" not in str(db.get(MemoryDream, job.id).payload)


def test_unavailable_model_preserves_memory_and_pending_handle(
    db, controller, monkeypatch
):
    enable(db)
    monkeypatch.setattr(
        dreaming,
        "chat_with_model",
        lambda *a: (_ for _ in ()).throw(ValueError("model unavailable")),
    )
    dreaming.queue(db, immediate=True)
    dreaming.tick()
    db.expire_all()
    job = db.scalar(select(MemoryDream))
    assert job.state == "processing" and job.payload["groups"]
    assert controller.commits == 0


def test_unavailable_babar_does_not_disable_ordinary_memory(
    db, controller, monkeypatch
):
    enable(db)
    monkeypatch.setattr(
        dreaming, "memory_call", lambda *a, **kw: (_ for _ in ()).throw(MemoryError())
    )
    dreaming.queue(db, immediate=True)
    dreaming.tick()
    db.expire_all()
    assert db.get(Settings, 1).advisor_memory_enabled
    assert "unchanged" in db.scalar(select(MemoryDream)).reason


def test_legacy_review_is_retired_even_without_a_queued_pass(db, controller):
    enable(db)
    job = MemoryDream(
        state="review",
        due_at=datetime.now(UTC),
        payload={"groups": [{"evidence": [{"text": "legacy"}]}]},
    )
    db.add(job)
    db.commit()
    dreaming.tick()
    db.expire_all()
    assert db.get(MemoryDream, job.id).state == "cancelled"
    assert db.get(MemoryDream, job.id).payload == {}
    assert db.scalar(select(MemoryDream).where(MemoryDream.state == "queued"))
    assert not controller.calls


def test_stale_source_does_not_block_future_passes(db, controller, monkeypatch):
    enable(db)
    original = controller.call

    def reject(enabled, operation, **kwargs):
        if operation == "dream_evaluate":
            raise MemoryError("conflict", "Source changed")
        return original(enabled, operation, **kwargs)

    monkeypatch.setattr(dreaming, "memory_call", reject)
    dreaming.queue(db, immediate=True)
    dreaming.tick()
    db.expire_all()
    assert db.scalar(select(MemoryDream)).state == "cancelled"
    assert controller.commits == 0


def test_disabled_memory_blocks_undo_without_contacting_babar(client, controller):
    response = client.post(
        f"/api/advisor/dreaming/undo/{controller.operation}",
        json={"expected_revision": 1},
    )
    assert response.status_code == 409
    assert not controller.calls


def test_forgetting_jobs_during_model_call_discards_late_result(
    db, controller, monkeypatch
):
    enable(db)
    dreaming.queue(db, immediate=True)

    def forget(*args):
        with dreaming.Session() as other:
            dreaming.cancel(other, purge=True)
        return "uninterpreted model response"

    monkeypatch.setattr(dreaming, "chat_with_model", forget)
    dreaming.tick()
    assert controller.commits == 0
    assert not any(op == "dream_evaluate" for op, _ in controller.calls)
