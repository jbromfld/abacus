import json
from unittest.mock import Mock

import pytest
from abacus import model_tracing as tracing
from abacus.local_model import ModelReply


def config(monkeypatch, capture=False):
    monkeypatch.setattr(
        tracing,
        "local_config",
        lambda: {
            "LANGSMITH_TRACING": "true",
            "LANGSMITH_API_KEY": "synthetic-secret",
            "LANGSMITH_PROJECT": "synthetic",
            "LANGSMITH_CAPTURE_CONTENT": str(capture).lower(),
        },
    )
    client = Mock()
    monkeypatch.setattr(tracing, "_client", lambda *args: client)
    return client


def test_disabled_tracing_does_not_instantiate_client(monkeypatch):
    monkeypatch.setattr(
        tracing, "local_config", lambda: {"LANGSMITH_API_KEY": "unused"}
    )
    monkeypatch.setattr(
        tracing, "_client", lambda *args: pytest.fail("Tracing without opt-in")
    )

    @tracing.traced_model("test")
    def call(model, messages):
        return ModelReply("result", truncated=True)

    reply = call("local", [{"content": "private"}])
    assert reply.truncated


def test_metadata_only_keeps_prompts_results_and_exception_messages_local(monkeypatch):
    client = config(monkeypatch)

    @tracing.model_workflow("memory_dreaming")
    @tracing.traced_model("abacus.ollama.chat")
    def call(model, messages):
        tracing.record_model_usage({"prompt_eval_count": 20, "eval_count": 5})
        return ModelReply("private answer", truncated=True)

    result = call("local", [{"content": "private budget"}])
    assert result.truncated
    created = client.create_run.call_args.kwargs
    updated = client.update_run.call_args.kwargs
    assert created["run_type"] == "llm"
    assert created["session_name"] == "synthetic"
    assert "memory_dreaming" in created["tags"]
    assert updated["outputs"]["usage_metadata"]["total_tokens"] == 25
    assert updated["outputs"]["truncated"]
    serialized = str(client.mock_calls)
    assert "private" not in serialized and "synthetic-secret" not in serialized


def test_content_capture_requires_separate_flag(monkeypatch):
    client = config(monkeypatch, capture=True)

    @tracing.traced_model("test")
    def call(model, prompt, schema):
        return {"rows": [1]}

    call("local", "synthetic prompt", {"type": "object"})
    assert client.create_run.call_args.kwargs["inputs"]["prompt"] == "synthetic prompt"
    assert client.update_run.call_args.kwargs["outputs"]["output"] == {"rows": [1]}


def test_error_trace_contains_only_exception_type_and_preserves_original(monkeypatch):
    client = config(monkeypatch)
    failure = ValueError("private financial evidence")

    @tracing.traced_model("test")
    def call(model):
        raise failure

    with pytest.raises(ValueError) as exc:
        call("local")
    assert exc.value is failure
    assert client.update_run.call_args.kwargs["error"] == "ValueError"
    assert "private" not in str(client.mock_calls)


def test_export_failures_never_repeat_or_change_model_call(monkeypatch):
    client = config(monkeypatch)
    client.create_run.side_effect = RuntimeError("export unavailable")
    calls = []

    @tracing.traced_model("test")
    def call(model):
        calls.append(model)
        return "answer"

    assert call("local") == "answer" and calls == ["local"]
    client.create_run.side_effect = None
    client.update_run.side_effect = RuntimeError("patch unavailable")
    assert call("local") == "answer" and calls == ["local", "local"]


def test_real_chat_transport_records_final_ollama_usage(monkeypatch):
    import httpx
    from abacus import local_model

    client = config(monkeypatch)
    monkeypatch.setattr(local_model, "available_models", lambda: ["local"])
    real_client = httpx.Client

    def handler(request):
        return httpx.Response(
            200,
            text=json.dumps(
                {
                    "message": {"content": "Answer"},
                    "done": True,
                    "prompt_eval_count": 10,
                    "eval_count": 3,
                }
            )
            + "\n",
        )

    monkeypatch.setattr(
        local_model.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    assert (
        local_model.chat_with_model("local", [{"role": "user", "content": "private"}])
        == "Answer"
    )
    assert client.update_run.call_args.kwargs["outputs"]["usage_metadata"] == {
        "input_tokens": 10,
        "output_tokens": 3,
        "total_tokens": 13,
    }
