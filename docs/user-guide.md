# User guide

[Documentation index](README.md) · [Setup and operations](operations.md) · [API](api.md)

## First use

1. Open **Settings** and select the budget currency before entering financial data.
2. Review the starter categories. Add or rename them to suit your budget.
3. Add named bank/card accounts for statement imports, manual transactions, or ACH.
4. In **Recurring accounts**, add income, recurring bills, and budget allowances.
5. Save an opening savings snapshot if you want projected savings balances.
6. Use **Planning → Current budget** to inspect the next 12 or 24 months.
7. Enter actual transactions or import statements, then inspect **Spending**.
8. Add Planning goals and optionally configure card freshness monitoring and Budget advisor.

## Budget concepts

| Concept | Meaning | Changes forecast expenses? |
| --- | --- | --- |
| Recurring payable | A scheduled monthly expense or annual budget total | Yes, while active |
| Recurring receivable | Scheduled income | Increases forecast income |
| Planning goal | A named amount and target date funded from shared savings | In the Planning projection |
| Actual spending | Recorded purchases and fees minus refunds | No; reported separately |
| Paid status | Confirmation that a scheduled occurrence was paid | No |
| Category planning guide | Informational monthly category reference | No |
| Savings snapshot | User-entered opening balance for cash projections | No |
| Recorded savings balance | A dated manual savings observation | No |

Each normal forecast month stands alone:

```text
remaining = scheduled income − recurring expenses
```

There is no balance carry-forward in monthly forecasts. Savings projections and
hypothetical trip funding explicitly carry balances within their own calculations.
Actuals never get added to forecast expenses, which would count spending twice.

Choose one budget currency: USD, EUR, GBP, CAD, AUD, CHF, or JPY. All calculations
use integer minor units. JPY has no decimal places; the other supported currencies
use two. Currency is locked once financial records or planning values exist. There
is no conversion between currencies.

## Navigation and accessibility

The menu contains **Overview**, **Spending**, **Recurring accounts**,
**Planning**, **Statement imports**, and **Settings**. **Budget advisor** appears
when enabled. On phones, navigation moves above the page and Settings remains in
the header; short desktop layouts keep navigation reachable by scrolling its menu.

Use the selected-month picker or previous/next arrows for forecasts. Actual
spending initially uses the preceding month. Historical spending has an independent
ending month. Due dates and Planning funding suggestions follow today's date, not the selected
forecast month. Each section labels its own period.

Forms and action buttons support keyboard focus, Tab navigation, and native form
submission. Focus indicators remain visible. Charts have corresponding tables or
expandable details, and warnings include text alongside color. On narrow screens,
wide tables scroll horizontally within their panel.

## Overview

Overview shows **Planned expenses**, **Room in your budget**, and **Actual spending**.
**Expected income** is in Recurring accounts. Check **Current month** on Actual
spending to use the selected forecast month instead of its preceding month.
**Explore breakdown** opens the same actual period in Spending.

A forecast deficit and actual spending above that actual month's forecast income
have separate notices. **Reconcile with Budget advisor** prepares a selected-month
versus previous-month question; press **Ask** to send it. If the advisor is disabled,
the notice links to Settings instead.

Each forecast-deficit and recorded-spending notice has **Dismiss**. Dismissal is
saved in local PostgreSQL for that month and alert type, survives reloads/restarts,
and remains in effect if the amount later changes. It does not dismiss other
months/types, change spending or forecasts, or hide the budget totals/charts.
Use **Settings → Dismissed budget alerts → Restore dismissed alerts** to show
all dismissed budget notices again. Failed saves leave the notice visible.

Due-date panels show monthly and annual bills. Toggle **Unpaid only** in Upcoming
monthly bills to hide paid monthly occurrences, including recorded ACH payments.
Future unpaid ACH bills remain visible. The filter starts off and does not change
annual expenses, payment history, or payment status.
 The right-hand **What changed this
month?** card compares recorded spending in the latest two finished months,
independently of the selected forecast month. It refreshes after changes and when
you return to the app, without using a model or requiring the advisor to be enabled.
Purchase planning is available from the main menu.

**The bigger picture** shows the selected year's income and expense bars. Deficit
markers appear only when that month's forecast remaining plus your current
manually entered savings is negative. Zero is covered. Each month is checked
independently against the same current balance; this is not a running savings
projection. Unset savings is treated as zero for markers. The table shows both
monthly remaining and remaining plus current savings; income/expense bars and
ordinary forecast-deficit alerts stay based on the original monthly forecast.
Choose a bar or table month to change the selected forecast month. Reserve checks
appear when enabled/configured; monitored card warnings appear across views.

## Recurring accounts

Use **Add account** for a monthly or annual payable/receivable. Payables require a
category. The first month is required; the final month is optional and inclusive.
Due dates are optional, so a grocery or entertainment allowance can stay in your
forecast without appearing as an unpaid bill.

Annual amounts are full yearly totals. For annual payables:

- **Distribute annual expense across 12 months** allocates the yearly amount monthly
  from the first active month. Rounded cents are spread so a full rate cycle sums
  to the yearly total. A partial active year includes only active allocations.
- Turn distribution off to count the full expense in its configured due month.
  Until a due date is configured, its first-month anniversary is used.
- Annual income counts fully in its first-month anniversary, without distribution.

Use **Adjust amount** for an ongoing default effective from a chosen month or an
individual-month override. The override takes priority; later defaults retain their
own effective months. Annual adjustments remain yearly totals. A one-month override
for an annual bill paid in one month must use its due month.

**Amount history** shows defaults and overrides. Changes can be removed except the
initial default. Edit a schedule to rename it, change its category, adjust its first
or final month, or configure dates/ACH. Moving the first month retains changes on
their calendar dates and establishes a starting default where needed. Structural
edits, including the distribution flag, can recalculate historical forecasts; use
effective amount changes when earlier months must stay intact. Recorded actuals
are preserved when a schedule changes or is deleted. Set a final month to retire
a bill while retaining its payment history; deleting the schedule removes its linked
payment confirmations and ACH occurrence identities.

### Due dates and payment status

Configure **Bill due day**, plus **Annual bill due month** for annual payables.
Days 29–31 clamp to the last valid day in short months. Contractual due dates and
ACH debit dates are separate fields.

**Track payments from** defaults to the date tracking is first configured. Choose
an earlier date deliberately to include older unpaid occurrences. Abacus does not
invent overdue history before that boundary.

Overview shows:

- Upcoming monthly occurrences from today through 30 days ahead, inclusive,
  including those already confirmed paid. Unpaid manual monthly occurrences have
  a muted red **Mark paid** action so they stand out while scrolling.
- Older tracked monthly occurrences that remain unpaid.
- All active annual expenses separately, with full next-payment amounts, oldest
  unconfirmed occurrences/counts, or allowance details when no due date is set.
- Expandable payment history with recorded dates and amounts.

For a manual bill, **Mark paid** opens a confirmation with an editable paid date.
Early payment is allowed; future paid dates are rejected. **Edit paid date** corrects
it and **Mark unpaid** reverses it. A monthly confirmation covers `YYYY-MM`; an
annual confirmation covers `YYYY`. Changing amounts or due dates retains that
period's confirmation and its historical snapshots.

Paid status does not create/delete actual spending. ACH occurrences need no manual
confirmation: recorded debits show **Paid by ACH**, while future ones show scheduled
ACH. Manual transactions and imports do not automatically confirm manual bills.
Undated allowances, such as medical copays, need no paid confirmation.

### ACH recording

Create a named bank account in Settings. For a monthly payable, enable **ACH ·
automatically record monthly actual spending**, select the bank account and debit
day, and choose **Record ACH actuals from**. The form defaults the recording start
to the current month; backdating it explicitly requests catch-up.

The running backend checks every minute and catches up on startup. It records each
due, active month once, using its effective amount/override and category. Short-month
days clamp. Spending labels generated rows **Scheduled ACH · confirm with bank**.
Correct recorded transaction details there when needed.

This records an assumed debit; it does not initiate a payment or connect to a bank.
Disabling ACH stops future generation and retains history. Reenabling catches up
from the configured start. Deleting a generated transaction does not regenerate
that occurrence. Schedule changes do not rewrite already generated actuals.
Imported/manual bank debits are not automatically reconciled with generated ACH
records; review overlap to avoid counting the same debit twice.

### Annual expected income

In **Recurring accounts**, **Annual expected income** tracks extra income estimates
for the selected calendar year, such as tax refunds, sale proceeds, or variable
earnings. It is separate from regular monthly income and from annual recurring
income already scheduled in its anniversary month.

Add a named source, enter its yearly amount or move its slider, and choose
**Include in monthly income**. Inclusion defaults off. Save to apply edits; moving
a slider alone never changes the forecast. Multiple sources can be included
independently. Included amounts are divided across January–December, with leftover
minor units assigned to the earliest months so the twelve allocations sum exactly
to the annual amount. **Monthly allocation of included estimates** shows the result.

The estimates apply only to that year; they do not recur in the next. They are
budget assumptions, not confirmed receipts or a monthly deposit schedule. Included
estimates affect forecasts, projections, and advisor context. They create no
actual transactions and do not increase recorded savings. Avoid entering a source
already represented by recurring income. Removing a source removes its forecast
contribution; existing recurring income remains independent.

### Savings

Open **Planning → Savings balance & slider**. Set an exact opening amount
or use the slider, choose **Balance month**, optionally set a savings floor, and
save. The balance belongs to the start of that month; it is not bank-synchronized
or automatically advanced. Slider edits are temporary until saved.

Planning and the advisor use this snapshot. Saving a current/past month
also records that month's opening balance in savings history. Saving a future
projection assumption does not create a current savings observation. Goal targets
remain unchanged when the savings balance changes.

## Planning

**Planning** is the single home for tax, vacation, and purchase goals. The top
shows your saved savings balance, total planned, and unassigned savings. Open
**Savings balance & slider** to update the shared opening balance or protected
floor. Annual income estimates remain in Recurring accounts.

Choose **Add a plan** and enter **Name**, **Target amount** (slider or exact entry),
and **Target date**. Category defaults to `purchase`; choose `tax`, `vacation`, or a
category managed in **Settings → Planning categories**. Saving a plan creates a
funding goal, not an actual transaction or a second recurring bill.

**Use annual expense** fills this same form from an existing annual bill. The
linked bill remains intact. Only one goal per annual expense/year is allowed.
The funding projection replaces that year's scheduled cash amount with the plan's
amount/date, so it counts once even if the original annual bill was spread monthly
or had no due day. Editing a goal does not edit the saved bill schedule.

Plans share the one savings balance in earliest-target-date order, preserving the
savings floor. Each card shows set aside, still needed, and a suggested monthly
amount. Suggestions are not recorded transfers or proof of affordability. Without
savings, funding is shown as unknown. No baseline, checkpoint, inclusion switch,
or separate trip-funding input is required.

**See the funding projection** shows conditional month-end balances over 24 months
from the saved balance month. It uses planned income and bills, includes each goal
once, and labels missing income. Full-month income is assumed; exact-day cash
availability and goals outside the displayed horizon are not established. Main
monthly budget forecasts remain based on recurring bills and income; the Planning
projection additionally considers your goals. Existing imported actuals remain
separate from both forecasts.

**Discuss** opens Budget advisor with that saved plan. **Edit** uses the same short
form. **Delete** permanently removes the goal and its earmark after confirmation;
its linked bill, savings balance, and actual transactions remain. No archive or
restart restores it. Overview links to Planning below the three summary cards.

## Spending

### Current spending and manual transactions

Spending has planner-style navigation for **Expense breakdown**, **All expense
entries**, **Transactions**, and **Historical trends**. Only the selected section
is shown. Breakdown and entries share the date range, source, and selected
category; switching to Transactions preserves those choices.

**Expense breakdown** and **Transactions** follow the actual-spending period.
Initially this is the month before the selected budget month; **Current month** switches to that selected month. The
checkbox is shared with Overview. Previous/next controls step through complete
months. In the breakdown month field, type **YYYY-MM** and press Enter or leave
the field to apply it. Incomplete or out-of-range months do not change the period;
Escape restores the current selection. Custom From/Through ranges remain available.
Transaction search matches descriptions; rows can be added, edited, deleted, and
assigned a named account and category.

Enter positive amounts for every transaction type:

| Type | Effect on recorded spending |
| --- | --- |
| `purchase` | Adds expense |
| `fee` | Adds fees/interest as expense |
| `refund` | Subtracts expense in its recorded month/category |
| `payment` | Excluded to avoid counting card settlement twice |
| `transfer` | Excluded |

**Expense breakdown** supports inclusive **From**/**Through** dates, category totals,
charges/refunds/net, a bar chart, and individual records with account names. Choose
a category bar/button/table row to open **All expense entries** for that category;
**All categories** resets the filter. The entries section initially shows 50
records; **Show more** reveals additional batches. **Transactions** separately
provides search, manual entry/editing, and monthly completeness controls.

Switch the breakdown to **Planned expenses** for recurring payables plus included
purchases across complete calendar months. Forecast and actual ranges remain
separate. Refund/zero-net categories remain visible rather than disappearing from
a chart that only accepts positive slices.

### Historical spending and category guides

**Historical trends** places **Spending, over time** at the top. Its independent ending
month selects a rolling 12-month window. **Latest 12 months** returns to the window
ending last month. Filter one or more categories, toggle forecast overlays, and
expand the matching data table. Choosing a chart/table month opens its Expense
breakdown. Historical category filters do not change Transactions' description search.

The numeric mean uses eligible past months in that window. Current/future and
missing months are excluded. Past months with recorded activity count even if
incomplete, with a warning; explicitly complete zero-spending months count as zero.
A category with no expenses in an included month contributes zero. Refunds reduce
the signed mean, and incomplete card data can understate it.

**Category means & planning guides** lists each category's mean and an editable
monthly reference. Enter a guide manually, choose **Use mean**, or clear it. A
negative mean suggests a zero guide; no eligible history gives an unknown mean.
Suggestions change with the historical window, while saved guides stay fixed.
Guides never add forecast expenses or reduce remaining budget/savings. They let
pets, dining, or travel have useful references when costs are covered by card bills.

### Completeness

Spending does not reload the workspace on a 60-second timer. Use **Transactions →
Refresh** to fetch current spending when you choose; saves and imports still update
the data. Same-period transaction and breakdown data stays visible while refreshing,
preserving search, focused controls, and scroll position. Selecting another period
hides the previous period's records until its request completes. Automatic ACH
recording continues on the backend every minute; due-date and freshness cards keep
their own local updates without resetting the transaction list.

In Transactions, mark the actual month complete only after all records are entered.
An unmarked month with no records is **missing**. Recorded months are **partial**
until marked complete; current/future months always display partial. A complete
month with no records is a known zero. Completeness is budget-wide and manual;
imports/undo/deletions do not prove all statements are present. Revisit the marker
after correcting records.

## Statement imports

Use **Import statements** in the header or the dedicated **Statement imports** menu.
It is not part of Spending's transaction-entry controls. CSV and selectable-text
PDFs are supported; scanned PDFs require another export because OCR is unavailable.

### Upload and map

1. Choose one or more files. Set default card and statement period, then check each
   queued file's account/period, especially for a multi-month batch.
2. Upload sequentially. One failure leaves other files available. **Stop after
   current file** pauses the queue; retry pending/failed entries without uploading
   successful ones again. There is no watched-folder or cron ingestion feature.
3. Open each CSV review and map date, description, and one signed amount column.
   Use **Apply & remember mapping** to save headers, date format, and sign convention
   for that card. Existing mapped reviews keep their own settings. Missing required
   headers leave the new file ready for manual mapping with a warning.
4. For PDFs, select an installed local model in Settings and choose **Extract PDF
   transactions / retry**. The model proposes rows/types, not categories. Extraction
   runs in the background; reopening the import polls its status.

Each file is limited to 15 MiB, 100 PDF pages, and 5,000 rows. Extracted PDF text
is limited to 500,000 characters; PDFs with any scanned/empty page are rejected. CSV accepts UTF-8
(including BOM), comma/semicolon/tab separators, and a first-five-row source preview.
Combine separate debit and credit columns into one signed column before upload.
The UI offers `YYYY-MM-DD`, `MM/DD/YYYY`, `DD/MM/YYYY`, `MM/DD/YY`, and `MM/DD` dates.
Yearless dates resolve against the statement period, including year boundaries.

Rows default to purchases regardless of sign unless you choose a sign convention.
Set **Positive = purchase; negative = refund** or its inverse when appropriate.
Descriptions containing the case-insensitive substring `PAYMENT` default to payment
before category suggestions. Review and correct exceptions explicitly.

### Review, save, retry, and remove

Review dates, original descriptions, amounts, types, categories, source details,
duplicate notes, and net spending totals. Use **Apply remembered payees** to fill
empty categories, or label rows manually. **Add review row** allows manual repair.
Zero-amount rows start unchecked; correct/select them if they should be saved.
Invalid unchecked rows do not block valid selected rows.

**Validate & save review** stores edits without actual transactions or category
learning. **Save selected transactions** revalidates and saves atomically; only
saved labels teach memory. **Finish import** can complete an all-overlap import
without adding transactions. A batch displays **Saved → View** after commit and
**Continue** for unfinished reviews.

Failures leave saved spending unchanged. Retry extraction, repair rows manually,
or delete the import and start over. Restarted processing becomes **interrupted**
and recoverable. Wait until processing stops before deleting. **Undo import**
removes all its linked actual transactions, including later edits; it retains the
import and file fingerprint. Undo a committed import before deleting it. Deleting
removes review/fingerprint data so the file can be uploaded again. Remembered
payees and per-card CSV profiles survive undo/import deletion.

### Duplicate handling

| Situation | Behavior |
| --- | --- |
| Identical file, same account | Blocked while its import exists, including after undo |
| All original named CSV fields match a saved row in another import for that account | Always skipped; rechecked at commit |
| Identical rows within one new file | Flagged but selectable, e.g. a bridge toll in each direction |
| Different account, PDF/manual row, or nonidentical CSV fields | Not automatically skipped by the CSV overlap rule |

CSV field equality includes unmapped fields, case, whitespace, and original number/
date formatting; column order does not matter. Editing a transaction/category does
not rewrite its CSV identity. Existing duplicates are not retroactively removed.
After undo removes transactions, their overlap evidence is gone, but the exact
file remains blocked until its import is deleted.

### Payee classification

Saving a categorized manual transaction/edit or committing an import remembers its
exact description and type. Rules are shared across accounts, but purchases,
refunds, and fees are separate. Matching preserves row types, amounts, and existing
review categories. Priority is existing review label, exact remembered variant,
unambiguous normalized group, then conservative similarity; unknown/conflicting
matches stay for review. Rules persist until forgotten in Settings.

Normalization ignores Unicode/case/spacing differences, explicit `#store` numbers,
leading years/dates, apostrophes, and punctuation. Meaningful brand numbers remain.
The [merchant configuration](../backend/abacus/payee_matching.json) also groups:

- Amazon.com, Amazon Marketplace, and Amazon Prime order codes into three separate groups.
- A2 PCI Parking, Panera Bread, PetSmart, and REI store/location variants by brand.
- ActBlue's `*` recipient suffixes under ActBlue.

**Remembered payees** displays exact saved variants, so it may contain hundreds of
rows even when normalized matching works. Editing/forgetting one rule does not
rewrite transactions. Normalization is not a database cleanup or trained model.

Patterns run case-insensitively on each classification pass; JSON `"\\1"` means
retain the first capture group. A literal replacement such as `"rei"` makes a
canonical name. `*` must be escaped to match a literal asterisk. Use merchant-specific
boundaries and test real variants before broadening patterns. The default fuzzy
threshold is `0.94` with a `0.05` margin; setting the threshold to `1` disables
similarity. Similarity also constrains first words, numeric components, transaction
types, and name lengths. **Similar payee · check category** labels its suggestions.
See [classification/training](../training/README.md) for exact behavior and exports.

## Budget advisor

Enable Budget advisor and select an installed local model in Settings. Chat can
answer spending questions, review saved Planning goals, and research a trip or
purchase. There is one chat card: no Planner context dropdown or research sidebar.

From a plan, choose **Discuss**. Chat shows a removable **Discussing** label and
reads the plan by ID with every question. Editing/deleting that plan invalidates
old context; a deleted/changed plan cannot return a stale in-flight answer. The
conversation stays available when budget data refreshes. Read-only spending
comparisons and transaction evidence appear below chat.

**Enable web search** is next to Ask. When enabled, enter a public search topic,
preview its queries, and approve them inline. Only that approved public topic goes
to Brave. Financial snapshots, private chat, memory, and account details stay local.
Travel and product topics share the chat workflow; researched sources appear with
the answer. Web search requires `BRAVE_SEARCH_API_KEY`.

**Add to Planning** on an answer asks the local model to suggest a name, exact
amount, target date, and category. It opens the normal Planning form for review.
Unknown dates or amounts remain blank. Nothing is saved until **Save plan**.

The advisor's database login has SELECT-only access, including `plans` and
`plan_categories`. Setup/update maintains the explicit allowlist. All monetary
figures passed to the model are Python-formatted currency amounts; funding totals
are calculated by Python, not the model. Predictions are conditional, not bank
verification. Local-model responses can still be mistaken.

Replies support Markdown and source citations. A token-limit warning marks an
incomplete answer. Optional [approved local memory](advisor-memory.md) remains
independent of saved plans. An unavailable-memory warning describes that answer;
use Settings → Advisor memory → Refresh memory to check the current connection.

## Settings

Settings cards stack independently on wider screens and use one column on smaller
screens. **Remembered payees** starts collapsed; expand its heading to review,
edit, or forget rules. The heading shows the number of saved rules.

- **Budget currency:** choose before financial records lock it.
- **Local model for advisor / PDF extraction:** list installed Ollama models with
  **Refresh models**; selecting none leaves CSV/manual workflows available.
- **Enable Budget advisor in the main menu:** optional; disabling chat does not
  disable PDF extraction or delete the model setting.
- **Planning categories:** add, rename, or delete planning labels.
- **Bank & card accounts:** add/rename/delete named accounts; names are not bank
  connections. Accounts/categories referenced by financial records may need those
  references resolved before deletion. Deleting a category also removes its payee
  rules. Deleting a statement does not erase the card's CSV profile.
- **Alert after 30 days:** opt in per account. Exactly 30 days is current; more than
  30 is stale. An account with no evidence warns immediately. Saved dated transactions
  and committed statement coverage establish freshness; old cycles imported today
  do not appear current. This does not prove a complete statement or bank sync.
- **Categories:** add/rename/delete categories used by schedules and actuals.
- **Remembered payees:** edit category memory or forget a specific rule without
  recategorizing history. A later saved label can teach it again.

### Alerts

| Alert | Trigger | Controls/action |
| --- | --- | --- |
| Forecast deficit | Forecast expenses exceed that month's income | Reconcile with advisor or edit plans; no separate disable toggle |
| Actual deficit | Actual net spending exceeds its own month's forecast income | Review Spending; no separate disable toggle |
| Card information stale/missing | Per-account opt-in; last evidence older than 30 days or absent | Settings checkbox; import the relevant account |
| Planning funding | Shared savings does not yet cover a goal | Open Planning to review dates, suggested contributions, and savings |
| Import/research/model errors | Validation, processing, or optional service failure | Correct/retry; saved spending stays unchanged on failed processing |

All notices remain inside the app. There are no email, push, OS notifications, bank
connections, automatic transfers, booking tools, or watched-folder imports.

### Review recovery and large date ranges

Retrying PDF extraction with existing review rows asks before replacing edits.
Failed extraction retains saved edits; successful re-extraction replaces them.
Normal transaction lists omit statement source text. Import review retains the
original descriptions and page references for inspection. Dates must fall in
1900–9998. Expense breakdown ranges may cover at most 120 calendar months; narrow
the range for longer histories.
