# API reference

[Documentation index](README.md) · [User guide](user-guide.md) · [Operations](operations.md)

Base URL: `http://127.0.0.1:8017/api`. The app serves interactive `/docs` and
`/openapi.json` on the same origin. Those generated schemas provide exact field
requirements, enum values, and validation responses for the running version.

## Conventions

- JSON requests/responses unless an upload is explicitly multipart. IDs are opaque strings.
- Money is an integer in currency minor units: USD 200.00 is `20000`, JPY 200 is `200`.
  Transaction/recurring/purchase amounts must be positive; refunds use a positive
  amount with kind `refund`. Savings, floors, observations, and guides allow zero.
- Months are `YYYY-MM`; dates are `YYYY-MM-DD`. Valid month and transaction-date years are 1900–9998.
  End months/date ranges are inclusive. Annual paid periods use `YYYY` instead.
- Repeat list parameters, e.g. `?end=2026-12&category_ids=ID1&category_ids=ID2`.
- Most creates return 201. Deletes return `{"ok":true}`. Most list endpoints return arrays; transaction/import history returns page envelopes;
  forecast, projection, averages, and breakdown endpoints return objects.
- This is an unauthenticated loopback application, not an Internet-facing API.
  Local host/origin restrictions apply. No API initiates payments or bank connections.

Most `PUT` resource bodies follow their full input schema rather than arbitrary
patch semantics. Send complete recurring/transaction records when editing.
`PUT /settings` has defaults for currency/model/advisor, so include their current
values when changing preferences. Use dedicated PATCH endpoints where provided.

## Health, settings, and local services

| Method | Path | Purpose / inputs |
| --- | --- | --- |
| GET | `/api/health` | Check database query; returns `status` |
| GET | `/api/settings` | Budget currency, selected model/advisor opt-in, savings fields |
| PUT | `/api/settings` | `currency`, `model`, `advisor_enabled` |
| GET | `/api/models` | Installed local model names and connection error text |
| GET | `/api/advisor/research-status` | Brave availability/status, without exposing the key |
| POST | `/api/advisor/research-preview` | `{topic}` prepares public queries and a confirmation value; no outbound request |
| POST | `/api/advisor/chat` | Read-only question with fresh budget context; described below |

Changing currency is rejected once financial/planning data locks it. Enabling the
advisor requires a selected installed model. Disabling the advisor does not require
Ollama to be reachable.

## Categories, accounts, and category guides

| Method | Path | Purpose / inputs |
| --- | --- | --- |
| GET | `/api/categories` | Categories including nullable `monthly_guide` |
| POST | `/api/categories` | Create with `name` |
| PUT | `/api/categories/{id}` | Rename with `name` |
| DELETE | `/api/categories/{id}` | Delete when references permit |
| PATCH | `/api/categories/{id}/guide` | Set `monthly_guide` in minor units, or `null` to clear |
| GET | `/api/spending/averages` | Required `end`; optional repeated `category_ids`; means, sample/partial counts, included/excluded months, guide suggestions |
| GET | `/api/accounts` | Named bank/card accounts, saved `csv_mapping`, freshness dates/flags |
| POST | `/api/accounts` | Create with `name`, optional `stale_alert_enabled` |
| PUT | `/api/accounts/{id}` | Edit name/monitoring; omitted fields preserve current values |
| PATCH | `/api/accounts/{id}/monitoring` | Set `stale_alert_enabled` |
| DELETE | `/api/accounts/{id}` | Delete when references permit |

Guides are informational. They do not change forecast or savings calculations.
Accounts are named local records, not connected financial institutions.

## Recurring schedules, ACH, and paid status

| Method | Path | Purpose / inputs |
| --- | --- | --- |
| GET | `/api/recurring` | Schedules with amount `changes` |
| POST | `/api/recurring` | Create schedule plus initial `amount`; may catch up due configured ACH actuals |
| PUT | `/api/recurring/{id}` | Edit schedule fields; amount history remains separately managed |
| DELETE | `/api/recurring/{id}` | Remove schedule and linked confirmations/occurrence identities; actual transactions remain |
| PUT | `/api/recurring/{id}/amount` | Upsert `{month,amount,override}`; `override=false` is an effective default |
| DELETE | `/api/recurring/{id}/amount/{change_id}` | Remove an override/default except the initial default |
| POST | `/api/recurring/record-due` | Idempotently catch up due ACH actuals; writes actual transactions |
| GET | `/api/recurring/dues` | Today/window, upcoming and overdue monthly occurrences, annual summaries, history |
| PUT | `/api/recurring/{id}/payments/{period}` | Idempotent manual paid-status update: `{paid,paid_on}` |

Schedule fields: `name`, `kind` (`payable`/`receivable`), `frequency`
(`monthly`/`annual`), `category_id`, `start_month`, optional `end_month`,
`distribute_annual`, `due_day`, `due_month`, `payment_tracking_start`,
`ach_enabled`, `ach_day`, `ach_start_month`, and `ach_account_id`.

Payables require a category. Annual amounts are full yearly totals. ACH is limited
to monthly payables and requires the account/day/recording start. Contractual dates
remain separate. Periods are `YYYY-MM` for monthly and `YYYY` for annual bills;
occurrence membership/tracking is validated. Paid dates cannot be in the future.
Paid-status updates leave actual transactions unchanged. Automatic ACH occurrences
are derived from their generated actuals rather than manual confirmations.

## Annual expected income

| Method | Path | Purpose / inputs |
| --- | --- | --- |
| GET | `/api/annual-income?year=YYYY` | Year, total, included total, twelve included monthly amounts, and sources |
| POST | `/api/annual-income` | Create `{year,name,amount,included}`; inclusion defaults false |
| PUT | `/api/annual-income/{id}` | Replace the source's year, name, amount, and inclusion |
| DELETE | `/api/annual-income/{id}` | Remove the source and its forecast contribution |

Years range from 1900 through 9998. Amounts are positive integer minor units,
at most 9,000,000,000,000. Each source response includes twelve `monthly_amounts`
showing its possible allocation; summary `monthly_amounts` includes only checked
sources. Division uses integer quotient/remainder, assigning leftover minor units
to January onward. Included estimates affect all twelve months of that calendar
year only. They supplement recurring income without creating transactions or
altering savings observations. These are estimates, not dated cash receipts.
Advisor access is SELECT-only on `annual_income`; rerun advisor setup after
migration 0015 to maintain the explicit allowlist.

## Remembered payee group review

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/payee-review/payees` | Approved groups, individual aliases, total, and latest resumable review |
| POST | `/api/payee-review/reviews` | Start one background local-model preview; return 202; repeated start reuses an active job |
| GET | `/api/payee-review/reviews/{id}` | Status, progress, snapshot members and suggestions |
| DELETE | `/api/payee-review/reviews/{id}` | Cancel/discard an unapplied review; remembered payees remain unchanged |
| POST | `/api/payee-review/reviews/{id}/apply` | Atomically apply explicitly selected groups |
| PUT | `/api/payee-review/groups/{id}` | Rename canonical label with `{name}` |
| DELETE | `/api/payee-review/groups/{id}` | Ungroup while retaining individual alias rules/categories |

Apply body: `{groups:[{suggestion_id,name,member_ids,category_id}]}`. Null
`category_id` preserves each alias's current category; an existing category ID
explicitly updates the selected aliases. At least two distinct displayed members
are required per group. Altered or forgotten selected rows return 409 without
applying any group. An identical applied request returns the prior result; a
different replay returns 409. Historical transactions are never recategorized.

States are queued, running, ready, applied, cancelled, failed, or interrupted.
Preview generation uses the configured local model, eight-name candidate batches,
and a dedicated 2,048-token allowance. Model output supplies exactly one
canonical name or null per provided payee ID. Unknown, missing, and duplicate
keys are rejected; the server derives each group's membership. A failed batch retries in smaller sets,
bounded to two subdivision levels. Complete validated suggestions are checkpointed
after each batch. `ready` can carry a nonempty `error` describing an incomplete
review; show that warning beside the still-reviewable suggestions. A failed call
never turns truncated JSON into proposals. No payee changes occur until apply.
Private jobs are excluded from the advisor's SELECT allowlist; approved groups and
payee rules are readable solely for aggregate naming. The existing `/payee-rules`
edit/forget endpoints continue to manage exact aliases.

## Planning

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/planning` | Goals, live linked bill values, funding gaps, and shared cash projection; optional `month` chooses projection start |
| POST | `/api/planning/annual/{recurring_id}` | Track the next open dated annual occurrence, reusing an existing goal |
| POST | `/api/planning` | Save `{name,amount,target_date,category_id?,recurring_id?,request_id?}` |
| GET | `/api/planning/{id}` | Current goal/funding; deleted IDs return 404 |
| PUT | `/api/planning/{id}` | Replace the goal using the same input |
| DELETE | `/api/planning/{id}` | Permanently delete; repeated deletion succeeds |
| GET/POST | `/api/planning/categories` | List or create `{name}` |
| PUT/DELETE | `/api/planning/categories/{id}` | Rename or delete a label; deleting retains uncategorized goals |
| POST | `/api/planning/draft` | Local-model extraction from `{user_message,assistant_message}` for review; never writes a goal |

Amounts are positive integer minor units. Target dates use YYYY-MM-DD (1900–9998).
The optional UUID `request_id` makes a retried create reuse the original saved goal.
Planning categories are separate from transaction categories. Linked annual
expenses must exist and have at most one plan per year. Savings remains a manual
opening snapshot. New goals affect the Planning funding projection, not actual
transactions. Linked annual cash amounts are replaced once in that projection;
saved recurring bills are not edited. Linked amount and dated target derive from the
annual occurrence on every read and save, rather than trusting copied fields.
Undated annual allowances retain the goal's chosen date. Annual goal responses
include `monthly_allocation`, `contributions`, `projected_contributions`,
`projected_funding`, and `funding_gap`; unknown funding is null. Paid/inactive goals
release earmarks and do not have active funding-gap fields.

`GET /api/forecasts?...&include_savings=true` uses the same running cash engine,
including saved goals. `projected_savings` and legacy `remaining_with_savings`
now carry a running balance, or null before the saved balance month/beyond ten
years. `cash_expenses` pays dated annual bills once instead of monthly allocations.
`funding_gap` sums tracked annual goals due in that month; `annual_funding` gives
those goal details. Monthly budget fields are unchanged.

Advisor chat accepts optional `plan_id`. The server resolves it inside the fresh
read-only snapshot and rejects a response if that plan was edited or deleted
while the model was answering. `plans` and `plan_categories` require the normal
advisor setup SELECT grants after migration 0016.

The following legacy planning endpoints are retained for internal scenario
calculations and older API callers; the application UI uses only Planning.
Migration 0016 clears their obsolete saved plan records.

## Forecasts, actuals, trends, and transactions

| Method | Path | Purpose / inputs |
| --- | --- | --- |
| GET | `/api/forecast` | Required `month`; optional `preview=PURCHASE_ID` for that same month |
| GET | `/api/trends` | Required `end`; optional repeated `category_ids`; rolling 12-month values |
| GET | `/api/expenses/breakdown` | Required `start`, `end`; `basis=actual` (default) or `forecast` |
| PUT | `/api/months/{month}` | Manual completeness marker `{complete:true/false}` |
| GET | `/api/transactions` | Optional `month`, description substring `q`, and single `category_id` |
| POST | `/api/transactions` | Create actual transaction with the fields below; learns reviewed category memory |
| PUT | `/api/transactions/{id}` | Edit actual details using the transaction input schema; learns category memory |
| DELETE | `/api/transactions/{id}` | Delete actual; does not erase learned payee memory |

Transaction input: `date`, `description`, positive `amount`, `kind`, `account_id`,
and `category_id` (required except for payments/transfers). Kinds are `purchase`,
`refund`, `fee`, `payment`, `transfer`. Transactions are ordered newest date first.

Forecast responses separate `income`, `expenses`, `remaining`, `deficit`, `lines`,
`actual`, and `actual_deficit`. Actuals group by transaction date, not statement
period. Missing trend values are `null`, not zero; complete zero months are zero.
Breakdowns include charges/refunds/net, category aggregates, entries, and month
completeness. Forecast breakdowns require full calendar-month boundaries.

## Savings projections

| Method | Path | Purpose / inputs |
| --- | --- | --- |
| GET | `/api/savings` | Opening snapshot `{amount,month,floor}`; unset amount is `null` |
| PUT | `/api/savings` | Save `{amount,month,floor}` |
| POST | `/api/savings/projection` | Read-only as-is or hypothetical 12-/24-month cash projection |

A projection takes `months` (12/24; default 24) plus `savings:{amount,month,floor}`
or, without known savings, `start_month`. Optional scenario inputs are mutually
exclusive:

- `bill:{name,amount,start_month,end_month}` for a proposed monthly payment.
- `recurring_change:{recurring_id,action,start_month,end_month,amount}`; `action` is
  `modify` (amount required) or `remove` (amount prohibited).

Omit all scenarios for the unchanged current budget. Existing schedules/transactions
are never mutated by projection. It returns separate forecast/cash expenses and
monthly room, allocation adjustments, named annual payments, baseline/scenario
savings, breaches, missing income, and status. Unknown savings remains `null`.

## Statement import lifecycle

| Method | Path | Purpose / inputs |
| --- | --- | --- |
| GET | `/api/imports` | Summary list, newest upload first |
| POST | `/api/imports` | Multipart fields `account_id`, `period`, and `file`; prepares CSV/text PDF |
| GET | `/api/imports/{id}` | Job status, review rows, source preview/mapping, and commit summary |
| POST | `/api/imports/{id}/mapping/default` | Apply remembered card mapping to an eligible unmapped CSV |
| PUT | `/api/imports/{id}/mapping` | Parse rows and save per-card mapping; replaces review edits |
| POST | `/api/imports/{id}/categorize` | Apply memory to empty categories without model categorization |
| POST | `/api/imports/{id}/process` | Queue local row processing/PDF extraction; poll the job afterward |
| PUT | `/api/imports/{id}/review` | Save/validate `{rows:[...]}` without committing actuals |
| POST | `/api/imports/{id}/commit` | Atomically save valid selected rows; skip exact cross-import CSV overlaps |
| POST | `/api/imports/{id}/undo` | Delete every linked actual transaction; retain import and memory |
| DELETE | `/api/imports/{id}` | Delete eligible stopped/uncommitted/undone import and release file fingerprint |
| GET | `/api/payee-rules` | Saved exact-description/type/category rules |
| PUT | `/api/payee-rules/{id}` | Correct remembered `category_id` without rewriting transactions |
| DELETE | `/api/payee-rules/{id}` | Forget memory rule; transactions remain |

CSV mapping input: `date_column`, `description_column`, `amount_column`,
`date_format` (default `%Y-%m-%d`), and `positive_is` (`purchase`, `refund`, or `null`
for all-purchase default). Mapping applies memory without Ollama. The original CSV
fields are the duplicate identity; editing row descriptions/categories does not
change it. `PAYMENT` defaults precede categorization; zero rows start unchecked.

Review rows use `date`, `description`, `amount`, `kind`, `category_id`, `selected`,
and `source_index` to retain a prepared row's provenance. The server preserves source
and validates errors/duplicate flags. Manually added rows have manual-review source.
Resolve all selected-row errors before commit; invalid unchecked rows do not block
valid ones. A commit with only already-imported rows may finish with zero additions.

```text
prepare → prepared or review (saved CSV mapping applied)
map CSV → review
process → processing → review or failed
server restart during processing → interrupted
review/manual correction → review
commit → committed → undo → undone → delete
stopped prepared/review/failed/interrupted jobs → delete
```

Poll `GET /api/imports/{id}` until processing finishes; the UI polls every 1.5 seconds.
Retries use the same process endpoint. Processing, committed, and undone jobs cannot
be edited/processed normally. Wait for processing to finish before deletion; undo
committed jobs first. Exact repeat files are blocked per account while their import
exists. Row overlaps are rechecked under an account lock at commit. Repeats within
one file are flagged rather than automatically skipped. Batch upload is a frontend
queue over these same per-file endpoints, not a separate bulk API.

Limits: 15 MiB per upload, 100 PDF pages, 500,000 extracted PDF characters, and
5,000 review rows. Scanned/nontext PDFs, unsupported encodings/formats, and invalid
column headers are rejected with a validation explanation. Original file bytes are
not retained; local review/provenance retention is explained in
[Operations](operations.md#privacy-and-data).

## Advisor request and context

`POST /api/advisor/chat` requires `month` and nonempty `message` (up to 2,000
characters). Optional fields:

| Field | Meaning |
| --- | --- |
| `history` | Up to 12 user/assistant messages, with bounded content/total length |
| `memory_epoch` | Echo `context.advisor_memory.epoch` for follow-ups with memory enabled; stale history returns 409 |
| `scenario:{name,amount,month}`  | A hypothetical one-off purchase |
| `monthly_bill` | Structured monthly payment; exclusive with purchase scenarios |
| `savings` | Explicit opening snapshot override for this request |
| `use_web` | Enable optional Brave research; default false at the API |
| `research_topic` | Required explicit public topic when using web research; chat/history never supply it |
| `research_confirmation` | Confirmation from `/advisor/research-preview` for this exact topic and query plan; required before outbound search |
| `planning:{available_savings,monthly_buffer}` | Optional separate trip-funding assumptions |

The response is `{reply,reply_truncated,context}`. `reply_truncated` is true when
Ollama ends generation at its token limit; the UI marks that answer incomplete. Context includes monthly forecasts, recent
actuals/completeness, category guide statistics, Python-calculated
`forecast_comparison`, selected scenario, `savings_projection`, `planning_capacity`,
`spending_history`, `spending_comparison`, and `web_research`. Monetary names ending `_minor` are integer minor units; **all
money in savings_projection also uses minor units**, even without that suffix.

The API waits for the completed reply while the local transport reads streamed
model output. It does not stream partial advice to the browser or expose tool access
to the model. Snapshot reads use a dedicated SELECT-only database login plus a
PostgreSQL-enforced read-only, repeatable-read transaction, released before model/search
waiting. Missing credentials, failed authentication, or unsafe/missing privileges
return advisor-only 503 responses with setup instructions; no writable fallback is used. Search is passed only a strict
public request with `use_web`, `research_topic`, and `research_confirmation`; no
financial snapshot, private message/history, or model output enters that adapter. Timeout/
research errors never save transactions or plans. The advisor must be opted in and
have a selected model; no cloud fallback or model download occurs.

## Optional advisor memory API

Settings accepts optional `advisor_memory_enabled` (default false; omission
preserves the preference). These operations use separate Memora storage.

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/api/advisor/memory/status` | Safe status/message and generation `epoch` |
| POST | `/api/advisor/memory/draft` | `{user_message,assistant_message?}` → editable `{note,warning}`; never saves |
| GET | `/api/advisor/memory?offset=0` | Up to 25 `{items,next_offset}` across all statuses |
| POST | `/api/advisor/memory/similar` | `{query}` → up to three active matches; no merging |
| POST | `/api/advisor/memory` | `{note,create_key:UUID}` → approved note, HTTP 201; identical retries are idempotent |
| GET | `/api/advisor/memory/{id}` | Note with revision history |
| PUT | `/api/advisor/memory/{id}` | `{note,expected_revision}` → new revision; conflicts return 409 |
| DELETE | `/api/advisor/memory/{id}?expected_revision=N` | Purges note/history/embedding; returns `{forgotten,epoch}` |

Note fields: `title` (1–100), `text` (1–400), `kind`
(`intention|preference|decision`), ISO `source_date`, `source_excerpt` (up to 1,000),
`cues` (up to eight nonempty strings of at most 50), and `status`
(`active|completed|abandoned`, default active). Extra fields are rejected.
Draft failure returns blank editable fields and a safe warning.

Chat context adds `advisor_memory:{status,warnings,notes,epoch}`. Model context
contains at most three active notes within 1,500 serialized characters, excluding
source excerpts. Unavailability warns without failing chat. Management returns
503 when unavailable, 409 when disabled/conflicted, and 422 for invalid fields.
Updates/forgetting invalidate pending answers and stale follow-up epochs (409).
See [memory operations and privacy](advisor-memory.md).

## Examples

Replace IDs and dates with your own values. The first two requests are read-only;
the upload prepares a review but does not commit transactions.

```sh
curl 'http://127.0.0.1:8017/api/forecast?month=2026-12'

curl -X POST 'http://127.0.0.1:8017/api/savings/projection' \
  -H 'Content-Type: application/json' \
  -d '{"months":12,"savings":{"amount":500000,"month":"2026-12","floor":0}}'

curl -X POST 'http://127.0.0.1:8017/api/imports' \
  -F 'account_id=YOUR_ACCOUNT_ID' -F 'period=2026-12' -F 'file=@statement.csv'
```

To preview a $200 monthly addition, add a `bill` to the projection body:

```json
{
  "months": 24,
  "savings": {"amount": 500000, "month": "2026-12", "floor": 0},
  "bill": {"name": "Potential payment", "amount": 20000, "start_month": "2026-12"}
}
```

## Errors and recovery

| HTTP status | Typical meaning/action |
| --- | --- |
| 403 | Nonlocal host or disallowed write origin |
| 404 | Record/estimate/schedule not found |
| 409 | Duplicate file/name, referenced record, locked import state, already converted estimate, currency lock, or disabled advisor |
| 413 | Upload exceeds size limit |
| 422 | Invalid input, unsupported file/mapping, selected review errors, or unavailable/unselected model choice |
| 503 | Optional local model/service unavailable or invalid response |
| 504 | Advisor local model exceeded its timeout |

Errors normally use JSON `detail`; validation errors can be a list rather than a
string. Background processing failure appears in the import's `status`/`error`,
not as a committed partial result. Read the response before retrying; already
committed imports/conversions cannot be blindly committed a second time.

## Bulk reads and provenance

`GET /api/forecasts?start=YYYY-MM&months=12` returns 1–24 consecutive monthly
forecasts with actual totals. The ending month must remain within 1900–9998.
`GET /api/trends` uses fixed-count aggregate reads; it returns forecast and actual
amounts separately. Expense breakdown accepts at most 120 inclusive calendar months,
returning 422 for a longer range before loading financial data.

`GET /api/transactions` returns compact display records; `provenance` contains only
the generated ACH marker, if present. `GET /api/transactions/{id}` returns full
review provenance, expanding shared PDF page references on demand. PDF page text
is stored once per import/page after commit; review and source details retain it.

`POST /api/imports/{id}/process` accepts optional `{replace_review:true}`. Existing
PDF review rows require this explicit replacement consent (409 otherwise). Failure
preserves saved review rows. Job generation tokens prevent an older worker from
writing over a newer attempt. Processing releases its DB connection during model calls.

The dues response no longer includes the unused, always-empty `missing_monthly`
and `missing_monthly_count` fields. Undated budget allowances continue to be omitted
from payment-tracking lists.

### Local advisor spending history

`context.spending_history` contains up to 12 finished calendar months, ending at
`min(selected_month, previous_current_month)` in `APP_TIMEZONE`. It includes:

- `start_month`, `end_month`, `months:[{month,status}]`, and a description of the basis.
- `categories:[{category,monthly_net_minor,comparisons}]`.
- `payees:[{payee,category,monthly_net_minor,comparisons}]` with normalized labels,
  `payee_limit` (20), `additional_payees_omitted`, and `payee_selection`.
- Each comparison identifies `months` (2 or 3), `from_month`, `to_month`,
  `first_month_minor`, `last_month_minor`, `change_minor`, `partial_month_count`,
  and `missing_month_count`. Arrays align with the shared `months` list.

`change_minor` is the last month minus the first, and is null when any month in
that window is missing. Refunds are negative spending; purchases and fees count;
payments/transfers are excluded. Partial months remain qualified evidence rather
than complete actuals. All summary values are deterministic; payee selection is
bounded and is not a claim that the full ledger was sent. `reply` may be Markdown.
No new endpoint gives the model arbitrary transaction lookup or SQL access.


### Recorded spending comparison

`context.spending_comparison` compares the latest two finished calendar months,
ending at the selected month or the latest finished month, whichever is earlier.
It contains `previous_month`, `month`, completeness statuses, `totals`, `accounts`
(named accounts only, no IDs), and `categories`. Rows contain `previous_minor`,
`current_minor`, and `change_minor`: purchases and fees less refunds, by transaction
date. Card payments and transfers are excluded. Missing months produce null values;
explicitly complete zero months produce zero. Partial data is labeled.

Its `budget_impact` rows subtract actual recorded spending from planned income for
each comparison month. Unrecorded income or missing actuals yields unknown room.
These are not verified income receipts, achieved savings, or a bank balance.
`forecast_comparison` remains separate planning evidence for forecast shortfalls;
a changed allowance never establishes changed actual spending. Future
`savings_projection` continues to use budget assumptions, not a substitution of
historical charges. History rows also include Python-calculated `average_minor`
and `sample_count`, excluding missing months. The local-model payload receives
formatted currency values for all monetary paths, including forecast changes,
annual payments, and savings. Model-only forecast/projection tables share column
labels to reduce prompt size; the API retains integer
minor units for UI calculations.


`GET /api/spending/comparison` is a deterministic Overview read, available without
Budget advisor enabled. It returns `{today,comparison}` for the latest two finished
months in `APP_TIMEZONE`, including account/category deltas and completeness. It
never invokes Ollama or web research and does not depend on the selected forecast
month. Refunds reduce spending; payments/transfers are excluded.

`GET /api/forecasts?...&include_savings=true` adds the running cash and annual
funding fields described under [Planning](#planning). `savings_adjusted_deficit`
flags a negative projected balance; if no cash estimate is available, it falls
back to the monthly budget deficit. Funding gaps are independent warnings.
Ordinary `remaining`/`deficit` fields are unchanged. The parameter defaults false.


### Permanent budget-alert acknowledgements

`GET /api/alerts/dismissals` returns `{month,kind,dismissed_at}` records.
`POST /api/alerts/dismissals` accepts a validated month and `kind` of
`forecast_deficit` or `actual_deficit`. The composite month/type key makes repeated
requests idempotent and preserves the original dismissal timestamp.
`DELETE /api/alerts/dismissals` restores all notices and returns `{restored:count}`.
Dismissals do not expire or depend on amounts and never modify financial records.
They control Overview notices only; other notifications retain their existing
checkpoint-based dismissal. The advisor login receives no access to this table.

### Bounded history pages

`GET /api/transactions` and `GET /api/imports` return
`{items,next_cursor}`. Pass `limit` (default 100, maximum 200) and return the
opaque `next_cursor` as `cursor` for the next page. A null cursor ends the list.
Transactions sort by date descending then ID ascending; imports sort by creation
time descending then ID ascending. Transaction `month`, `category_id`, and literal
`q` search filters apply before paging. Reset the cursor when filters change.
Malformed cursors and out-of-range limits return 422. Cursors describe the current
data rather than a historical snapshot; refresh starts at the first page.

Core read responses have explicit OpenAPI schemas. Generate frontend contracts
with `uv run python scripts/generate_api_types.py`; CI runs the same command with
`--check` to detect drift. Generated files are not manually formatted or edited.
