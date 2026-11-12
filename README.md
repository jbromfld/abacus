<img src="docs/assets/abacus-logo.png" alt="Abacus logo" width="240" />

A local personal budget app: recurring income and bills, purchase estimates, actual spending, and 12-month category trends. React/TypeScript + FastAPI + PostgreSQL, with classification memory, an optional local Budget advisor, and optional Ollama PDF extraction.

## Documentation

- [Documentation index and feature map](docs/README.md)
- [User guide: every screen and workflow](docs/user-guide.md)
- [Setup, configuration, upgrades, backups, and troubleshooting](docs/operations.md)
- [Complete API reference](docs/api.md)
- [Remembered payee groups, local-model review, and classification](training/README.md)
- [Optional LangSmith model tracing](docs/operations.md#optional-langsmith-model-tracing)
- [Optional local advisor memory and dreaming with Memora](docs/advisor-memory.md)
- [Unified Planning: annual bill funding, savings goals, sliders, and advisor research](docs/reserve-redesign.md)

Use the user guide for daily workflows and Operations for maintenance. Feature details live in those guides to keep one source of truth.

## Argo deployment

Abacus runs locally through Argo with its Babar stdio child bundled in the image.
See [Argo operations](docs/argo.md) for releases, restart, recovery and image
rollback. Native service support is archived in the unchanged
[v0.2.0](https://github.com/jbromfld/abacus/tree/v0.2.0) tag; version 0.3.0 uses
Argo for managed operation.

The image includes the frontend and a separate Babar environment, runs one
Uvicorn worker as UID 1000 on port 8000, and consumes runtime configuration through
Secrets. Publish committed sources with:

```sh
python3 scripts/publish_images.py --babar-revision FULL_BABAR_COMMIT
```

The publisher archives both source commits and records Babar provenance. Mount
its offline model cache read-only and its private profile at
`/run/abacus/memory.json`, owned by UID 1000 with mode 0600. Database placement is
independent of the image. Use `DATABASE_URL` for runtime and
`ABACUS_ADMIN_DATABASE_URL` for explicit Alembic/advisor maintenance; keep the
administrator DSN out of runtime Secrets.

Memory setup accepts `--admin-env` to use independent administrator `PG*`
settings and `--pre-provisioned` to maintain an existing memory database/login.
Keep the `abacus-advisor` namespace and existing model identity.

## Quick start for foreground development

Use an isolated development database. When Argo is running, choose a different
HTTP port and update the Vite proxy rather than starting a second writer against
your live database.

Requirements: Python 3.11+, `uv`, Node.js 24 LTS or 26+, and a running local PostgreSQL instance. Ollama is optional; manual transaction entry and CSV review work without it.

```sh
uv sync
cp .env.example .env
# Edit HOST, PORT, USER, PASS, and DATABASE for your local PostgreSQL login.
# If the database does not exist yet, create it with your local login:
createdb --host=127.0.0.1 --port=5432 --username=YOUR_DB_USER --password
uv run alembic upgrade head
uv run --no-sync python scripts/setup_advisor.py
cd frontend
npm ci
npm run build
cd ..
uv run uvicorn abacus.main:app --host 127.0.0.1 --port 8017
```

The backend and Alembic automatically read `.env` from the project root. `HOST`, `PORT`, `USER`, `PASS`, and `DATABASE` describe the PostgreSQL connection. File values take precedence over inherited shell values (particularly the login shell’s `USER`). Passwords are passed through SQLAlchemy’s URL builder, so characters such as `@`, `:`, `/`, and `#` do not need URL escaping; quote values in `.env` when needed. An exported `DATABASE_URL` explicitly overrides the discrete attributes, useful for tests or alternate setups. Do not commit `.env`.

Open **http://127.0.0.1:8017**. Use one server worker: import jobs run in a single local background thread, and startup marks unfinished jobs as interrupted. Do not expose this unauthenticated app to your LAN or the Internet. Nothing is deployed automatically.

Start in **Settings**: select your currency before creating entries, add a named card account, and optionally choose an installed Ollama model for Budget advisor or PDF extraction. Starter categories are editable. No sample financial records are inserted.

Migration **0016** replaces the old planning flow and clears obsolete purchase, bill-estimate, and combined reserve records. Imported expenses and recurring bills are preserved. New goals live in **Planning**. Migration **0019** removes the obsolete planning tables and APIs permanently; back up before upgrading. Current Planning goals and financial records are preserved. See [upgrade and recovery details](docs/operations.md#upgrade).

### Release and restart with Argo

Publish a committed image and promote its release metadata in
`agent-platform-gitops`. Use the [Argo operations guide](docs/argo.md) for
maintenance, restart, Secret rotation and image rollback. Database migrations and image promotion are explicit steps.

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

