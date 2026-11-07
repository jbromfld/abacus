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
| [Detailed feature notes](../README.md#planning-rules) | Implementation details and edge cases |

## Find a feature

| Feature | Documentation |
| --- | --- |
| Forecasts, actuals, currency, refunds, and payments | [Budget concepts](user-guide.md#budget-concepts) |
| Monthly dashboard and annual forecast | [Overview](user-guide.md#overview) |
| Upcoming/overdue bills, paid dates, and payment history | [Due dates and payment status](user-guide.md#due-dates-and-payment-status) |
| Monthly/annual income and expenses, amount history and overrides | [Recurring accounts](user-guide.md#recurring-accounts) |
| Scheduled ACH actual spending | [ACH recording](user-guide.md#ach-recording) |
| Savings slider and opening snapshot | [Savings](user-guide.md#savings) |
| As-is cash projections, annual payments, and payment scenarios | [Purchase planner](user-guide.md#purchase-planner) |
| One-time drafts and inclusion | [One-time purchases](user-guide.md#one-time-purchases) |
| Manual transactions and custom expense ranges | [Spending](user-guide.md#spending) |
| Historical charts, means, completeness, and informational guides | [Historical spending and category guides](user-guide.md#historical-spending-and-category-guides) |
| Single/batch imports, card mappings, review, retry, undo, and deletion | [Statement imports](user-guide.md#statement-imports) |
| Exact files, overlapping CSV rows, and repeated tolls | [Duplicate handling](user-guide.md#duplicate-handling) |
| Remembered payees, merchant patterns, and similarity thresholds | [Payee classification](user-guide.md#payee-classification) |
| Manual reserve checks and fixed annual funding targets | [Annual bill reserve checks](user-guide.md#annual-bill-reserve-checks) |
| Optional local chat, deficit reconciliation, and travel research | [Budget advisor](user-guide.md#budget-advisor) |
| Currency, accounts, categories, optional models, and alerts | [Settings](user-guide.md#settings) |
| Alert conditions and controls | [Alerts](user-guide.md#alerts) |
| Responsive navigation, keyboard access, and chart tables | [Navigation and accessibility](user-guide.md#navigation-and-accessibility) |
| Local-only operation and retained data | [Privacy and data](operations.md#privacy-and-data) |
| Database credentials, Ollama, Brave, and timezone | [Configuration](operations.md#configuration) |
| Recovery, missing data, timeouts, and matching problems | [Troubleshooting](operations.md#troubleshooting) |

## Keeping documentation current

Update the user guide when a workflow or visible default changes. Update the API
reference with endpoint or request-field changes; the running app's `/docs` and
`/openapi.json` describe exact schemas. Update `.env.example` and Operations when
configuration changes. Document whether each new feature changes forecasts,
actual transactions, payment status, or informational references—these are
separate concepts in Abacus.
