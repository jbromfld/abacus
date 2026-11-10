"""Provision optional local Memora, never enabling it or downloading model weights."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from abacus.advisor_setup import persist_local_values
from abacus.config import ENV_FILE, database_url
from sqlalchemy.engine import make_url


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--babar", type=Path, default=ENV_FILE.parent.parent / "babar")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--rotate-password", action="store_true")
    args = parser.parse_args(argv)
    try:
        root = args.babar.expanduser().resolve(strict=True)
        python = root / ".venv" / "bin" / "python"
        runtime = (args.config or root / ".memora-abacus.json").expanduser().absolute()
        if not python.is_file() or not ENV_FILE.is_file() or ENV_FILE.is_symlink():
            raise ValueError()
        url = make_url(database_url())
        if url.host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError()
        # Provisioning alone receives administrator credentials, through env rather
        # than command-line arguments. The runtime file has only the memory login.
        environment = {
            k: os.environ[k]
            for k in ("PATH", "HOME", "TMPDIR", "LANG")
            if k in os.environ
        }
        environment.update(
            PGHOST=url.host,
            PGPORT=str(url.port or 5432),
            PGDATABASE=url.database,
            PGUSER=url.username or "",
            PGPASSWORD=url.password or "",
        )
        command = [
            str(python),
            "-m",
            "memora.setup",
            "--config",
            str(runtime),
            "--namespace",
            "abacus-advisor",
            "--database",
            "abacus_memory",
            "--user",
            "abacus_memory",
        ]
        if args.rotate_password:
            command.append("--rotate-password")
        result = subprocess.run(
            command, cwd=root, env=environment, capture_output=True, timeout=90
        )
        if result.returncode:
            raise ValueError()
        persist_local_values(
            ENV_FILE, {"MEMORA_PYTHON": str(python), "MEMORA_CONFIG": str(runtime)}
        )
    except Exception:
        print(
            "Memory setup failed. Sync Babar's locked environment and verify pgvector, local admin permissions, and its managed role. Use --rotate-password only for credential recovery. No credentials were displayed or passed to the runtime service.",
            file=sys.stderr,
        )
        return 1
    print(
        "Optional Memora provisioned and local paths saved. Memory remains off until enabled in Settings; no models were downloaded."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
