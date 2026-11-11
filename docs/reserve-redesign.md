# Proposed savings reserves

Status: implementation plan for review. The existing reserve checker still uses
the workflow in the [user guide](user-guide.md#annual-bill-reserve-checks).

## One savings balance, several goals

A reserve is a named portion of savings for an upcoming expense. Start with the
existing **Savings** balance and its date; do not ask for another reserve baseline.
Use one shared source named `savings` for winter tax, summer tax, and fall vacation.
These are earmarks within that balance, not three accounts or three new expenses.

The current app stores one manual savings snapshot, not bank account balances.
The first version should reuse that snapshot and its observation history. It does
not need a new account ledger or multi-account transfers. `savings` identifies this
shared source; existing transaction accounts do not supply a verified balance.

## Setup and daily use

1. Open **Savings → Reserves**. Show the saved savings amount and date immediately.
   If savings is missing, set it once in the same panel. Keep the savings floor as
   a protected buffer, separate from the reserves.
2. Choose **Add reserve**. Either select an existing annual expense distributed
   through the year, or enter a name, target amount, and target date.
3. For a linked annual expense, fill the name, amount, next due date, and existing
   monthly allocation from its schedule. Ask for a missing due date inline. No
   need to reenter the tax amount or start a combined funding plan.
4. Show the goal immediately: **Set aside / Target**, **Still needed**, **Due**,
   **Monthly funding**, and a plain status with its reason. Allow edit, pause,
   and permanently delete. Deleting removes the goal, its contribution plan, and
   goal-owned research/draft details from active storage, rather than archiving
   them. The confirmation identifies any independently linked expense that will
   remain; deleting a reserve does not silently delete an existing bill or purchase.
   Draft purchase plans and reserve goals must both have a permanent delete action.
   Deleted goals never return on restart or migration. Savings observations remain
   separate financial records.
5. Use **Update savings** in this panel or the existing Savings panel. Both update
   the same dated balance, which the advisor and Purchase planner also use.
   A future projection assumption is not a current balance.

Keep the target/date fields sufficient for a manual goal. There is no separate
baseline month, schedule snapshot confirmation, checkpoint setup, or independent
balance to maintain. Optional details can expose funding assumptions and history.

## Sharing existing savings

Automatically assign available savings to active reserves in earliest-deadline
order, up to each target. Use creation order to break equal-date ties. Explain the
order beside the totals. No assignment form is required. A future version may add
manual priorities if needed.

```text
available for reserves = max(0, recorded savings − protected savings floor)
set aside for each goal = min(goal target, unassigned available savings)
free savings = max(0, recorded savings − floor − total set aside)
still needed for each goal = target − set aside
```

The total assigned can never exceed the one available balance. Show a floor
shortfall separately if savings is below the protected buffer. Lowering a balance
can reduce the amount assigned to later goals, but never lowers a goal's target.
Label the assignment as an earmark based on a manual balance, not a verified
transfer. Do not count forecast contributions as already set aside.

For example, with a recorded balance of **$8,000**, no protected floor, and these
illustrative goals:

| Reserve | Target date | Target | Set aside now | Still needed |
| --- | --- | ---: | ---: | ---: |
| Winter tax | February 15, 2027 | $3,000 | $3,000 | $0 |
| Summer tax | July 15, 2027 | $6,000 | $5,000 | $1,000 |
| Fall vacation | October 1, 2027 | $2,400 | $0 | $2,400 |

All $8,000 is assigned once. The summary shows **$8,000 set aside**, **$3,400 still
needed**, and **$0 free savings**. Updating savings recalculates these assignments;
it does not invent another $8,000 for each reserve.

## Funding pace and deadlines

Keep **Set aside now** separate from **Projected by deadline**. The first uses the
recorded balance; the second is a conditional plan for future saving.

- For a linked annual expense, reuse its existing monthly budget allocation and
  scheduled changes. If that pace will not reach the target by the first due date,
  show a catch-up amount. Starting midyear must not imply a full year's funding
  has happened. Do not automatically increase the budget expense to catch up.
- For a manual goal, calculate a suggested monthly contribution from its remaining
  need and contribution dates before the deadline. Default contributions to the
  first of each future month, strictly before the target date. Show the first
  contribution date and count; do not assume today's opening balance already
  includes a future transfer. Round up in minor units and cap the last contribution
  at the remaining need. With no contribution dates left, show **Needed now**.
- In the shared projection, add all planned contributions once to the pool and
  deduct each planned payment once at its due date. At every date check the
  cumulative amount due against the same pool, including all goals due that day.
  Contributions are assumptions, not confirmed deposits; check them against the
  existing forecast room and flag missing income or overcommitted budget room.
- Track the dated funding plan separately from observations. Refreshing the balance
  must not silently reset an overdue milestone or deadline. Recalculate remaining
  need and offer a revised contribution plan explicitly when the goal is behind.

Use four understandable statuses: **Funded** (assigned amount reaches target),
**On track if planned contributions arrive** (projection covers the deadline),
**Needs attention** (shortfall, insufficient budget room, or overdue unpaid goal),
and **Update savings** (missing/stale balance). Show the balance date, projected
shortfall, and next action. If an older balance suggests a funded goal, qualify it
with **Update savings**. Never present a projection as cash already available.

## Count each expense once

Linked taxes retain their existing annual expense and monthly distribution.
Creating a reserve only tracks earmarked savings. It creates no second payable,
transaction, payment, or forecast deduction. At payment time, reuse the existing
cash projection rule that replaces monthly allocations with the dated annual
payment. Reuse the recurring schedule's amount logic, including overrides and
rounding, instead of separately dividing amounts in the UI.

A manual vacation reserve tracks a goal without automatically creating a forecast
expense. In the same reserve editor, show **Include expense in budget** and link
an existing one-time purchase or create its single purchase record when requested.
The user enters the amount/date once; linked edits are synchronized atomically.
Until included, show **Not yet in budget**, include the goal in reserve coverage
checks, and label the main budget projection's omission. The reserve projection
includes that payment once and shows that planned contributions compete for budget
room. Once included, use the purchase's existing expense once rather than also
subtracting the reserve target. Internal purchase records do not require a second
planner workflow.

Reserve earmarks must also be deducted when the planner or advisor reports savings
available for an *unrelated* new purchase. Reuse the full savings balance for cash
projections that already include those same reserve payments; subtracting both
the earmark and its payment there would double-count the expense.

## Annual cycles, changes, and payments

An annual-linked goal follows the next unpaid occurrence. Use the schedule's
start/end dates and effective amount for that occurrence; never infer that an
overdue bill has been paid. Prevent duplicate tracking of the same occurrence.
Group all payments on one date for coverage checks. If an amount/date changes,
show the update and recalculate remaining need, without rewriting completed cycles.
Deleting a source keeps the goal and last known amount/date for explicit review.

At payment, use the existing bill payment action for a linked goal; for a manual
goal, use **Mark spent**. Offer **Update savings after payment** in the same flow.
Require a dated post-payment balance to finalize releasing the earmark and, for
an annual goal, starting the next cycle. If the balance is not available, keep a
**Payment recorded · update savings** state and hold its earmark so the old balance
cannot suddenly become free cash. Recording payment status is not a bank debit;
do not decrement a manually entered post-payment balance again. Multiple payments
can share one post-payment balance update, without making the user date it tomorrow.

## One planning flow, from research to reserve

Combine vacation and one-time purchase planning with reserves. The proposed main
screen is **Plans & reserves**, replacing the separate purchase planning journey.
Keep the useful current-budget projection and monthly bill scenarios as a
**Budget impact** view; a recurring payment is still a recurring expense rather
than a savings reserve.

The ordinary flow is:

1. **Explore** in the advisor: “Plan a fall vacation” or “Compare replacement
   laptops.” A short task selector offers **Understand spending**, **Explore a
   plan**, and **Review a reserve**, defaulting to automatic selection. Research
   remains optional, public terms remain previewed/approved, and only supported
   findings receive source links. The advisor asks for the missing details that
   affect the estimate, rather than showing every planning control at once.
2. Show a proposed plan card with a name, estimated amount or range, target date,
   itemized assumptions, sources/retrieval dates, and any uncertain costs. This
   is still a conversation: no reserve, forecast expense, or payment is created.
3. When requested, **Review & add reserve** opens one short form. Select one exact
   target from any estimate range, confirm the date, use the existing `savings`
   source, and optionally include its expense in the budget. The app previews
   set-aside funds, monthly pace, and effects on other reserves using Python.
4. **Save reserve** persists the reviewed plan. The local model remains read-only;
   it proposes fields, and the app validates and saves the user's reviewed values.
   Adding the linked expense and reserve is atomic and idempotent. Retrying cannot
   create two vacation expenses or earmarks. Returning later opens the same card
   to edit, research again, or view progress.

No separate “trip funds,” savings baseline, or monthly buffer fields in chat when
the saved savings/floor and reserve plan already supply them. The advisor can
discuss a plan without savings configured, but must not label it funded. Existing
draft purchases can be adopted into reserves; retain their inclusion state and
source identity, rather than re-creating them. Researching an active reserve
proposes changes for review, never silently changes its target or due date.

The current public research helper is tailored to travel. Product planning will
need a separate validated public-topic shape (product type, requirements, region,
and currency), plus the same preview/consent and source handling. Do not derive
search terms from private budget context or silently route a purchase through
travel's destination/date requirements. Current prices and availability need
dated sources; an unresearched estimate remains visibly provisional.

Named yearly income estimates can contribute to a conditional funding forecast
when included. They never increase **Set aside now**, which uses recorded savings.
Their monthly allocation is a budgeting assumption, so unknown or delayed receipt
timing must be visible before claiming a goal can be funded by its deadline.

## Advisor routing: rules first, measurable classification later

Current code builds one read-only financial snapshot for every question and adds
short prompt sections: forecast comparison when present, transaction evidence when
present, savings/bill rules when a Python projection exists, travel rules from
keyword matches or an approved research request, and memory rules when approved
notes were recalled. Travel matching inspects user history and the selected
purchase name. Separately, a regular expression can infer a simple monthly bill
from a question. There is no trained intent classifier or separate prompt model.

Use an explicit task selection plus a small deterministic, multi-label router for
the redesigned flow. Tasks can overlap: a vacation reserve can need research,
spending context, and a funding projection in the same answer. Active reserve ID,
selected scenario, and user choice are stronger evidence than a keyword in an old
chat turn. Route to structured calculations before selecting prompt sections;
keep common accounting/privacy rules in every mode. Show the interpreted task
and allow correction without discarding the conversation. Ambiguous questions get
a short clarification, never a silent write or automatic public search.

Start with tested examples: savings advice after a prior cut; a tax reserve versus
a question about tax law; a vacation without dates; a non-travel purchase; “what
about next month?” for the active reserve; and “how has dining changed?” after a
travel discussion. Keep earlier travel messages from permanently selecting travel
mode when the current task has changed.

A second generative model adds latency and another failure point without yet
showing a benefit for these few tasks. Add a local classifier only if a labelled
set of real routing failures shows that rules/user selection are insufficient.
Evaluate mixed-intent recall, incorrect routing, uncertainty, and latency. Any
classifier returns bounded labels and confidence only; it receives no authority
to save a reserve or grant research consent. This is a proposal, not a routing
change in the current application.

## Delivery plan

1. Unify Savings editing and observations: one actual dated balance used everywhere,
   keeping future scenario inputs separate. Preserve existing month-opening
   semantics for projections; do not reinterpret a midmonth observation as the
   month's opening balance or rerun an entire month's expenses against it.
2. Add individual reserve goals with source, target/date, optional recurring or
   purchase link, cycle/payment state, and a dated contribution plan. Keep savings
   assignments derived from the shared pool rather than storing independent balances.
3. Replace the combined reserve form with the list, short add flow, totals, and
   contextual reminders. Retain the existing alert toggle; replace checkpoint
   jargon with dated balance freshness and upcoming deadlines.
4. Integrate shared coverage and free-savings amounts with Overview, Purchase
   planner, and the advisor. Consolidate the planning controls into Plans & reserves
   and add the reviewed research-to-reserve handoff. Keep observed progress and
   conditional plans distinct.
5. Migrate safely: preserve observations and the old plan for history, propose
   individual linked goals from its schedules, and show them for review. Do not
   copy the old baseline into savings or each new reserve. Keep the old checker
   active until adoption, then disable it to avoid duplicate alerts.

Acceptance checks: the three-goal example above; balance decreases; floor breaches;
missing/stale balances; midyear setup; equal-date goals; no future contribution
dates; changed/removed schedules; refund/corrected balances; two payments followed
by one balance update; annual rollover; and no duplicate annual or vacation costs
in forecasts, projections, or the advisor's available savings.
