# Abacus

A local personal budget app: recurring income and bills, purchase estimates, actual spending, and 12-month category trends. React/TypeScript + FastAPI + PostgreSQL, with classification memory, an optional local Budget advisor, and optional Ollama PDF extraction.

## Quick start

Requirements: Python 3.11+, `uv`, Node.js 20.19+ or 22.12+, and a running local PostgreSQL instance. Ollama is optional; manual transaction entry and CSV review work without it.

```sh
uv sync
cp .env.example .env
# Edit HOST, PORT, USER, PASS, and DATABASE for your local PostgreSQL login.
# If the database does not exist yet, create it with your local login:
createdb --host=127.0.0.1 --port=5432 --username=YOUR_DB_USER --password abacus
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

### Development

Start the Python server as above with `--reload`, then in another terminal:

```sh
cd frontend
npm run dev
```

Open http://127.0.0.1:5173. Vite proxies `/api` to port 8017. If you use another backend port, update `frontend/vite.config.ts`. Rebuild the frontend and restart FastAPI after changing production assets. Interactive API documentation is at `/docs`.

## Card freshness alerts

In **Settings → Card accounts**, check **Alert after 30 days** next to each card
that should be monitored. Monitoring is off by default and can be toggled
independently for each card. Warnings appear in the app across all views, with an
**Import statement** action that preselects the card and current statement month.
No email, push, or operating-system notification is sent.

Information is stale when its latest dated evidence is **more than 30 days old**
(30 is current; 31 is stale). A monitored card with no saved information shows a
separate “no saved information yet” warning immediately. Evidence includes dated
saved transactions and committed statement periods. A statement period establishes
coverage through the month's end, capped at the file's upload date and today;
this is based on the period you selected when importing. Importing an old cycle
today does not make it fresh. Future records/periods and uncommitted, failed, or
undone imports do not establish current coverage. Undoing an import recalculates
coverage from the remaining information.

Dates use `APP_TIMEZONE`, independent of the budget month being viewed. Status
refreshes after app actions, every minute while the app is open, and when the tab
becomes visible. This indicates dated information availability, not bank-sync or
statement completeness verification.

## Planning rules

- Each month is independent: forecast income minus recurring payables minus **included** purchase estimates. There is no opening balance or carry-forward.
- Annual expenses are entered as yearly totals. **Distribute annual expense across 12 months** defaults on (including existing schedules), allocating the total monthly from the first active month. Uncheck it to count the full total only in the configured annual due month (or the first-month anniversary until configured), for example for a digital subscription. This option appears for annual payables only; monthly entries and annual income ignore it. Changing the flag recalculates the entire forecast schedule, including earlier months, without changing recorded actual transactions. Integer rounding cents are distributed across the first months of each 12-month rate cycle so the allocations sum exactly to the yearly amount. Annual income still counts fully in its anniversary month. Optional final months are inclusive; for distributed expenses, a partial active year includes only its active monthly allocations.
- **Adjust amount** adds an ongoing default from a chosen month or an override for that month only. Overrides take precedence; later defaults preserve earlier months. You can remove changes except the initial default.
- The first month is editable. Moving it changes the active forecast range and annual allocation anchor. For annual payments without a configured due month it also changes their anniversary month; explicitly configured due months remain independent. Amount changes and overrides retain their calendar dates; a default amount is established at the new start using the applicable existing default (or the earliest known default when moving earlier). Changes outside the active range are retained but do not contribute to forecasts. Name/category/direction edits affect the schedule globally; use amount changes for historical amount preservation. For distributed annual expenses, amount changes remain yearly totals and establish a new monthly-allocation rate from their effective month; a one-month override uses only that month’s share of its entered annual total. For annual expenses counted in their due month, effective changes apply to the next due month; one-month overrides must select a due month and replace its full payment.
- Purchases start as drafts. Preview includes the selected purchase once without saving its inclusion status.
- Actual spending is separate from forecasts: purchases and fees add spending, refunds subtract it, and payments/transfers contribute zero. All stored amounts are positive integer minor units. Use transaction dates, not statement periods, for monthly grouping.
- Forecast deficits and actual spending above forecast income produce separate **in-app** alerts. No email, push, bank connections, or automatic payments.
- USD, EUR, GBP, CAD, AUD, CHF use two decimal places; JPY uses none. One currency per budget, fixed after entries/imports exist. No currency conversion.

## Upcoming bills and payment confirmations

Overview replaces its recurring-account ledger with **Upcoming monthly bills**
(today through 30 days from today, inclusive), **Overdue monthly bills**, and a
separate **Annual expenses** panel for bills and budget allowances. These dates follow `APP_TIMEZONE` and today's
calendar date, independently of the forecast month selected at the top. Due lists
refresh every minute and when the app returns to the foreground.

Edit a payable in **Recurring accounts** to set **Bill due day** and, for annual
bills, **Annual bill due month**. These contractual dates are separate from the
ACH debit day. Short months clamp days 29–31 to their final day. Existing schedules
have no assumed due dates. Undated entries without ACH are budget allowances,
not bills with missing information. Monthly allowances such as groceries, pets,
and entertainment stay in the forecast without due-date prompts. Undated annual
allowances such as medical copays show their annual budget and monthly allocation
in Annual expenses, without payment controls. Their distribution setting remains
editable in Recurring accounts. Receivables and purchase plans
are excluded from these lists. Schedule start/end months still bound occurrences.

**Track payments from** defaults to today when a due day is first configured.
Choose an earlier date explicitly to include earlier unconfirmed bills. No overdue
history is inferred before that boundary. Annual bills show their full yearly
payment amount, including the due month's effective amount/override, regardless of
monthly forecast distribution. All active annual schedules are listed separately,
even when their next payment is within 30 days. Their oldest unconfirmed payment,
overdue count, and next scheduled date are shown when applicable.

For bills paid manually, use **Mark paid** to confirm an occurrence with a paid date no later than today;
early payment is allowed. **Edit paid date** corrects that date, and **Mark unpaid**
reverses the status. Confirmations retain their scheduled-date and amount snapshots
in expandable history. Monthly confirmations cover a calendar month; annual ones
cover a calendar year, so editing a bill's due date or amount does not erase an
existing confirmation for that period.

Paid status never creates, removes, or changes an actual-spending transaction.
ACH bills do not require manual paid confirmation. Recorded scheduled ACH debits
automatically show **Paid by ACH**; upcoming automatic occurrences show **Scheduled
ACH**. If no contractual due day is set, the ACH debit day and recording start
define the schedule. Automatic occurrences never appear as manually overdue.
ACH status is derived from the existing recorded transaction, including its date
and amount, without creating another transaction or confirmation. Disabling future
ACH recording preserves the paid status of existing debits. Automatic payment rows
have no Mark paid/Mark unpaid controls; correct their actual transaction or schedule
if necessary. This reflects the local recorded schedule, not a bank confirmation.
Imports and manual transactions do not infer paid status for manually paid bills. Annual payables counted entirely in one month use the configured due
month for their forecast; until a due date is configured, their original first-month
anniversary behavior remains. Distributed annual forecasts remain monthly.

The API provides `GET /api/recurring/dues` and idempotent
`PUT /api/recurring/{id}/payments/{period}` with `paid` and optional `paid_on`.
Periods are `YYYY-MM` for monthly bills and `YYYY` for annual bills. No bank
integration or external notifications are involved.

## Automatic ACH actual spending

In Settings, add a named bank account under **Bank & card accounts**. Edit a
monthly payable in **Recurring accounts**, check **ACH · automatically record monthly
actual spending**, and choose the account, debit day, and **Record ACH actuals from**
month. Automatic recording is off for existing bills. The recording start defaults
to the current month in the form; select an earlier month explicitly to backfill.

While the backend is running, it checks due debits every minute and catches up on
startup after downtime. Days 29–31 use the last day when a month is shorter.
Only active, due months from the selected recording start are recorded, using that
month's amount override or effective default and category. Each debit is a spending
transaction, so actual totals, category trends, and alerts include it; forecast
expenses continue to include the recurring bill once. This records an assumed
debit from the schedule; it does not connect to a bank or initiate a payment.

Generated transactions show **Scheduled ACH · confirm with bank** in Spending.
Edit their actual dates or amounts there when necessary. A persistent occurrence
record prevents duplicate generation, including after restarts, concurrent checks,
or deleting a generated transaction. Changes to schedules do not rewrite recorded
actuals. Disabling ACH stops generation and keeps history; reenabling catches up
from the configured recording start. Deleting the schedule keeps its transactions.
Manual entries and later bank-statement imports are not automatically reconciled
with these generated debits: choose a start month without already recorded debits
and review overlapping bank data to avoid counting it twice. No cron job is needed.

## Statement imports

1. Select **Import statements** in the header on any screen, or open **Statement imports** in the main menu to upload files and return to unfinished reviews. Select **Import statements** and choose one or more CSV/text-PDF files. Set default card/period values, then check or edit them separately for every queued file (especially when uploading multiple months). Each file keeps the existing 15 MB, 100 PDF pages, and 5,000-row limits. Files upload sequentially; one failure does not cancel the others. Retry only retries pending/failed entries; already-uploaded files are identified separately. **Stop after current file** pauses the queue. Successful files each have a **Review** action and still require review and explicit saving before transactions are added. The batch queue tracks review progress: committed statements show **Saved → View**, unfinished reviews show **Continue**, and undone/deleted statements update accordingly. You can review a file and return to the remaining upload queue.
2. For an unfinished CSV import, the **CSV columns & parsing** form is always visible above the review rows. Map date, description, and one signed amount column. **Apply & remember mapping** saves the column choices, date format, and sign convention for that card. Later matching CSV uploads apply that profile automatically; files already in a batch queue pick it up when opened. Existing mapped reviews keep their own settings and edits. If required headers are missing, the file stays ready for manual mapping with a visible warning. Applying a corrected mapping replaces the card default; renaming the card or deleting a statement does not erase it. Select the date format. Descriptions containing `PAYMENT` (case-insensitive) default to payment, with no spending category, before remembered category rules. Other rows default to purchases regardless of amount sign; optionally select a sign convention to distinguish charges and credits automatically. A preview shows the first five source rows. UTF-8 CSV exports with comma, semicolon, or tab delimiters are supported. Combine separate debit/credit columns into a single signed column before importing.
3. CSV mapping applies remembered payees automatically; label new payees manually or use **Apply remembered payees**. CSV categorization never calls a model. For PDFs, use **Extract PDF transactions / retry** with a selected local model, then categorize rows with memory or manual review. You can also add review rows manually. Scans require a text PDF or CSV instead; OCR is not included.
4. Correct rows against your statement. Dates and amounts from CSV are parsed deterministically and never rewritten by the model. PDFs are model-proposed and require careful review. Missing/invalid values are flagged. Source details preserve original CSV values or PDF page text.
5. Select the rows to save. **Validate & save review** checks edits without creating transactions. **Save selected transactions** validates again and commits atomically. Zero-amount rows start unchecked and do not block saving the other rows. You can correct and select them if needed; saved transactions still require a positive amount. Invalid unchecked rows do not block saving valid selected rows.

Exact repeat files for the same card are blocked while the import exists, including after undo. Open the original import to retry, or use **Delete import** to remove its review data and fingerprint so you can upload the file again. Failed, prepared, review, interrupted, and undone imports can be deleted; wait for processing to finish, and undo committed imports before deleting them. Across imports for the same card, rows are always skipped when every original named CSV field equals a saved CSV row. Column order does not matter, but exact values (including whitespace, case, formatting, and unmapped columns) do. Editing a saved transaction or a review category does not change its original CSV identity. Within a single file, repeated rows remain selectable with a possible-duplicate warning, so two identical bridge tolls can both be saved. Nonidentical rows, different card accounts, PDF rows, and manual entries are not automatically skipped under this CSV rule. The save summary reports added and skipped counts. Overlaps are rechecked while saving, including concurrent imports. Existing saved duplicates are not deleted or merged. Undo removes every transaction linked to the import, including edits made after import. Add a manually entered transaction if you need to restore a specific item after undo.

Uploaded original bytes are discarded after extraction. Extracted input is retained locally for review/retry until commit; normalized rows and source provenance remain in PostgreSQL. Import records and fingerprints remain after undo until the import is deleted. Model or extraction failures do not create actual transactions. CSV proposals remain available for manual correction; failed and interrupted jobs can be retried.

### Local models

Start Ollama separately and install a model yourself, for example an appropriate Gemma or Granite model for your machine. Abacus only lists installed local models and does not download any. Select a model in Settings and use **Refresh models** after installing one.

`OLLAMA_URL` defaults to `http://127.0.0.1:11434`. Only HTTP loopback addresses without paths are allowed. HTTP proxy environment variables are ignored and redirects are disabled. Optional PDF extraction uses Ollama structured JSON output followed by Pydantic and database validation. It extracts transaction rows and types, not categories. CSV processing makes no Ollama requests. No tools or database access are provided to the model and there is no cloud fallback. Keep Ollama configured for local models only (including disabling cloud features in Ollama if you use those elsewhere).

Changing the model affects future advisor replies and PDF extraction/retries, not saved transactions. Model suggestions can be wrong; review is mandatory. Date formats without a year infer the closest year to the statement period, including December/January boundaries.

## Learning recurring payees

Saved transaction labels remember specific payee variants, then share categories
across normalized variants of the same transaction type. Explicit `#store` IDs,
leading years/dates, punctuation, and spacing are ignored for normalized matching:
`panera bread #600874 k` matches `panera bread #600878 k`, and
`2025 holiday hustle` matches `2026 holiday hustle`. Unmarked numbers in names
such as Route 66 or Studio 54 remain significant. Specific remembered variants
take priority; new variants use a group only when its categories agree. Conflicts
stay for manual review. Existing rules work immediately without rewriting history. CSV mapping applies these rules immediately; use **Apply
remembered payees** to fill empty categories in an existing review. Settings lets
you edit or forget rules. Rules preserve transaction types and never overwrite
existing review categories. Only saved transactions teach labels; unsaved model
proposals do not. Rules persist when imports are undone/deleted, until forgotten.

Merchant pattern matching is configured in `backend/abacus/payee_matching.json`.
The default Python regex strips changing order codes from `Amazon.com*…` and
`AMAZON MKTPL*…`, keeping these two merchant groups separate. Add entries to
`patterns` with `pattern` and `replacement` strings (JSON needs doubled backslashes).
Patterns run case-insensitively before the normal store/date cleanup. This is trusted
local configuration; use simple, bounded patterns. Edits take effect on the next
classification pass, including **Apply remembered payees** in an existing review.
No saved descriptions, categories, or CSV duplicate identities are rewritten.

When exact and normalized memory have no match, Python similarity matching uses
`fuzzy_threshold` (default `0.94`) and a minimum score gap between competing categories
of `fuzzy_margin` (default `0.05`). Set the threshold to `1` to disable similarity.
It only compares names of at least 12 characters with the same first word, numeric
components, and transaction type. Conflicting or close categories stay for review;
similarity suggestions show **Similar payee · check category** in the review table.
Explicit labels and already populated review categories always take priority.
Invalid configuration disables optional matching and logs a warning; basic memory
continues to work. A saved label is still needed before any matching can categorize.

CSV imports use remembered payees and manual labeling only, regardless of whether a
model is configured. PDF extraction still requires the model. See
[training/README.md](training/README.md) for the baseline's matching limits, a local
training-data exporter, and the future classifier stub. No trained statistical
model is currently installed or used.

## Optional Budget advisor

Advisor replies are read from Ollama's local streaming transport, allowing slow
generation without waiting for a single buffered response. The browser receives
the completed answer and shows elapsed time while it waits. The default time limit
is **300 seconds**, including local generation; set `ADVISOR_TIMEOUT_SECONDS` in
`.env` to a value from 30 to 1800 seconds for your hardware. Ollama connection setup
still has a five-second timeout. The generation limit is checked as chunks arrive;
a stalled read can wait up to the configured read timeout. Cold starts and large
prompts can take longer than a short test question. Unknown funding assumptions
omit redundant monthly funding rows from the model prompt, while the UI retains
the full snapshot. Failed or incomplete streams never become partial advice or
change saved budget data. The question is restored for retry; choose a faster
installed model or raise the time limit if needed. Restart the backend after code
changes and refresh the frontend. If using another reverse proxy, its request
timeout must also allow the longer advisor request.

1. Start Ollama locally. In Settings, select **Refresh models**, choose an installed
   model, check **Enable Budget advisor in the main menu**, and save.
2. Open **Budget advisor**. Ask a general budget question, select a saved draft or
   included purchase, or enter a new amount and target month as a what-if scenario.
3. The backend reads a fresh snapshot for every question: the selected month plus
   11 future forecast months (23 with web research enabled); three months of category spending and completeness;
   up to 20 upcoming drafts; and the selected purchase scenario. Expand **Budget
   context** to inspect the snapshot used for the last response.

The advisor is disabled by default and is read-only. It cannot change the budget
or make purchases. Python calculates scenario balances before the model sees them;
included purchases are never deducted twice. Each month remains independent, and
actual spending stays separate from forecast expenses. Savings and bank balances
are unknown, so forecast room alone does not establish cash affordability.

Only aggregates, your explicit planning assumptions, and purchase/category names are provided to the local model, never raw statements,
card identifiers, individual transaction descriptions, or credentials. Chat requests use [Ollama’s no-thinking option](https://ollama.com/blog/thinking) and a bounded reply length to reduce empty replies and latency on compatible local models. Model requests go
to the selected loopback Ollama instance with no transaction or booking tools and
no cloud-model fallback. Optional web research uses Brave Search separately as described below. The model can still make mistakes; compare its explanation with
the displayed numbers. General budgeting is the intended scope.

Chat history stays in the current tab's memory, is retained while changing menu
views, and clears on reload, a new conversation, a changed context month/model,
or disabling the advisor. Each question sends at most the most recent 12 bounded
messages plus the fresh snapshot. Cancelling stops waiting in the UI; the local
model may finish its current computation. Timeouts show a retryable error without
altering saved financial records. Disabling the advisor does not disable optional
PDF extraction or change its configured model.

### Internet-assisted travel planning

Set `BRAVE_SEARCH_API_KEY` in `.env` using your own [Brave Search API key](https://api-dashboard.search.brave.com/documentation/guides/authentication). Refresh the research connection in Budget advisor; **Use current web research** becomes available and is initially enabled when a key is configured. Uncheck it for an entirely local conversation. No key is bundled, created, or exposed to the browser. Search usage is subject to your Brave plan and quota; each researched turn makes at most three searches.

Ask naturally, for example:

- “Plan a Friday–Sunday trip to western New York in July 2027, with Friday dinner and three meals Saturday. Suggest lodging and dining, a budget, and when to plan and pay.”
- “What kind of weekend in Puerto Vallarta next fall would fit my budget?”

The backend builds up to three public travel queries directly from the latest user-authored trip request, without letting the model invent dates, departure cities, traveler counts, or preferences. No database budget snapshot, savings input, monthly-buffer input, or assistant financial reply is used for query construction. Sentences with financial details and common identity terms are omitted, and outgoing queries are checked again. If this leaves no useful travel topic, the advisor asks for one. An optional **Public research topic** lets you specify travel-only search terms instead of using chat discussion. Search terms go to Brave, while budget reasoning stays on your local model. The terms actually sent are displayed with the answer.

The backend uses [Brave Web Search](https://api-dashboard.search.brave.com/api-reference/web/search/get), retrieving up to four results per query with excerpts. It deduplicates sources, filters unsafe/private links, and passes excerpts to the local model as untrusted evidence. Answers show clickable sources, retrieval dates, missing details, and partial/failed research status. No arbitrary page fetching, account login, reservations, or purchases occur. Excerpts are not exact-date quotes: availability, booking deadlines, menus, taxes, fees, currency conversions, and cancellation terms require confirmation with the provider. Research that fails or yields no sources is visibly labeled; it does not silently become current advice.

Relative dates use `APP_TIMEZONE` (default `America/Detroit`) and the current date. Query construction resolves “next season” to the next calendar year and asks the user to confirm that interpretation before treating dates as settled. The advisor must state the year for “next fall” and ask for ambiguous dates, exact weekends, precise areas within a region, travelers, departure airport, transport, and preferences. It can provide provisional assumptions and estimates while asking for missing information; it must not invent an exact itinerary or rate.

### Trip funding assumptions

Optional **Funds already set aside** and **Monthly breathing room to preserve** inputs support a separate, hypothetical 24-month funding projection. Contributions are the nonnegative forecast room after the stated monthly buffer, starting no earlier than the current month. Actual transaction spending is not added to forecast expenses. A selected included purchase is counted once. Monthly contributions are not reserved in the budget or guaranteed cash; income timing, other draft purchases, competing trips, and monthly buffer shortfalls can change comfort.

Without stated savings and a monthly buffer, the advisor asks before claiming comfortable payment timing. Missing forecast income makes cumulative funding unknown. The snapshot shows the projection and any buffer shortfalls. For a Python-calculated funding month, select a saved purchase or enter the proposed trip's total as an estimate scenario. A cost range generated by the model remains provisional until you choose a scenario total; the model cannot turn an unsourced estimate into a guaranteed cash-ready date. The main budget still treats each month independently—this projection does not enable carry-forward.

## Expense breakdown and date-range drill-down

Actual spending defaults to the month before the selected budget month. Check
**Current month** on the Overview card or Spending view to use the selected budget
month instead. The checkbox is shared across actual totals, transactions, expense
breakdowns. Historical trends have their own ending-month control. Forecasts continue to use the
selected budget month; actual deficit alerts compare with income from the actual
period itself. Every actual view labels its period. A reload restores the
previous-month default, and explicit trend-month drill-down selects that exact month.

Open **Spending → Current** to see that actual month's complete expense breakdown
and transactions, or choose **Explore breakdown** from the Overview actual-spending
card. Use the **− / +** month controls to go back or forward a complete month, or
select a month directly. The transaction list follows the same actual month.
**From** and **Through** still support an inclusive custom date range.

Choose **Historical** for the 12-month chart at the top of its view. It has an
independent ending-month selector and previous/next controls; **Latest 12 months**
resets it to the window ending last month. Select a month in the trend chart or
its accessible data table to open that month's breakdown in Current.

- **Actual spending** shows purchases and fees, refunds, net expense totals, a
  category bar chart, and the individual transactions (including card accounts).
  Refunds appear as negative spending; payments and transfers are excluded.
- Select a category bar, category button, or category table row to drill into its
  entries. **All categories** returns to the full breakdown. Details initially
  show 50 rows; **Show more** reveals all remaining rows in batches.
- **Planned expenses** uses full calendar-month ranges and shows recurring bills
  plus included purchase estimates. Annual expenses follow their distribution setting;
  amount changes and monthly overrides are respected. Drafts and income are
  excluded, and actual transactions are never added to the forecast.
- Category tables retain both gross charges and refunds, even for a category
  whose net is zero or negative. No pie chart hides negative/credit categories.
- Actual month completeness is shown alongside the range. Missing records and
  partial months are not proof of zero spending. Mark actuals complete using the
  existing Transactions control once all records for that month are entered.

## Trends and completeness

In **Spending → Historical**, trends default to a rolling 12 months ending in the previous month. Choose another ending month independently of Current and the budget forecast. Select one or more categories for individual lines and toggle forecast overlays. An expandable table provides the same numbers. Historical category filters apply to trends; the Current transaction list keeps its own description search.

Months with no records are **missing**, rather than zero, unless explicitly marked complete. Months with records remain **partial** until marked complete. Current/future months always display as partial, even if marked complete. Completeness is a manual budget-wide marker; the app cannot infer whether all card statements have been imported. Adjust it after adding, deleting, or undoing records as needed.

## Tests

Tests require a separate PostgreSQL database whose name begins with `abacus_test`. They delete app data in that database; never point them at your budget database.

```sh
createdb --host=127.0.0.1 --port=5432 --username=YOUR_DB_USER --password abacus_test
# Use your authenticated SQLAlchemy URL (URL-escape credentials in full URLs):
DATABASE_URL='postgresql+psycopg://USER:PASS@127.0.0.1:5432/abacus_test' uv run alembic upgrade head
TEST_DATABASE_URL='postgresql+psycopg://USER:PASS@127.0.0.1:5432/abacus_test' uv run pytest -q
cd frontend
npm run check
npm run build
```

For another test connection, set `TEST_DATABASE_URL` (and use that same URL for the test migration). Tests cover recurrence boundaries, amount history, previews, deficits, refunds, payment exclusion, completeness, category trends, statement mapping, PDF text extraction, invalid/unavailable models, duplicates, atomic commit, undo, interrupted imports, and loopback restrictions. Tests use synthetic data and mocked models. A separate optional real-model smoke check is available:

```sh
uv run python scripts/check_local_model.py granite4.2:3b
```

The smoke check sends only a synthetic budget scenario to the named installed local model and does not touch the budget database. It prints the reply for inspection. Automatic tests mock chat and extraction; they verify advisor opt-in, purchase calculations, current context, error handling, read-only behavior, input limits, the absence of CSV model calls, source handling, missing-key/partial research states, search privacy boundaries, and hypothetical funding calculations. Web API calls are mocked; live Brave search requires your configured key.

## Backup and restore

Back up PostgreSQL regularly. These example commands use the database name; pass `-h`, `-U`, or a standard PostgreSQL connection URL if needed. SQLAlchemy's `postgresql+psycopg://` URL is not a `pg_dump` URL. Use your configured host, port, and database login; `--password` prompts instead of putting your password in shell history.

```sh
pg_dump --host=127.0.0.1 --port=5432 --username=YOUR_DB_USER --password -Fc -f abacus-backup.dump abacus
# Restore into a new database to inspect it before switching DATABASE_URL:
createdb --host=127.0.0.1 --port=5432 --username=YOUR_DB_USER --password abacus_restored
pg_restore --host=127.0.0.1 --port=5432 --username=YOUR_DB_USER --password --no-owner -d abacus_restored abacus-backup.dump
```

Backups contain private financial descriptions and source excerpts. Keep them in a private location. Changing the browser or clearing its storage does not delete the PostgreSQL budget.
