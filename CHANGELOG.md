# Changelog

Notable changes to Abacus. Release entries describe changes between tagged versions.

## [0.3.0] — 2026-11-11

### Added

- **Argo deployment:** a digest-pinned Linux ARM64 image includes the built
  frontend and a separately locked **Babar 0.3.0** stdio runtime. The publisher
  builds committed archives and records both source revisions in release metadata.
- Dedicated runtime credentials and explicit administrator configuration for
  financial database maintenance; memory setup can use independent administrator
  settings and pre-provisioned databases/logins.
- Explicit private Ollama host-gateway configuration for container deployments.
  Loopback defaults, URL restrictions, disabled redirects/proxies, and
  local-only model discovery remain in place.
- Explicit `HF_HOME` propagation to the memory child for read-only offline model
  caches without forwarding application or administrator credentials.

### Changed

- Managed operation uses Argo with one API worker, serialized replacement,
  database-backed readiness, and a managed localhost forward on port **8017**.
  Database placement remains independent of application images.
- Memory lists exclude superseded sources before pagination and refresh after
  consolidation. The combined note retains original sources and revisions for
  evidence and Undo; consolidation does not delete those historical records.
- Completed and cancelled dreaming runs move into collapsed **Past runs**, keeping
  pending reviews in the main view and Undo accessible from history.
- Consolidation approval uses full-width fields, a taller text editor, and
  consistent spacing. Annual expense funding and Planning starts collapsed,
  including when a funding gap exists.
- Python distribution, frontend package/lockfile, and OpenAPI versions are
  aligned at **0.3.0**.

### Removed

- Native macOS service controller, runner, updater, and service-specific tests.
  The environment controller no longer invokes native service scripts or exposes
  native activation/rollback commands. Historical native support remains in the
  unchanged **`v0.2.0`** tag.

### Upgrade notes

- Promote the application digest through GitOps and perform required database
  maintenance explicitly; image startup does not run migrations.
- The deployed financial schema remains **0020**, and bundled Babar uses memory
  schema **3**. A native rollback from the archived tag requires stopping Argo
  writers and reviewing both schema versions before starting the older release.

## [0.2.0] — 2026-11-11

Compared with [v0.1.0](https://github.com/jbromfld/abacus/compare/v0.1.0...v0.2.0).

### Added

- **Unified Planning:** tax, vacation, and purchase goals with exact target dates,
  editable categories, amount sliders, and links to annual bills. Shared savings
  are earmarked by deadline after protecting the savings floor. Funding gaps and
  a running cash projection appear in Planning, Overview, and The bigger picture.
- **Annual expected income:** year-specific estimates with optional inclusion in
  forecasts and exact allocation across twelve months. Estimates supplement
  recurring income without creating transactions or changing recorded savings.
- **Remembered payee groups:** review similar payees with a local model, inspect
  proposed aliases, and explicitly approve selected groups. Rename, edit, forget,
  or ungroup aliases while preserving individual categories by default. Background
  reviews support progress, cancellation, partial results, and stale-data checks;
  saved transactions are not recategorized.
- **Optional memory dreaming:** enable idle consolidation, run a pass on demand,
  review ambiguous proposals, inspect retained sources, undo unchanged merges,
  and explicitly forget an entire consolidated family. Babar owns source binding,
  proposal policy, persistence, and atomic commits; Abacus supplies scheduling,
  model calls, and review UI. Memory and dreaming remain independently optional.
- **Optional LangSmith tracing:** model/workflow metadata, timing, token usage,
  truncation, error types, and dreaming controller outcomes. Tracing defaults off;
  exporting prompts and replies requires a separate content-capture opt-in.

### Changed

- Transactions and import history now use stable cursor pagination, defaulting to
  100 records per page with a maximum of 200. Transaction month, category, and
  literal-text filters remain available.
- Import review displays 100 rows at a time while retaining edits, selections,
  original source indices, validation, and totals across the complete review.
- Screens load transaction rows and import history when needed. Shared reads
  deduplicate requests, support cancellation, and invalidate affected resources
  and dependent summaries after mutations. Metadata failures are handled separately.
- Duplicate validation uses batched queries and indexed account-scoped CSV source
  fingerprints, confirming exact original-field equality before skipping a row.
  Account locking and commit-time duplicate revalidation remain in place.
- Funding calculations reuse amount-change indexes and avoid an unused forecast
  projection. A synthetic 5,000-row unique-description import benchmark reduced
  validation from 5,000 queries / 3,136 ms to 21 queries / 226 ms in one local run;
  these measurements are not a production latency guarantee.
- Advisor discussions use current Planning goals and shared funding projections.
  Model-generated Planning suggestions require review before saving. Public
  research also supports product specifications and buying information.
- Backend feature routers and explicit response schemas replace portions of the
  application shell; generated TypeScript contracts now have a CI drift check.

### Fixed

- Conditional form fields retain edits through hide/show cycles while hidden
  fields remain excluded from submission. Editable forms and import reviews warn
  before discarding unsaved changes and retain drafts after failed saves.
- Import polling waits for each request to finish, cancels abandoned reads, and
  ignores responses from closed or superseded reviews.
- Card-freshness alerts recover after interrupted requests. Advisor network errors
  provide a clearer explanation when the local server is unavailable.
- Statement-import pagination spacing, controlled-input warnings, and React effect
  dependencies were corrected.

### Removed and breaking changes

- Retired purchase-planner, bill-estimate, and reserve-monitor features, including
  their routes, request fields, database storage, settings, and unused components.
  Removed routes return 404; removed request fields are rejected.
- Transaction and import-history list responses changed from arrays to
  `{items, next_cursor}`. API clients must consume the page envelope.
- Savings-aware forecast fields now represent a running cash balance rather than
  independently adding the same savings balance to each month.
- Merchant-specific `payee_matching.json` patterns and automatic fuzzy category
  guesses were retired. Manage approved aliases in Settings → Remembered payees;
  deterministic import classification continues without model calls.

### Upgrading

- **Back up before upgrading.** Migrations 0015–0020 add annual income, Planning,
  payee groups/reviews, CSV fingerprints, and dreaming settings/jobs, and remove
  legacy planning storage. Migration 0016 clears obsolete purchase, bill-estimate,
  and combined reserve records; 0019 drops the obsolete tables and reserve
  observations/preferences. Downgrade cannot recover deleted legacy records.
- Current Planning goals, savings balances, recurring bills, payment history,
  accounts/categories, imports, and transactions are preserved.
- Run `python3 scripts/update.py` for an installed macOS service, or follow the
  [manual upgrade instructions](docs/operations.md#upgrade). Update dependencies,
  apply migrations, refresh advisor grants, rebuild the frontend, and restart.
- Dreaming additionally requires upgrading Babar to schema 3 with the
  `dreaming-controller-v1` capability. Older Babar installations can continue
  ordinary memory operation. Existing pending legacy proposals are cancelled and
  must be freshly prepared; original memories remain intact.
- LangSmith requires explicit `LANGSMITH_TRACING=true` and an API key. Leave
  `LANGSMITH_CAPTURE_CONTENT=false` to keep model content local; enabling it exports
  potentially private budget, statement, chat, and memory content.

[0.2.0]: https://github.com/jbromfld/abacus/compare/v0.1.0...v0.2.0

