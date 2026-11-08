# User guide

[Documentation index](README.md) · [Setup and operations](operations.md) · [API](api.md)

## First use

1. Open **Settings** and select the budget currency before entering financial data.
2. Review the starter categories. Add or rename them to suit your budget.
3. Add named bank/card accounts for statement imports, manual transactions, or ACH.
4. In **Recurring accounts**, add income, recurring bills, and budget allowances.
5. Save an opening savings snapshot if you want projected savings balances.
6. Use **Purchase planner → Current budget** to inspect the next 12 or 24 months.
7. Enter actual transactions or import statements, then inspect **Spending**.
8. Optionally configure reserve checks, card freshness monitoring, and Budget advisor.

## Budget concepts

| Concept | Meaning | Changes forecast expenses? |
| --- | --- | --- |
| Recurring payable | A scheduled monthly expense or annual budget total | Yes, while active |
| Recurring receivable | Scheduled income | Increases forecast income |
| Included purchase | A saved one-time plan counted in its month | Yes |
| Draft purchase/payment estimate | A possibility for preview | No, until explicitly included/converted |
| Actual spending | Recorded purchases and fees minus refunds | No; reported separately |
| Paid status | Confirmation that a scheduled occurrence was paid | No |
| Category planning guide | Informational monthly category reference | No |
| Savings snapshot | User-entered opening balance for cash projections | No |
| Reserve target | A fixed plan for funding dated annual bills | No |
| Recorded savings balance | A dated manual observation for reserve checks | No |

Each normal forecast month stands alone:

```text
remaining = scheduled income − recurring expenses − included purchases
```

There is no balance carry-forward in monthly forecasts. Savings projections and
hypothetical trip funding explicitly carry balances within their own calculations.
Actuals never get added to forecast expenses, which would count spending twice.

Choose one budget currency: USD, EUR, GBP, CAD, AUD, CHF, or JPY. All calculations
use integer minor units. JPY has no decimal places; the other supported currencies
use two. Currency is locked once financial records or planning values exist. There
is no conversion between currencies.

## Navigation and accessibility

The menu contains **Overview**, **Recurring accounts**, **Purchase planner**,
**Spending**, **Statement imports**, and **Settings**. **Budget advisor** appears
when enabled. On phones, navigation moves above the page and Settings remains in
the header; short desktop layouts keep navigation reachable by scrolling its menu.

Use the selected-month picker or previous/next arrows for forecasts. Actual
spending initially uses the preceding month. Historical spending has an independent
ending month. Due dates and reserve checks follow today's date, not the selected
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

Due-date panels show monthly and annual bills. The purchase shortcut opens Purchase
planner. **The bigger picture** shows the selected year's income and expense bars;
choose a bar or table month to change the selected forecast month. Reserve checks
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

### Savings

The **Savings** panel sits beside **Expected income**. Set an exact opening amount
or use the slider, choose **Balance month**, optionally set a savings floor, and
save. The balance belongs to the start of that month; it is not bank-synchronized
or automatically advanced. Slider edits are temporary until saved.

Purchase planner and the advisor use this snapshot. Saving a current/past month
also records that month's opening balance for reserve checks. Saving a future
projection balance does not create an actual savings observation. A saved reserve
funding target remains unchanged in either case.

## Purchase planner

### Current budget and cash projections

**Current budget** is selected initially and needs no hypothetical bill. Choose
12 or 24 months. With savings set, the projection starts at the saved balance month;
without savings, it starts at the selected forecast month and shows budget/cash
flow without inventing a balance. The chart offers monthly budget room and, when
available, projected savings.

The summary shows starting-month budget room, lowest projected savings, and ending
savings. **Monthly comparison & assumptions** exposes income, forecast expenses,
room, cash expenses, cash remaining, named annual payments, and month-end savings.

For dated, distributed annual bills, cash calculations remove the monthly
allocations from expenses, leaving that cash in savings, then subtract the full
annual payment when due. This avoids counting the allocation and payment twice.
Undated annual allowances retain their budget timing. Annual bills already counted
fully in their due month are not added again.

```text
cash expenses = forecast expenses − dated annual allocations + distributed annual payments due
cash remaining = income − cash expenses
month-end savings = previous savings + cash remaining
```

The savings balance includes money reserved for annual bills; it is not all free
spending money. For example, $5,943.67 of forecast expenses with $791.67 of dated
allocations and a $1,500 annual payment becomes $6,652 cash expenses. With $6,000
income, savings falls by $652 that month. This can happen even with positive
forecast room, because the reserve is being spent on its intended bill.

These are full-month estimates. Payday ordering, interest, inflation, live bank
balances, and actual transaction reconciliation are not modeled. Missing income
is flagged instead of being treated as a confident affordability result.

### Recurring payment scenarios

Choose **Add payment**, **Change payment**, or **Remove payment**:

- Add: enter name, monthly amount, start/end months, and optionally a due day.
  Previewing needs no category; saving a draft requires one. **Save estimate**
  leaves it outside expenses. **Add to recurring bills** explicitly creates a
  real monthly payable once. An already added estimate stays in the baseline once.
- Change: select an existing payable, enter the new amount and effective month,
  and optionally limit the final month. Annual entries use the full annual total.
  Earlier months, explicit overrides, and later scheduled defaults remain intact.
- Remove: select a payable and exclusion window. It is removed only from that
  hypothetical window, including the corresponding annual cash payments.

The summary/chart/table compare current and proposed budgets. Change/remove are
preview-only; use Recurring accounts to apply real edits. **Current budget** returns
to the unchanged baseline. **Discuss this preview with Budget advisor** sends an
add-payment preview and savings assumptions to optional local chat.

### One-time purchases

Use **Plan a purchase** to save a name, category, amount, month, and optional notes.
Drafts stay outside forecasts. **Preview impact** counts that purchase once in its
month without changing its inclusion status. **Include in budget** counts it;
**Return to draft** removes its forecast effect while preserving the estimate.
Edit or delete a purchase from its card. Include a trip as a one-time estimate when
you have chosen a total; an advisor's proposed price range is not a saved purchase.

## Spending

### Current spending and manual transactions

**Current** follows the actual-spending period. Initially this is the month before
the selected budget month; **Current month** switches to that selected month. The
checkbox is shared with Overview. Previous/next controls step through complete
months. Transaction search matches descriptions; rows can be added, edited, deleted,
and assigned a named account and category.

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
a category bar/button/table row to drill down; **All categories** resets it. Details
initially show 50 entries; **Show more** reveals additional batches.

Switch the breakdown to **Planned expenses** for recurring payables plus included
purchases across complete calendar months. Forecast and actual ranges remain
separate. Refund/zero-net categories remain visible rather than disappearing from
a chart that only accepts positive slices.

### Historical spending and category guides

**Historical** places **Spending, over time** at the top. Its independent ending
month selects a rolling 12-month window. **Latest 12 months** returns to the window
ending last month. Filter one or more categories, toggle forecast overlays, and
expand the matching data table. Choosing a chart/table month opens its Current
breakdown. Historical category filters do not change Current's description search.

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

## Annual bill reserve checks

Enable **Annual bill reserve alerts** and set **Reserve checkpoint day** in Settings
(default enabled/day 1). Days 29–31 clamp in short months. In **Recurring accounts →
Annual bill reserve plan → Set funding target**, explicitly save an opening baseline
and month. The plan snapshots dated annual payables distributed monthly, including
future amount changes/overrides. No target is invented before setup.

```text
reserve target = max(0, fixed baseline + allocations due by checkpoint
                        − annual payments scheduled before that date)
```

Prior-month allocations should arrive by the next month's checkpoint day. With a
$500 baseline plus $791.67 allocated in November, December 1 targets $1,291.67.
Optional forecast surplus is excluded. The full baseline is treated as available
for these bills; savings for other goals is not separately earmarked. Undated
allowances and non-distributed annual bills are outside this reserve plan.

Use **Record savings balance** to enter an opening balance and **Balance as of** date,
before annual payments due that day. An after-payment balance belongs to the next
date; future observations are rejected. Reusing a date corrects it. The history
lists the 12 most recent dated observations. Observations do not change the saved
Purchase planner snapshot; the existing slider can update that separately.

Overview and Purchase planner distinguish:

- Missing/stale balance: **Update savings**, not an assertion that a transfer was missed.
- Fresh balance below target: the amount needed to reach the saved reserve target.
- Upcoming payment risk: recorded balance plus planned allocations may not cover
  payments due within 30 days. Same-day bills share funds; future allocations are
  clearly unconfirmed.
- On track or a scheduled next checkpoint: a quieter status with the next target.

**View funding plan** exposes current/upcoming checkpoints and allocation/payment
components. **Dismiss until next checkpoint** suppresses notices until that date;
a new observation clears the dismissal. Settings can disable alerts without
removing the plan or observation history. Checks follow today in `APP_TIMEZONE`,
refresh every minute and on foreground/focus, and are independent of forecast month.

Updating observed savings never lowers the fixed target. Annual schedule edits
show a review notice; only **Replace funding target** adopts new schedules or a
baseline. Scheduled payments are subtracted after their due day even if not marked
paid; this is an assumption, not bank verification. Reserve checks create no
transactions or payment confirmations. A reserve target is not an extra expense.

## Budget advisor

Optional **Memora** recalls approved intentions, preferences, and decisions in
later conversations. It defaults off. Choose **Remember this**, review the local
draft and source excerpt, then **Save memory**. Settings provides editing, revision
history, completion/abandonment, and confirmed forgetting. Goals are statements,
not achieved savings, and never change budget calculations. See the complete
[advisor memory guide](advisor-memory.md) for setup, controls, and privacy.

Choose an installed local model in Settings, enable **Budget advisor in the main
menu**, and save. No models download automatically. Ask a general budget question,
select saved planning context, or discuss an add-payment preview from Purchase
planner. Create/edit estimates in Purchase planner; chat itself is read-only.

Each turn reads a fresh snapshot: forecasts for the selected month and following
11 months (23 with web research), three months of recent category actuals, up to
12 finished calendar months of category/payee spending history, category guides,
upcoming drafts, a previous-month forecast comparison, and any
selected purchase/payment/savings scenario. Python calculates balances and deltas.
Expand **Budget context** and calculated result panels to inspect the numbers.

Replies render Markdown headings, emphasis, lists, code, and tables. Source citations
remain clickable; remote images and links not present in verified research sources
are disabled so model-generated URLs cannot transmit financial details.

Ask **“What could I do to increase my savings?”** to discuss recorded category and
payee changes. Python computes the first-to-last difference over the latest two
and three finished months. For example, restaurant spending of $150 then $200 is
a recorded $50 increase. Refunds reduce spending; card payments
and transfers do not count. Current/future months are excluded; missing months
produce unknown changes, and incomplete months are flagged. History ends at the
selected month or the latest finished month, whichever is earlier.

**Budget context → View the snapshot used for the last answer → Local transaction
history used for this answer** shows category amounts, data completeness, and
calculated differences. Up to 20 normalized payees are included, prioritizing
recent increases and then recent spending; omitted-payee counts are visible.
These are transaction labels grouped by existing normalization rules, not verified
merchant identities. Suggestions do not change the budget or actual transactions.

The snapshot uses a **dedicated SELECT-only PostgreSQL login** and a **read-only,
repeatable-read transaction**, released before the model responds. Setup and the
updater maintain its explicit permission allowlist; see [advisor account setup](operations.md#dedicated-advisor-database-login).
Missing credentials or grants disable advisor requests only, without falling back
to the writable login. The model receives a bounded local snapshot, not credentials,
SQL, or tool access.
**No personal financial context is sent to Brave**: search receives only the
separately entered, previewed, approved public travel topic. Database amounts,
payees, transaction history, private chat/history, and model responses never feed
search construction. The financial snapshot goes only to loopback Ollama.

From a deficit alert, **Reconcile with Budget advisor** prepares a question comparing
months, turns web research off for that handoff, and clears unrelated scenario
selection. Press **Ask**. **What changed this month?** shows income/expenses/remaining,
named changed schedules/purchases, and their effect on budget room. Reductions are
suggestions; lowering future entertainment spending does not reduce a card bill
already owed. **Preview changes in Purchase planner** lets you test an adjustment.

A narrow unambiguous phrase such as “another $200 monthly bill” can be converted
into a deterministic monthly scenario starting in the selected month. Ambiguous
amounts/dates/durations need explicit planner fields. Saved savings is used when
available; without it, only monthly budget impact is calculated.

### Web research and trip funding

Configure your own Brave key as described in [Operations](operations.md#optional-local-model-and-web-research).
**Use current web research** becomes available but defaults off. Enter a
**Public research topic** with travel details only, select **Preview public searches**,
and approve the displayed terms before asking. Editing the topic clears approval.
The preview does not contact Brave; only an approved request searches. Chat and
history never become search queries. The sent terms are also shown with the reply. Research provides excerpts, clickable sources/retrieval dates, missing
details, and partial/failure labels. It does not verify exact-date availability or
book anything. Confirm dates, traveler counts, departure airports, currency,
accommodation preferences, fees, and estimates before relying on a trip plan.

**Funds already set aside** and **Monthly breathing room to preserve** support a
separate hypothetical 24-month trip-funding calculation. Contributions use
nonnegative forecast room after the buffer, starting no earlier than the current
month. Missing income/funding assumptions leave readiness unknown. A proposed trip
range becomes a calculated selected scenario only after you choose a purchase
estimate. Contributions are not reserved in the budget or guaranteed available cash.

Chat stays in tab memory and survives menu navigation. New conversation, reload,
context month/model changes, or disabling the advisor clear it. Cancel stops UI
waiting; the model may finish its current computation. Errors restore the question
for retry and do not change financial records. See [timeout troubleshooting](operations.md#troubleshooting).

## Settings

- **Budget currency:** choose before financial records lock it.
- **Local model for advisor / PDF extraction:** list installed Ollama models with
  **Refresh models**; selecting none leaves CSV/manual workflows available.
- **Enable Budget advisor in the main menu:** optional; disabling chat does not
  disable PDF extraction or delete the model setting.
- **Annual bill reserve alerts / Reserve checkpoint day:** control reserve reminders.
- **Bank & card accounts:** add/rename/delete named accounts; names are not bank
  connections. Accounts/categories referenced by financial records may need those
  references resolved before deletion. Deleting a category also removes its payee
  rules. Deleting a statement does not erase the card's CSV profile.
- **Alert after 30 days:** opt in per account. Exactly 30 days is current; more than
  30 is stale. An account with no evidence warns immediately. Saved dated transactions
  and committed statement coverage establish freshness; old cycles imported today
  do not appear current. This does not prove a complete statement or bank sync.
- **Categories:** add/rename/delete categories used by schedules, purchases, and actuals.
- **Remembered payees:** edit category memory or forget a specific rule without
  recategorizing history. A later saved label can teach it again.

### Alerts

| Alert | Trigger | Controls/action |
| --- | --- | --- |
| Forecast deficit | Forecast expenses exceed that month's income | Reconcile with advisor or edit plans; no separate disable toggle |
| Actual deficit | Actual net spending exceeds its own month's forecast income | Review Spending; no separate disable toggle |
| Card information stale/missing | Per-account opt-in; last evidence older than 30 days or absent | Settings checkbox; import the relevant account |
| Annual reserve check | Missing observation, below target, or upcoming coverage risk | Settings toggle/day, manual update, plan review, dismissal |
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
