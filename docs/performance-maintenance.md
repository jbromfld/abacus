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

## Remaining implementation

- Remove legacy APIs, schemas, advisor inputs, settings, and storage through a new
  migration, including the authorized deletion of obsolete records.
- Introduce resource-specific invalidation and parameter-keyed shared reads.
- Paginate transaction and import-history APIs and update their consumers.
- Extract feature routers and frontend screen ownership.
- Add explicit response contracts, generated frontend types, and CI drift checks.
- Enable effect-dependency checks and resolve the existing App input warnings.
- Complete populated migration tests, broader synthetic benchmarks, and browser QA.

Verification uses disposable PostgreSQL only. Build artifacts go under `/tmp`;
applying migrations and restarting the installed service are separate operations.
