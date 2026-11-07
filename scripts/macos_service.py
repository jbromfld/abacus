"""Install/manage Abacus as the current macOS user's login LaunchAgent."""

import argparse
import os
import plistlib
import subprocess
import sys
import time
from pathlib import Path

LABEL = "local.abacus"
ROOT = Path(__file__).resolve().parents[1]


def launch_agent(root, home, port=8017):
    logs = home / "Library/Logs/Abacus"
    return {
        "Label": LABEL,
        # Keep the venv path: resolving its Python symlink would lose the virtual environment.
        "ProgramArguments": [
            str(root / ".venv/bin/python"),
            str(root / "scripts/run_service.py"),
            "--port",
            str(port),
        ],
        "WorkingDirectory": str(root),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 30,
        "ExitTimeOut": 60,
        "ProcessType": "Background",
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
        "StandardOutPath": str(logs / "stdout.log"),
        "StandardErrorPath": str(logs / "stderr.log"),
    }


def installed_path(home):
    return home / "Library/LaunchAgents" / f"{LABEL}.plist"


def preflight(root):
    for relative in (
        ".venv/bin/python",
        ".env",
        "frontend/dist/index.html",
        "scripts/run_service.py",
    ):
        if not (root / relative).is_file():
            raise RuntimeError(
                f"Missing {relative}. Complete setup and the frontend build first."
            )


def control(*args, check=True):
    result = subprocess.run(["/bin/launchctl", *args], capture_output=True, text=True)
    if check and result.returncode:
        raise RuntimeError(
            result.stderr.strip()
            or f"launchctl {args[0]} failed ({result.returncode})."
        )
    return result


def registered(target):
    return control("print", target, check=False).returncode == 0


def unload(target):
    if not registered(target):
        return
    control("bootout", target)
    # bootout can return while a graceful shutdown is still removing the job.
    # Wait for that registration to disappear before loading its replacement.
    deadline = time.monotonic() + 70
    while registered(target):
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "Service is still shutting down; retry once it exits. Check Abacus logs."
            )
        time.sleep(0.2)


def assert_workspace(path, root):
    if path.exists():
        data = plistlib.loads(path.read_bytes())
        if data.get("Label") != LABEL or data.get("WorkingDirectory") != str(root):
            raise RuntimeError(
                "A different workspace owns this LaunchAgent. Remove it from that workspace first."
            )


def start(path, target, domain):
    control("enable", target)
    if registered(target):
        control("kickstart", target)
    else:
        control("bootstrap", domain, str(path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=["install", "start", "stop", "restart", "status", "uninstall"],
    )
    parser.add_argument(
        "--port", type=int, default=8017, help="HTTP port for install; default 8017"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the install plist without changing anything",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")
    if args.dry_run and args.command != "install":
        parser.error("--dry-run is for install only.")
    if args.dry_run:
        print(
            plistlib.dumps(launch_agent(ROOT, Path.home(), args.port)).decode(), end=""
        )
        return 0
    if sys.platform != "darwin":
        parser.error("Use this command on macOS in your logged-in user session.")
    if os.geteuid() == 0:
        parser.error("Run as your normal user, without sudo.")
    home = Path.home()
    path = installed_path(home)
    domain = f"gui/{os.getuid()}"
    target = f"{domain}/{LABEL}"
    try:
        assert_workspace(path, ROOT)
        if args.command == "status":
            print(
                f"Login file: {path} ({'installed' if path.exists() else 'not installed'})"
            )
            result = control("print", target, check=False)
            if result.returncode:
                print("Not loaded. Use start, or install if the login file is absent.")
                return 1
            # Do not dump the job environment; show only useful service metadata.
            for line in result.stdout.splitlines():
                if (
                    line.startswith("\t")
                    and not line.startswith("\t\t")
                    and line.strip().startswith(
                        ("state =", "pid =", "last exit code =", "runs =")
                    )
                ):
                    print(line.strip())
            print(f"Logs: {home / 'Library/Logs/Abacus'}")
            return 0
        if args.command == "install":
            preflight(ROOT)
            unload(target)
            path.parent.mkdir(parents=True, exist_ok=True)
            logs = home / "Library/Logs/Abacus"
            logs.mkdir(parents=True, exist_ok=True, mode=0o700)
            logs.chmod(0o700)
            path.write_bytes(plistlib.dumps(launch_agent(ROOT, home, args.port)))
            path.chmod(0o600)
            start(path, target, domain)
            print(f"Installed {path}. Starts now and at login after a restart.")
            print(
                f"Open http://127.0.0.1:{args.port}. An occupied port is left alone until it becomes free."
            )
        elif args.command == "start":
            if not path.exists():
                raise RuntimeError("Install the LaunchAgent first.")
            preflight(ROOT)
            start(path, target, domain)
            print("Abacus startup enabled and started.")
        elif args.command == "restart":
            if not path.exists():
                raise RuntimeError("Install the LaunchAgent first.")
            preflight(ROOT)
            unload(target)
            start(path, target, domain)
            print("Abacus restarted; startup remains enabled.")
        elif args.command == "stop":
            control("disable", target)
            unload(target)
            print(
                "Abacus stopped and login startup disabled. Use start to enable it again."
            )
        else:
            unload(target)
            path.unlink(missing_ok=True)
            print(
                "Abacus login startup removed. Database, workspace, and logs retained."
            )
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
