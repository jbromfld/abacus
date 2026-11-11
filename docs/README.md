# Abacus documentation

Abacus runs locally with React/TypeScript, Python/FastAPI, and PostgreSQL. CSV
imports and manual budgeting work without a model. Ollama adds optional PDF row
extraction and Budget advisor; Brave adds optional public web research.

| Start here | What it covers |
| --- | --- |
| [Quick start](../README.md#quick-start) | Install and launch Abacus |
| [User guide](user-guide.md) | Every screen, daily workflows, calculations, alerts, and defaults |
| [Operations](operations.md) | Configuration, upgrades, backups, testing, and troubleshooting |
| [API reference](api.md) | All `/api` endpoints, conventions, examples, and import lifecycle |
| [Classification and training](../training/README.md) | Matching precedence, exports, and the future classifier stub |
| [Detailed feature notes](user-guide.md) | Implementation details and edge cases |

## Find a feature

| Feature | Documentation |
| --- | --- |
| Forecasts, actuals, currency, refunds, and payments | [Budget concepts](user-guide.md#budget-concepts) |
| Monthly dashboard and annual forecast | [Overview](user-guide.md#overview) |
| Upcoming/overdue bills, paid dates, and payment history | [Due dates and payment status](user-guide.md#due-dates-and-payment-status) |
| Monthly/annual income and expenses, amount history and overrides | [Recurring accounts](user-guide.md#recurring-accounts) |
| Scheduled ACH actual spending | [ACH recording](user-guide.md#ach-recording) |
| Savings slider and opening snapshot | [Savings](user-guide.md#savings) |
| Year-specific extra income, sliders, and optional monthly allocation | [Annual expected income](user-guide.md#annual-expected-income) |
| Conditional cash projections and annual payments | [Planning funding projection](user-guide.md#planning) |
| Dated goals, amount sliders and permanent deletion | [Planning](user-guide.md#planning) |
| Manual transactions and custom expense ranges | [Spending](user-guide.md#spending) |
| Historical charts, means, completeness, and informational guides | [Historical spending and category guides](user-guide.md#historical-spending-and-category-guides) |
| Single/batch imports, card mappings, review, retry, undo, and deletion | [Statement imports](user-guide.md#statement-imports) |
| Exact files, overlapping CSV rows, and repeated tolls | [Duplicate handling](user-guide.md#duplicate-handling) |
| Remembered payees, merchant patterns, and similarity thresholds | [Payee classification](user-guide.md#payee-classification) |
| Savings goals, shared funding, annual bill links, sliders and deletion | [Planning](user-guide.md#planning) |
| Unified Planning implementation | [Design and migration](reserve-redesign.md) |
| Optional local chat, deficit reconciliation, and travel research | [Budget advisor](user-guide.md#budget-advisor) |
| Approved cross-conversation intentions, preferences, and decisions | [Optional advisor memory](advisor-memory.md) |
| Currency, accounts, categories, optional models, and alerts | [Settings](user-guide.md#settings) |
| Alert conditions and controls | [Alerts](user-guide.md#alerts) |
| Responsive navigation, keyboard access, and chart tables | [Navigation and accessibility](user-guide.md#navigation-and-accessibility) |
| Local-only operation and retained data | [Privacy and data](operations.md#privacy-and-data) |
| Database credentials, Ollama, Brave, and timezone | [Configuration](operations.md#configuration) |
| Start after reboot/login; start/stop/restart and logs | [Automatic macOS startup](operations.md#automatic-startup-on-macos) |
| Recovery, missing data, timeouts, and matching problems | [Troubleshooting](operations.md#troubleshooting) |

See [pre-merge review fixes and verification](review-fixes.md) for the current hardening work and migration 0012.

## Keeping documentation current

Update the user guide when a workflow or visible default changes. Update the API
reference with endpoint or request-field changes; the running app's `/docs` and
`/openapi.json` describe exact schemas. Update `.env.example` and Operations when
configuration changes. Document whether each new feature changes forecasts,
actual transactions, payment status, or informational references—these are
separate concepts in Abacus.
