"""One configured calendar for all budget, scheduling, and completeness checks."""

from datetime import datetime
from zoneinfo import ZoneInfo

from .config import local_config


def local_today():
    return datetime.now(
        ZoneInfo(local_config().get("APP_TIMEZONE", "America/Detroit"))
    ).date()
