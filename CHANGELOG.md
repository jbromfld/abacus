# Changelog

Notable changes to Abacus. Release entries describe changes between tagged versions.

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
