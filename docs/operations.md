# Setup and operations

[Documentation index](README.md) · [User guide](user-guide.md) · [API](api.md)

## Install and run

Use Python 3.11+, `uv`, Node.js 20.19+ or 22.12+, and local PostgreSQL. Ollama and a
Brave key are optional. Run commands from the repository root unless noted.

```sh
uv sync
cp .env.example .env
```

Edit `.env` for your database login. Create the database with a PostgreSQL role
that can own/create its app tables; `createdb` may require a role with `CREATEDB`
or a database created for it by your local administrator.

```sh
createdb --host=127.0.0.1 --port=5432 --username=YOUR_DB_USER --password abacus
uv run alembic upgrade head
npm ci --prefix frontend
npm run build --prefix frontend
uv run uvicorn abacus.main:app --host 127.0.0.1 --port 8017
```

Visit **http://127.0.0.1:8017**. Migrations create starter categories and singleton
settings, not sample financial records. The production frontend is served from
`frontend/dist`; build it before starting FastAPI. API docs are at `/docs` and the
machine-readable schema at `/openapi.json`. `GET /api/health` checks database access.

Use one server worker. Statement processing uses an in-process background executor;
startup marks interrupted work recoverable and catches up due ACH debits. The
backend must be running to generate scheduled ACH actuals. There is no folder
watcher, cron import integration, bank synchronization, or external notification
service.

## Automatic startup on macOS

Use the user LaunchAgent included with Abacus. It starts after reboot **when you
log into your macOS account**, rather than before login. It also restarts after a
process failure. Existing Homebrew/PostgreSQL login services can start the database;
Abacus waits for database connectivity/schema readiness instead of assuming startup
order. Ollama remains an optional separately managed service. Temporal, Docker
Compose, and a cron daemon are not needed for this setup.

Complete installation, `.env`, migrations, and the frontend build first, then run
as your normal user, without `sudo`:

```sh
uv run python scripts/macos_service.py install
uv run python scripts/macos_service.py status
```

The installer writes `~/Library/LaunchAgents/local.abacus.plist` and loads it in the
current GUI login session. It uses the workspace's absolute `.venv/bin/python` and
`scripts/run_service.py`, not a shell startup file. There are no startup package
installs, model downloads, automatic migrations, or credentials in the plist. The
app reads its existing `.env`. An exported shell-only `DATABASE_URL` is not copied
into the agent; put the intended connection in `.env` for unattended startup.

The runner waits if PostgreSQL is unavailable, migrations are pending, the frontend
is missing, or another server occupies its port. It never terminates that other
server or starts a second application worker alongside it. If a manually started
Abacus is already running, stop that terminal server when ready; the managed service
will take over when the port becomes available. Run only the managed instance once
it has taken over. HTTP access stays on `127.0.0.1`, port 8017 by default.

| Command | Behavior |
| --- | --- |
| `uv run python scripts/macos_service.py install` | Install/reinstall for this workspace and enable login startup |
| `uv run python scripts/macos_service.py install --port 8020` | Explicit alternate HTTP port; update Vite's proxy if needed |
| `uv run python scripts/macos_service.py install --dry-run` | Print the generated plist without changing services/files |
| `uv run python scripts/macos_service.py status` | Show registration, process state/PID, and log location |
| `uv run python scripts/macos_service.py stop` | Stop and disable startup until `start` is used again |
| `uv run python scripts/macos_service.py start` | Enable startup and start the installed service |
| `uv run python scripts/macos_service.py restart` | Reload the installed service while retaining startup |
| `uv run python scripts/macos_service.py uninstall` | Remove this login service; retain budget, workspace, and logs |

Logs are private to your user under `~/Library/Logs/Abacus/stdout.log` and
`stderr.log`. Routine HTTP access logging is disabled for this service; startup and
error diagnostics remain. Read recent messages with:

```sh
tail -n 60 "$HOME/Library/Logs/Abacus/stderr.log"
curl --fail http://127.0.0.1:8017/api/health
```

`status` shows the process, which may still be waiting for prerequisites; `/api/health`
confirms the running HTTP service/database. A normal process restart is automatic;
repeat failures are throttled. The service does not wake a sleeping Mac, open a
browser, run before login, or launch external budget notifications. Keep a bookmark
for the local dashboard.

For upgrades, use `stop`, follow the [upgrade procedure](#upgrade), then `start`
instead of starting a second terminal server. Do not restart while an important
statement extraction is in progress; interrupted jobs remain recoverable. Before moving the workspace, uninstall the service and reinstall from the new
location afterward. Reinstall if you recreate the virtual environment. A service
owned by a different workspace must be uninstalled there first. Log files are
retained on uninstall; manage their retention locally when the service is stopped.

## Configuration

Copy [`.env.example`](../.env.example); do not commit your `.env`.

| Attribute | Default/example | Purpose |
| --- | --- | --- |
| `HOST` | `127.0.0.1` | PostgreSQL host |
| `PORT` | `5432` | PostgreSQL port; separate from the HTTP server port |
| `USER` | `abacus` in the example | PostgreSQL role |
| `PASS` | Replace the example value | PostgreSQL password |
| `DATABASE` | `abacus` | Budget database name |
| `DATABASE_URL` | Optional full SQLAlchemy URL | Explicit override of the five connection attributes |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Loopback-only local model endpoint |
| `ADVISOR_TIMEOUT_SECONDS` | `300` | Advisor generation/read limit, from 30 to 1800 seconds |
| `BRAVE_SEARCH_API_KEY` | Empty | Optional public travel research through Brave |
| `APP_TIMEZONE` | `America/Detroit` | Calendar date for due lists, reserve/card checks, and advisor relative dates |

The backend/Alembic read `.env` at the project root. Its discrete values take
precedence over inherited environment values, particularly a login shell's `USER`.
An exported `DATABASE_URL` explicitly overrides those attributes and a file URL.
Use `postgresql+psycopg://` for a full SQLAlchemy URL.

Discrete credentials use SQLAlchemy's URL builder. Quote `.env` values with spaces
or special characters; do not URL-escape `PASS` in the separate-attribute format.
Credentials embedded in a full URL must be URL-encoded. `.env` interpolation is
disabled. Do not paste real credentials into documentation, chat, or shell history.
Restart the backend after changing its database connection.

Currency, categories, account names, card monitoring/mappings, savings, reserve
preferences, and selected local model/advisor opt-in live in PostgreSQL. Merchant
normalization patterns live separately in
[`backend/abacus/payee_matching.json`](../backend/abacus/payee_matching.json).
Patterns reload on the next classification pass, including an open review's
**Apply remembered payees**. Invalid config disables optional regex/similarity
matching and logs a warning; exact/basic memory remains available.

## Development

Run the backend on loopback with reload:

```sh
uv run uvicorn abacus.main:app --host 127.0.0.1 --port 8017 --reload
```

In another terminal:

```sh
npm ci --prefix frontend
npm run dev --prefix frontend
```

Visit **http://127.0.0.1:5173**. Vite proxies `/api` to port 8017, configured in
[`frontend/vite.config.ts`](../frontend/vite.config.ts). Update that target if you
change backend ports. Frontend changes hot-reload in development; production uses
the built assets and requires a rebuild/refresh.

Navigation is local React state, rather than separate server URLs per screen.
Reloading starts at Overview and restores the default previous-month actual period;
chat, selected view, chart filters, and upload-queue UI state are not durable data.
Uploaded import jobs/reviews are durable and can be reopened from Statement imports.

## Optional local model and web research

Start Ollama separately and install a suitable model using your own local Ollama
setup. Abacus does not download models or select Gemma/Granite automatically.
Choose an installed model using **Settings → Refresh models**. Enable Budget advisor
if desired; choosing a model alone also permits optional PDF row extraction.
CSV/manual categorization does not require or call Ollama.

Ollama must use HTTP on loopback, without URL paths or credentials. Redirects and
proxy environment variables are not used for model requests. Keep Ollama configured
for local execution, including disabling its cloud features if used elsewhere.

Run a synthetic chat smoke check without touching the database:

```sh
uv run python scripts/check_local_model.py YOUR_INSTALLED_MODEL
```

Inspect its reply; this is not an automated guarantee of financial accuracy or PDF
extraction quality. Automated tests mock models instead of depending on local
hardware or a particular model. Advisor requests use bounded replies/no-thinking
options where supported. PDF extraction has its own transport settings; the advisor
timeout attribute is not a general import timeout setting.

To add web research, obtain your own Brave Search API key, set it in `.env`, and
refresh **Budget advisor → Travel research → Refresh connection**. Research becomes
available and initially selected when a key is available; a reconciliation handoff
explicitly starts with it off. Your selection remains under your control. Brave
usage/quota belongs to your account; no API key is bundled or exposed to the browser.

There are at most three searches per researched turn, up to four results per query.
Abacus sends public travel queries rather than database budget values, credentials,
or assistant financial replies. Excerpts go to the local advisor with clickable
source links. No arbitrary page retrieval, reservations, account login, or purchases
occur. Model/research failures are visible and do not mutate financial records.

## Upgrade

Stop the running server before an upgrade. Preserve a database backup and a copy
of the app version/configuration used with it. After updating the source:

```sh
uv sync
uv run alembic upgrade head
npm ci --prefix frontend
npm run check --prefix frontend
npm run build --prefix frontend
uv run uvicorn abacus.main:app --host 127.0.0.1 --port 8017
```

Refresh the browser after rebuilding. A running Python process must be restarted
to load changed backend code/routes. A frontend built before the new backend can
otherwise show missing endpoints or outdated controls.

Check schema status without changing data:

```sh
uv run alembic current
uv run alembic heads
uv run alembic check
```

Use `upgrade head`, not manual table creation. Migrations retain financial history;
review individual migration code before rolling backwards. Downgrades may drop
feature-specific data. In particular, reserve setup is explicit: its migration
preserves an existing nonfuture savings opening balance as a dated observation,
without inventing a reserve target.

## Backup and restore

PostgreSQL contains the budget, actuals, imports/review provenance, payee memory,
per-card mappings, guide values, savings observations, reserve plans, and payment
history. Browser storage is not the budget database.

Use PostgreSQL tools with the configured host, port, and role. `--password` prompts
rather than putting a password into the command. A SQLAlchemy URL containing
`postgresql+psycopg://` is not a `pg_dump` connection URL.

```sh
pg_dump --host=127.0.0.1 --port=5432 --username=YOUR_DB_USER --password \
  --format=custom --file=abacus-backup.dump abacus

createdb --host=127.0.0.1 --port=5432 --username=YOUR_DB_USER --password abacus_restored
pg_restore --host=127.0.0.1 --port=5432 --username=YOUR_DB_USER --password \
  --no-owner --dbname=abacus_restored abacus-backup.dump
```

Restore into a new database first. Check it with the appropriate application
version and migrations before switching `DATABASE`/`DATABASE_URL`. Stop the app
while switching, then restart it. Do not run tests against the restored budget.

Back up `.env` and custom payee patterns separately, using a private location; a
database dump does not include them. Backups, source excerpts, and optional
training exports contain private financial information. Clearing browser storage
or switching browsers does not remove PostgreSQL data.

## Tests and verification

Create a dedicated database whose name begins with `abacus_test`. Tests delete its
app data. Their fixture rejects other database names; do not point test migrations
or tests at the personal budget database.

```sh
createdb --host=127.0.0.1 --port=5432 --username=YOUR_DB_USER --password abacus_test
export TEST_DATABASE_URL='postgresql+psycopg://YOUR_DB_USER:URL_ENCODED_PASSWORD@127.0.0.1:5432/abacus_test'
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head
uv run pytest -q
npm run check --prefix frontend
npm run build --prefix frontend
```

Set the test URL through your own secure environment configuration when using real
credentials; the URL above is only a placeholder. Without `TEST_DATABASE_URL`, the
fixture uses `postgresql+psycopg://localhost/abacus_test`, which must still have valid
local role authentication. Tests use synthetic statements, mocked extraction/chat,
and mocked research. They cover recurrence/annual rounding, overrides, forecasts,
actuals/refunds, ACH, confirmations, charts/means/guides, savings/reserves, mappings,
classification, duplicates, atomic saves, undo/delete/restart recovery, and loopback
constraints.

Manual release checks: narrow/short screens, keyboard forms and dialogs, chart
reference tables, one reviewed CSV import/overlap, undo, a reserve balance update,
and optional local-model smoke check. A successful build may include a Vite bundle
size advisory; inspect performance separately if changing dependencies or chart code.

Export reviewed labels for local experiments:

```sh
uv run python scripts/export_training_data.py --output .training/examples.jsonl
```

This refuses to overwrite a file and exports saved descriptions, normalized payees,
types, category IDs, and dates. It does not train a model. See the
[classification guide](../training/README.md) for privacy and evaluation details.

## Privacy and data

Abacus has no login and is intended for a trusted local machine. Bind FastAPI to
loopback. It rejects nonlocal hostnames and cross-origin writes outside the app's
allowed local origins; those checks are not a substitute for authentication or a
public deployment design. Keep the database and app private.

| Data/process | Where it goes or remains |
| --- | --- |
| Forecasts, actuals, schedules, observations, memory, settings | Local PostgreSQL |
| Uploaded original files | Discarded after preparation/extraction rather than kept as originals |
| Extracted CSV/PDF review input | Retained locally for review/retry until commit |
| Reviewed rows and source provenance | Retained with imports/transactions; may contain sensitive text |
| PDF extraction | Extracted statement text to the configured loopback Ollama model |
| Advisor budget context | Local model receives aggregates, schedule/purchase/category names, assumptions, and chat; no raw statements or individual transaction descriptions |
| Optional web research | Public travel queries to Brave; visible search terms/results |
| Chat and upload queue UI | Current tab memory; saved import jobs remain in PostgreSQL |
| Merchant patterns / optional export | Local repository config / explicitly selected export file |

Import undo deletes linked transactions but keeps the import/fingerprint; deleting
an eligible import removes its review data/fingerprint. Payee memory survives undo
and import deletion. Recorded payment status, ACH actual generation, and manual
reserve observations are separate mechanisms. Abacus does not initiate banking
transactions, download models, send external notifications, or offer cloud fallback.

## Troubleshooting

| Symptom | Check/action |
| --- | --- |
| Database login fails | Check all five attributes, role access, server/port, and any overriding `DATABASE_URL`; `.env` wins over inherited `USER`. Do not print credentials. |
| Missing column/table | Stop app, run `uv run alembic upgrade head` against the intended database, restart. |
| Automatic startup not serving | Use the service `status` command and check logs for an occupied port, unavailable PostgreSQL, pending migrations, or missing frontend. Install in the logged-in GUI user session. |
| `/` missing or old UI | Build `frontend/dist`, restart FastAPI, refresh browser. `/api/health` can still work without built assets. |
| Vite API request fails | Run the backend on the proxy's configured port (8017 by default). |
| API reports 403 on writes | Use the loopback app URL or supported Vite origin; do not expose through an arbitrary origin. |
| Advisor is not in the menu | Select an installed model, enable it in Settings, save. |
| Local model unavailable / empty list | Start Ollama, verify loopback URL, refresh models, and choose an installed model. CSV/manual review remains usable. |
| Advisor 504/slow response | Raise `ADVISOR_TIMEOUT_SECONDS` within 30–1800, choose a faster installed model, and account for cold starts. Any proxy must allow the longer request. Retry the restored question. |
| PDF failed/interrupted | Open its import, retry local extraction or repair rows manually. A restarted job is recoverable; no partial actuals were saved. |
| PDF rejected | Supply selectable text/CSV; scans, over-100-page PDFs, or over-500,000-character extracted text are unsupported. |
| CSV mapping resets or wrong columns | Open an unfinished CSV for that account; use **Apply & remember mapping**. Required header changes need remapping. |
| Refunds treated as purchases | The default is purchase regardless of sign; choose the correct sign convention and review types. |
| PAYMENT row needs a different type | Correct it explicitly in review; keyword defaults are overridable. |
| No new rows saved from overlap | Original fields matched an earlier saved CSV row for that account. Inspect skipped counts; repeats inside one file remain selectable. |
| Reupload blocked after undo | Delete the undone import to release its exact-file fingerprint. |
| Remembered category seems wrong | Clear the review category before applying memory; inspect exact rule/category conflicts, pattern formats, and similarity labels. Existing descriptions in Settings are not canonical groups. |
| Remembered payees list keeps growing | Saving new exact variants is intentional. Normalization affects matching, not automatic record consolidation. |
| ACH missing from actual total | Check the actual period (previous month by default), active range, recording start, day, account, and running backend. Deleted generated occurrences are not regenerated. |
| Actual total differs from forecast | Forecasts and actuals are independent. Confirm transaction types, refunds, dates, card settlement exclusion, and possible imported/generated ACH overlap. |
| Monthly room positive but savings falls | An annual payment can draw saved allocations. Read cash expenses and named annual payments in Purchase planner. |
| Reserve asks for an update | Record an opening balance dated on/after the latest checkpoint; an old balance does not prove a missed transfer. |
| Reserve target ignores a new balance | Deliberate: the funding baseline is fixed. Use the observation to check progress; explicitly replace the target only when changing the plan. |
| Reserve target ignores an edited bill | Review the schedule-changed notice and explicitly replace the target to adopt the new annual schedules. |
| Calendar checks use the wrong date | Set a valid `APP_TIMEZONE`; due/reserve/card checks are independent of the selected forecast month. |

The code entry points are [`main.py`](../backend/abacus/main.py),
[`budget.py`](../backend/abacus/budget.py), [`savings.py`](../backend/abacus/savings.py),
[`reserves.py`](../backend/abacus/reserves.py), and
[`classification.py`](../backend/abacus/classification.py).
