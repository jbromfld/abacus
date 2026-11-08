"""Rebuild and restart the installed macOS Abacus service from this workspace."""

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEPS = (
    (
        "Stop Abacus",
        ("uv", "run", "--no-sync", "python", "scripts/macos_service.py", "stop"),
    ),
    ("Sync locked Python dependencies", ("uv", "sync", "--locked")),
    ("Upgrade database", ("uv", "run", "--no-sync", "alembic", "upgrade", "head")),
    (
        "Configure advisor permissions",
        ("uv", "run", "--no-sync", "python", "scripts/setup_advisor.py"),
    ),
    ("Install locked frontend dependencies", ("npm", "ci", "--prefix", "frontend")),
    ("Build frontend", ("npm", "run", "build", "--prefix", "frontend")),
    (
        "Start Abacus",
        ("uv", "run", "--no-sync", "python", "scripts/macos_service.py", "start"),
    ),
)


def preflight():
    if sys.platform != "darwin":
        raise RuntimeError("Run this updater on macOS in your logged-in user session.")
    if os.geteuid() == 0:
        raise RuntimeError("Run as your normal user, without sudo.")
    for tool in ("uv", "npm"):
        if not shutil.which(tool):
            raise RuntimeError(f"Install {tool} and make it available on PATH first.")
    for relative in (
        ".venv/bin/python",
        ".env",
        "frontend/package-lock.json",
        "scripts/macos_service.py",
    ):
        if not (ROOT / relative).is_file():
            raise RuntimeError(f"Missing {relative}. Complete initial setup first.")
    agent = Path.home() / "Library/LaunchAgents/local.abacus.plist"
    if not agent.is_file():
        raise RuntimeError("Install the macOS login service before using this updater.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Show commands without changing anything"
    )
    args = parser.parse_args(argv)
    print(f"Workspace: {ROOT}", flush=True)
    if args.dry_run:
        for label, command in STEPS:
            print(f"{label}: {shlex.join(command)}")
        return 0
    try:
        preflight()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    stopped = False
    for label, command in STEPS:
        print(f"\n{label}…", flush=True)
        try:
            subprocess.run(command, cwd=ROOT, check=True)
        except (subprocess.CalledProcessError, OSError, KeyboardInterrupt) as exc:
            print(f"\nUpdate stopped at: {label}.", file=sys.stderr)
            if label == "Start Abacus" or not stopped:
                print(
                    "Check service status with python3 scripts/macos_service.py status.",
                    file=sys.stderr,
                )
            else:
                print(
                    "Abacus remains stopped and login startup is disabled. Fix the error and rerun this updater.",
                    file=sys.stderr,
                )
            return 130 if isinstance(exc, KeyboardInterrupt) else 1
        if label == "Stop Abacus":
            stopped = True
    print("\nUpdate complete; Abacus startup requested. Refresh your browser.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
