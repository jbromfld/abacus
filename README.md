# Abacus

A local personal budget app: recurring income and bills, purchase estimates, actual spending, and 12-month category trends. React/TypeScript + FastAPI + PostgreSQL, with classification memory, an optional local Budget advisor, and optional Ollama PDF extraction.

## Documentation

- [Documentation index and feature map](docs/README.md)
- [User guide: every screen and workflow](docs/user-guide.md)
- [Setup, configuration, upgrades, backups, and troubleshooting](docs/operations.md)
- [Complete API reference](docs/api.md)
- [Classification memory and future training](training/README.md)

Use the user guide for daily workflows and Operations for maintenance. Feature details live in those guides to keep one source of truth.

## Quick start

Requirements: Python 3.11+, `uv`, Node.js 24 LTS or 26+, and a running local PostgreSQL instance. Ollama is optional; manual transaction entry and CSV review work without it.

```sh
uv sync
cp .env.example .env
# Edit HOST, PORT, USER, PASS, and DATABASE for your local PostgreSQL login.
# If the database does not exist yet, create it with your local login:
createdb --host=127.0.0.1 --port=5432 --username=YOUR_DB_USER --password
uv run alembic upgrade head
cd frontend
npm ci
npm run build
cd ..
uv run uvicorn abacus.main:app --host 127.0.0.1 --port 8017
```

The backend and Alembic automatically read `.env` from the project root. `HOST`, `PORT`, `USER`, `PASS`, and `DATABASE` describe the PostgreSQL connection. File values take precedence over inherited shell values (particularly the login shell’s `USER`). Passwords are passed through SQLAlchemy’s URL builder, so characters such as `@`, `:`, `/`, and `#` do not need URL escaping; quote values in `.env` when needed. An exported `DATABASE_URL` explicitly overrides the discrete attributes, useful for tests or alternate setups. Do not commit `.env`.

Open **http://127.0.0.1:8017**. Use one server worker: import jobs run in a single local background thread, and startup marks unfinished jobs as interrupted. Do not expose this unauthenticated app to your LAN or the Internet. Nothing is deployed automatically.

Start in **Settings**: select your currency before creating entries, add a named card account, and optionally choose an installed Ollama model for Budget advisor or PDF extraction. Starter categories are editable. No sample financial records are inserted.

### Start automatically on macOS

After completing Quick start, install the per-user login service:

```sh
uv run python scripts/macos_service.py install
uv run python scripts/macos_service.py status
```

Abacus starts now and after a restart when you log in. It waits for PostgreSQL,
runs one loopback worker, and restarts after process failure. Existing servers on
the port are left alone until they stop. See [automatic startup and controls](docs/operations.md#automatic-startup-on-macos)
for stop/start/restart/uninstall, logs, and updates. Temporal, Docker, and cron are
not required for this local macOS setup.

### Update and restart

For an installed macOS login service, apply the current workspace changes with:

```sh
python3 scripts/update.py
```

This stops Abacus, syncs locked dependencies, migrates, rebuilds, and starts it.
Use `--dry-run` to preview commands. A failed update stops before later steps.
See [upgrade and recovery details](docs/operations.md#upgrade).

### Development

Start the Python server as above with `--reload`, then in another terminal:

```sh
cd frontend
npm run dev
```

Open http://127.0.0.1:5173. Vite proxies `/api` to port 8017. If you use another backend port, update `frontend/vite.config.ts`. Rebuild the frontend and restart FastAPI after changing production assets. Interactive API documentation is at `/docs`.

## Verify before merging

See [verification and CI](docs/operations.md#tests-and-verification) for the
isolated PostgreSQL test setup, frontend behavior tests, lint, formatting, schema
checks, and production build. The GitHub Actions workflow runs those checks on
pull requests. See [the review fixes](docs/review-fixes.md) for migration 0012 and
this change’s regression coverage.
