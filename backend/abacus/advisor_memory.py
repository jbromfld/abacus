"""Optional local MCP adapter. Model outputs never dispatch MCP operations."""

import json
import os
from contextlib import ExitStack, asynccontextmanager
from datetime import timedelta
from pathlib import Path
from threading import RLock
from typing import Protocol
from uuid import uuid4

import anyio
from anyio.from_thread import start_blocking_portal

from .config import local_config

UNAVAILABLE = "Local memory is unavailable. Check MEMORA_PYTHON, MEMORA_CONFIG, its database, and offline model files. Advisor chat can continue without memory."
RECALL_UNAVAILABLE = "Saved notes could not be recalled for this answer. In Settings, choose Refresh memory to check the current connection, then ask again. Chat continued without memory."


class MemoryError(Exception):
    def __init__(self, code="unavailable", message=UNAVAILABLE):
        super().__init__(message)
        self.code = code


class MemoryProvider(Protocol):
    def call(self, operation: str, **arguments) -> dict: ...
    def close(self) -> None: ...


class DisabledMemory:
    def call(self, operation, **arguments):
        raise MemoryError("disabled", "Enable advisor memory in Settings first.")

    def close(self):
        pass


class MCPMemory:
    """One persistent subprocess; async context enter/exit run in the same task."""

    def __init__(self, python, config, timeout):
        self.python, self.config, self.timeout = python, config, timeout
        self.stack = None
        self.portal = self.client = None

    @asynccontextmanager
    async def connection(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        # SDK inherits only its documented OS allowlist, not arbitrary environment.
        # Explicitly pass only this service's runtime file and offline flags.
        params = StdioServerParameters(
            command=self.python,
            args=["-m", "memora.server"],
            cwd=str(Path(self.config).parent),
            env={
                "MEMORA_CONFIG": self.config,
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "HF_HUB_DISABLE_TELEMETRY": "1",
                "PYTHONUNBUFFERED": "1",
            },
        )
        with open(os.devnull, "w") as errors:
            async with stdio_client(params, errlog=errors) as (read, write):
                async with ClientSession(
                    read, write, read_timeout_seconds=timedelta(seconds=self.timeout)
                ) as client:
                    with anyio.fail_after(self.timeout):
                        await client.initialize()
                    yield client

    def call(self, operation, **arguments):
        if operation not in {
            "status",
            "search",
            "list",
            "get",
            "create",
            "update",
            "forget",
            "dream_candidates",
            "dream_prepare",
            "dream_get",
            "dream_evaluate",
            "dream_commit",
            "dream_cancel",
            "consolidate",
            "consolidation_status",
            "undo_consolidation",
            "forget_consolidation",
        }:
            raise MemoryError("invalid", "Unknown memory operation.")
        try:
            if self.stack is None:
                stack = ExitStack()
                try:
                    self.portal = stack.enter_context(start_blocking_portal())
                    self.client = stack.enter_context(
                        self.portal.wrap_async_context_manager(self.connection())
                    )
                    self.stack = stack
                except BaseException:
                    stack.close()
                    raise
            result = self.portal.call(
                self.client.call_tool, "memory_" + operation, arguments
            )
            payload = result.structuredContent
            if payload is None:
                payload = json.loads(
                    next(c.text for c in result.content if c.type == "text")
                )
            if result.isError or not isinstance(payload, dict):
                raise MemoryError()
            if not payload.get("ok"):
                # Only fixed service errors are exposed, never arbitrary server text.
                code = payload.get("code", "unavailable")
                messages = {
                    "invalid": "Invalid memory fields. Check the note and try again.",
                    "not_found": "Memory not found.",
                    "conflict": "Memory changed or was forgotten. Reload before saving.",
                }
                raise MemoryError(code, messages.get(code, UNAVAILABLE))
            return payload["data"]
        except MemoryError:
            raise
        except Exception:
            self.close()
            raise MemoryError() from None

    def close(self):
        stack, self.stack = self.stack, None
        if stack is not None:
            try:
                stack.close()
            except Exception:
                pass
        self.portal = self.client = None


_lock = RLock()
_provider = None
_key = None
_epoch = str(uuid4())


def memory_epoch():
    with _lock:
        return _epoch


def invalidate_memory():
    global _epoch
    with _lock:
        _epoch = str(uuid4())


def close_memory():
    global _provider, _key
    with _lock:
        if _provider is not None:
            _provider.close()
        _provider, _key = None, None


def provider(enabled):
    global _provider, _key
    if not enabled:
        return DisabledMemory()
    config = local_config()
    try:
        # Preserve a venv executable symlink: resolving it loses the venv site-packages.
        python = str(Path(config["MEMORA_PYTHON"]).expanduser().absolute())
        runtime = str(Path(config["MEMORA_CONFIG"]).expanduser().resolve(strict=True))
        timeout = float(config.get("MEMORA_TIMEOUT_SECONDS", "30"))
        if (
            not Path(python).is_file()
            or not os.access(python, os.X_OK)
            or not 1 <= timeout <= 120
        ):
            raise ValueError()
        key = (python, runtime, timeout, Path(runtime).stat().st_mtime_ns)
    except (KeyError, ValueError, OSError):
        raise MemoryError() from None
    if _key != key:
        close_memory()
        _provider, _key = MCPMemory(python, runtime, timeout), key
    return _provider


def memory_call(enabled, operation, **arguments):
    # Serialized operations also make forget/recall invalidation deterministic.
    with _lock:
        return provider(enabled).call(operation, **arguments)


def mutate_memory(operation, **arguments):
    with _lock:
        # The response can be lost after the service committed: invalidate first.
        invalidate_memory()
        return memory_call(True, operation, **arguments)


def recalled_memory(enabled, request):
    result = {
        "status": "disabled",
        "warnings": [],
        "notes": [],
        "epoch": memory_epoch(),
    }
    if not enabled:
        return result
    query = "\n".join(
        [m.content for m in request.history if m.role == "user"][-1:]
        + [request.message]
    )[-2000:]
    try:
        with _lock:
            candidates = memory_call(True, "search", query=query, limit=3)["items"]
            result["epoch"] = memory_epoch()
        for item in candidates[:3]:
            note = {
                key: item[key]
                for key in ("id", "revision", "title", "text", "kind", "source_date")
            }
            if (
                len(
                    json.dumps(
                        [*result["notes"], note],
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                )
                <= 1500
            ):
                result["notes"].append(note)
                if item.get("is_consolidated"):
                    detail = memory_call(True, "get", id=item["id"])
                    note["source_details"] = []
                    for source in (detail.get("consolidation") or {}).get(
                        "sources", []
                    ):
                        retained = {
                            key: source[key] for key in ("id", "source_date", "text")
                        }
                        note["source_details"].append(retained)
                        if (
                            len(
                                json.dumps(
                                    result["notes"],
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                )
                            )
                            > 1500
                        ):
                            note["source_details"].pop()
                            result["warnings"].append(
                                "Some retained source details did not fit; inspect the consolidated memory before relying on omitted amounts or constraints."
                            )
                            break
        result["status"] = "ready"
    except (MemoryError, KeyError, TypeError, ValueError):
        result.update(status="unavailable", warnings=[RECALL_UNAVAILABLE], notes=[])
    return result
