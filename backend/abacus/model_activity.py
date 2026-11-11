"""Serialize local generation, giving interactive callers priority between jobs."""

from contextlib import contextmanager
from functools import wraps
from threading import Condition, local

_condition = Condition()
_active = False
_waiting = 0
_local = local()


def interactive_model(function):
    @wraps(function)
    def call(*args, **kwargs):
        global _active, _waiting
        if getattr(_local, "background", False):
            return function(*args, **kwargs)
        with _condition:
            _waiting += 1
            try:
                _condition.wait_for(lambda: not _active)
                _active = True
            finally:
                _waiting -= 1
        try:
            return function(*args, **kwargs)
        finally:
            with _condition:
                _active = False
                _condition.notify_all()

    return call


@contextmanager
def background_model():
    global _active
    with _condition:
        allowed = not _active and not _waiting
        if allowed:
            _active = True
    if not allowed:
        yield False
        return
    _local.background = True
    try:
        yield True
    finally:
        _local.background = False
        with _condition:
            _active = False
            _condition.notify_all()
