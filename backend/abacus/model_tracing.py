"""Explicit opt-in LangSmith telemetry; trace failures never retry model calls."""

from contextvars import ContextVar
from functools import lru_cache, wraps
from inspect import signature
from urllib.parse import urlparse
from weakref import WeakSet

from .config import local_config

_workflow = ContextVar("abacus_model_workflow", default="model")
_usage = ContextVar("abacus_model_usage", default=None)
_clients = WeakSet()


def model_workflow(name):
    def decorate(function):
        @wraps(function)
        def call(*args, **kwargs):
            token = _workflow.set(name)
            try:
                return function(*args, **kwargs)
            finally:
                _workflow.reset(token)

        return call

    return decorate


def record_model_usage(payload):
    usage = _usage.get()
    if usage is None:
        return
    for source, target in [
        ("prompt_eval_count", "input_tokens"),
        ("eval_count", "output_tokens"),
    ]:
        value = payload.get(source)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            usage[target] = value
    if "input_tokens" in usage and "output_tokens" in usage:
        usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]


@lru_cache(maxsize=2)
def _client(endpoint, key, workspace):
    from langsmith import Client
    from urllib3.util.retry import Retry

    client = Client(
        api_url=endpoint,
        api_key=key,
        workspace_id=workspace or None,
        timeout_ms=2000,
        retry_config=Retry(total=0),
        auto_batch_tracing=True,
        tracing_mode="langsmith",
    )
    _clients.add(client)
    return client


def _new_run(name, arguments):
    config = local_config()
    # Do not infer consent from an API key, SDK context, or legacy tracing flags.
    if str(config.get("LANGSMITH_TRACING", "")).lower() != "true":
        return None, False
    key = config.get("LANGSMITH_API_KEY", "").strip()
    if not key:
        return None, False
    endpoint = config.get(
        "LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"
    ).rstrip("/")
    parsed = urlparse(endpoint)
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not parsed.hostname
        or not (
            parsed.scheme == "https"
            or parsed.scheme == "http"
            and parsed.hostname in ("localhost", "127.0.0.1", "::1")
        )
    ):
        return None, False
    capture = str(config.get("LANGSMITH_CAPTURE_CONTENT", "")).lower() == "true"
    from langsmith.run_trees import RunTree

    metadata = {
        "ls_provider": "ollama",
        "ls_model_name": arguments.get("model", ""),
        "ls_model_type": "chat",
        "workflow": _workflow.get(),
        "structured": arguments.get("schema") is not None,
        "capture_content": capture,
    }
    if arguments.get("max_tokens") is not None:
        metadata["max_tokens"] = arguments["max_tokens"]
    inputs = {"model": arguments.get("model", ""), "structured": metadata["structured"]}
    if capture:
        inputs.update(
            {
                k: arguments[k]
                for k in ("messages", "prompt", "schema")
                if k in arguments
            }
        )
    run = RunTree(
        name=name,
        run_type="llm",
        inputs=inputs,
        extra={"metadata": metadata},
        tags=["abacus", "ollama", _workflow.get()],
        project_name=config.get("LANGSMITH_PROJECT", "abacus"),
        replicas=[],
        client=_client(endpoint, key, config.get("LANGSMITH_WORKSPACE_ID", "")),
    )
    run.post()
    return run, capture


def _finish(run, usage, result=None, error=None, capture=False):
    if run is None:
        return
    try:
        outputs = {"truncated": bool(getattr(result, "truncated", False))}
        if capture and error is None:
            outputs["output"] = result if isinstance(result, dict) else str(result)
        if usage:
            run.add_metadata({"usage_metadata": usage})
            outputs["usage_metadata"] = usage
        # Exception messages/tracebacks can contain prompts or financial data.
        run.end(outputs=outputs, error=type(error).__name__ if error else None)
        run.patch()
    except Exception:
        pass


def traced_model(name):
    def decorate(function):
        parameters = signature(function)

        @wraps(function)
        def call(*args, **kwargs):
            run, capture = None, False
            usage = {}
            token = _usage.set(usage)
            try:
                try:
                    run, capture = _new_run(
                        name, parameters.bind(*args, **kwargs).arguments
                    )
                except Exception:
                    # Configuration, SDK and exporter failures are optional telemetry.
                    pass
                try:
                    result = function(*args, **kwargs)
                except BaseException as error:
                    _finish(run, usage, error=error, capture=capture)
                    raise
                _finish(run, usage, result=result, capture=capture)
                return result
            finally:
                _usage.reset(token)

        return call

    return decorate


def flush_model_traces():
    for client in list(_clients):
        try:
            client.flush(timeout=2)
        except Exception:
            pass
