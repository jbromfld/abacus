# Performance and maintenance work

## Implemented

Migration 0018 adds an account/CSV-fingerprint index and backfills existing
transaction identities in batches of 500. It does not delete financial data.
Original CSV field values remain the authority: a hash match also requires exact
canonical source equality. ORM transaction inserts and updates maintain the hash.

Import validation now fetches duplicate candidates in batches of 500 rather than
querying once per PDF/manual review row. PostgreSQL supplies case normalization;
within-file duplicate detection retains its existing Python casefold behavior.
Account locking and duplicate revalidation at commit remain in place.

The 5,000-row repeated-description regression previously required roughly 5,001
validation reads; it now asserts no more than four. This is a query-count result,
not a production latency benchmark. Distinct candidate keys require additional
500-item batches.

Import review renders 100 rows at a time while retaining and submitting every
row and its original source index. Polling waits for each request to finish before
scheduling another and cancels requests on close. Forms retain conditional edits;
forms and review dialogs confirm before discarding unsaved changes.

Unreachable BudgetImpactPlanner and ReserveMonitor screens, their exclusive
styles, and the obsolete ReserveMonitor tests/mock have been removed. Current
Planning and savings behavior remains covered by backend regressions. Funding
calculations reuse per-schedule changes, and savings-aware forecast windows skip
an unused intermediate projection.

## Completed follow-up

Migration 0019 removes the obsolete planning tables and reserve settings. Its
downgrade restores empty schemas only. Current Planning, recurring bills, imports,
transactions, and saved savings are covered by populated migration tests. Retired
routes return 404 and retired advisor/settings/projection inputs are rejected.
Historical migration files are unchanged.

Transaction and import history now use bounded cursor pages. Both default to 100
rows and cap pages at 200; date/creation-time ties use IDs for stable ordering.
The UI fetches rows only for the relevant screen and keeps review edits across
pages. Transaction/import route handlers and common CRUD helpers are extracted
from the application composition module.

Shared parameter-keyed reads deduplicate requests, retain independent cancellation
ownership, and cache for up to 30 seconds. Mutations invalidate affected resource
versions and dependent financial summaries. Metadata resources refresh separately;
a failed account/category read does not discard successful settings or forecasts.
Manual refresh invalidates financial reads.

Core response schemas drive generated TypeScript contracts. CI detects generated
contract drift. Effect-dependency linting is an error and passes without warnings;
the old App input warnings were resolved with correct API fixtures.

## Measurements and verification

A synthetic 5,000-row unique-description import comparison on local disposable
PostgreSQL measured 5,000 queries / 3,135.78 ms for the former per-row matching
versus 21 queries / 225.92 ms for batched validation. The new measurement includes
row validation; this is one local run, not a production latency guarantee.
Reproduce with `TEST_DATABASE_URL=... uv run python scripts/benchmark_import_validation.py`.
The benchmark requires an abacus_test database and rolls back synthetic records.

Tests cover equal-date/creation-time page boundaries, literal search, cursor and
limit validation, shared-request cancellation, targeted invalidation, review edits,
removed API validation, and data preservation through migration. Verification
builds are placed under `/tmp`. Browser visual/keyboard/narrow-layout QA could
not run because the browser-control host was unavailable.

Applying migrations and restarting the installed service are separate operations.

Final verification: 490 backend tests, 42 frontend tests, Alembic schema check,
Ruff lint/format, ESLint, Prettier, TypeScript, generated-contract drift check,
and the production build passed. Obsolete feature tests were removed; current
advisor privacy and model-error tests were adapted to hypothetical scenarios.
The backend emits an existing Starlette TestClient deprecation warning.
