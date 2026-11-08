# Pre-merge review fixes

[Documentation index](README.md) · [Operations](operations.md#upgrade)

All seven findings from the pre-merge review are addressed:

| Finding | Change and regression coverage |
| --- | --- |
| Private chat leaking into Brave queries | Web defaults off. Only a separate public topic can form queries; preview and explicit approval are required. Chat/history never supply queries. Tests cover debt, formatted identity numbers, absent/tampered confirmation, and approved public topics. |
| Failed PDF retry overwriting review edits | Extraction builds candidates outside the database transaction. Failure preserves saved review rows; replacement requires explicit consent. Generation tokens prevent stale workers from overwriting newer attempts. The DB connection is released during model calls. |
| Old totals under a newly selected month | Workspace reads are cancellable and keyed by month. Mismatched forecasts are hidden immediately and stay hidden after failures. Metadata is reused across month changes. Hook and rendered-App tests cover failure and late-response cases. |
| Repeated full-table trend reads | Request-scoped forecast inputs plus SQL actual aggregates reduce the 12-month trend query from 517 SQL statements to six, independent of category/month loops. Historical alone fetches trends. Savings/advisor calculations reuse forecast inputs; annual summary uses a bulk endpoint. |
| Out-of-range transaction dates | Manual, CSV, and model-review validation use the shared 1900–9998 date bounds, with boundary tests. |
| Inconsistent application calendar | ACH, completeness, dues, reserves, category means, and advisor context share the `APP_TIMEZONE` clock. Tests deliberately cross UTC/local month and year boundaries. |
| Excessive breakdown date ranges | Both actual and forecast breakdowns reject more than 120 calendar months before loading financial data. Supported ranges reuse bulk inputs. |

Smaller improvements are included:

- Ruff/Prettier formatting and lint checks across Python, TSX, and CSS; extracted
  App, FormEditor, ImportReview, YearSummary, HistoricalSpending, and workspace reads.
- Removed obsolete savings/ledger styles and unused monthly-missing response fields.
  Retained the documented future `predict_unknown` hook; local-model transport
  imports now point directly to their owning module.
- Named dialogs with `aria-labelledby`; verified mobile Settings visibility and
  keyboard focus/close behavior using synthetic browser data.
- Lazy advisor, charts, planner, breakdown, and import dialogs. Initial JavaScript
  decreased from 776.54 kB (225.20 kB gzip) to 304.99 kB (91.56 kB gzip).
- Compact transaction list DTOs, a provenance-detail endpoint, shared PDF page
  storage, and indexes for import undo and account/date queries.
- Frontend behavior tests and CI with PostgreSQL migrations/schema checks, backend
  tests, frontend lint/format/tests/type checking/build, and npm audit. CI actions
  are pinned to official release commits; permissions are read-only.
- README is a short entry point; detailed workflows remain in the linked guides.
  Private `.env.*` variants are ignored while `.env.example` remains tracked.
- Updated lint/test dependencies, including a documented patched glob-parser
  override. npm and locked Python dependency audits reported zero known advisories.
  The working-file secret signature scan found no credentials or private dotenv files.

## Verification

- 367 PostgreSQL backend tests, including a data-bearing migration downgrade/upgrade.
- Six frontend behavior tests across five files.
- Alembic schema check, Ruff checks/format, ESLint, Prettier, TypeScript, production
  build, and whitespace checks passed.
- Chrome checks used synthetic API responses: failed-month clearing, deferred chart
  and advisor loading, public-search preview, 390 px mobile layout, visible Settings,
  named dialog keyboard focus/close, and no browser errors or horizontal overflow.
- Hosted GitHub Actions has not run locally; its equivalent commands passed locally.
  Model/search calls in regressions were mocked; no private chat was sent to Brave.

## Applying the change locally

Migration **0012** adds job-generation tokens, transaction indexes, and shared PDF
pages. Existing PDF provenance is compacted without changing monetary records;
its downgrade expands that text before removing the shared page table.

The personal database and running login service were left unchanged during these
checks. The verified production bundle was built under `/private/tmp` to avoid
serving a new UI against the older running backend. Follow the normal
[backup](operations.md#backup-and-restore) and [upgrade](operations.md#upgrade)
procedure before using this version: stop the app, migrate, rebuild, restart, and
refresh the browser. For the installed login service:

```sh
python3 scripts/restart.py
```

## Suggested squash message

Use the hosting provider’s squash merge if desired; existing branch history has
not been rewritten or force-pushed.

```text
Build Abacus local budgeting and planning workspace

Add recurring budgets, statement review and payee memory, actual-spending trends,
payment tracking, purchase planning, savings projections, and optional local advice.

Protect public-search consent and saved PDF reviews, unify application dates,
and batch financial calculations. Add regression tests, pinned CI, formatting,
local startup support, and complete user/operations documentation.
```
