"""Provision/check the dedicated local advisor login without displaying credentials."""

import argparse
import sys

from abacus.advisor_setup import (
    AdvisorSetupError,
    check_connection,
    persist_credentials,
    provision_advisor,
)
from abacus.config import (
    ENV_FILE,
    administrator_database_url,
    advisor_database_url,
    local_config,
)
from sqlalchemy.engine import make_url


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--rotate-password",
        action="store_true",
        help="Generate and persist a new password for the managed role",
    )
    group.add_argument(
        "--check",
        action="store_true",
        help="Verify credentials and privileges without changing anything",
    )
    args = parser.parse_args(argv)
    try:
        if args.check:
            check_connection(advisor_database_url())
        else:
            if not ENV_FILE.is_file() or ENV_FILE.is_symlink():
                raise AdvisorSetupError(
                    "Use an existing, regular .env file before provisioning."
                )
            config = local_config()
            role = config.get("ADVISOR_USER") or "abacus_advisor"
            password = provision_advisor(
                make_url(administrator_database_url()),
                role,
                config.get("ADVISOR_PASS"),
                rotate=args.rotate_password,
            )
            persist_credentials(ENV_FILE, role, password)
    except AdvisorSetupError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (ValueError, OSError):
        # Exceptions may contain database URLs or dotenv contents. Keep console
        # errors actionable but credential-free, even for unexpected IO failures.
        print(
            "Advisor setup/check failed. Verify the application login can manage roles and grant table access, that the role is managed by this database, and that no memberships, ownership, or PUBLIC privileges violate the allowlist. Missing/unusable managed credentials require --rotate-password. The app remains fail-closed.",
            file=sys.stderr,
        )
        return 1
    print(
        "Advisor login verified: dedicated credentials and SELECT allowlist. No password is displayed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
