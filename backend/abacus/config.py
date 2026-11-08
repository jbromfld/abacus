"""Local configuration; do not interpolate credentials into URL strings."""

import os
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import URL, make_url

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def local_config():
    # File values win for discrete attributes, including USER, which login shells
    # already export. DATABASE_URL remains an explicit process-level override.
    file_values = {
        k: v
        for k, v in dotenv_values(ENV_FILE, interpolate=False).items()
        if v is not None
    }
    return {**os.environ, **file_values}


def database_url():
    config = local_config()
    explicit = os.environ.get("DATABASE_URL") or config.get("DATABASE_URL")
    if explicit:
        return explicit
    return URL.create(
        "postgresql+psycopg",
        username=config.get("USER") or None,
        password=config.get("PASS") or None,
        host=config.get("HOST", "127.0.0.1"),
        port=int(config.get("PORT", "5432")),
        database=config.get("DATABASE", "abacus"),
    )


def advisor_database_url():
    """Use the same database/transport, with mandatory dedicated credentials."""
    config = local_config()
    user, password = config.get("ADVISOR_USER"), config.get("ADVISOR_PASS")
    base = make_url(database_url())
    if not user or not password or user == base.username:
        raise ValueError("Dedicated advisor credentials are required.")
    return base.set(username=user, password=password).difference_update_query(
        ["user", "password"]
    )
