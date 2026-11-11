# Unified Planning

Implemented with migration 0016. This replaces the earlier reserve-design proposal.

Planning is the single page for tax, vacation, and purchase goals. A goal has a
name, positive amount, exact target date, and optional planning category. Amount
and savings sliders retain exact entry for precision. Settings starts with tax,
vacation, and purchase categories; these labels are independent of transaction
categories so existing imported classification is preserved.

The page shows shared savings, total planned and unassigned savings. Funds are
earmarked by earliest deadline after protecting the savings floor. Each goal has
Edit, Discuss, and permanent Delete actions. Annual bills link to goals whose amount and dated deadline follow the bill.
The conditional running cash projection counts each linked bill/goal once and is
shared by Planning, Overview, Bigger picture, and advisor context. A separate
funding-coverage check compares each tracked annual bill with its earmark plus its
own budgeted future contributions. It warns before savings becomes negative and
does not assume other categories will cover the gap. Recorded savings excludes
projected contributions; updating the absolute balance replaces it. No extra
contribution ledger or duplicated expense is introduced.

The advisor has one chat card. Web search controls and explicit public-query
approval live beside the composer. Discuss passes a saved goal ID, never a copied
preview or stale dropdown selection. Add to Planning creates a reviewable local
model suggestion; Save plan performs the actual write.

Migration 0016 deliberately clears obsolete purchases, bill estimates and combined
reserve targets. No old plan migration or compatibility UI is provided. Imported
expenses, import provenance, accounts, categories, recurring bills, amount changes,
payment history, savings, and annual income are retained. The reset runs once;
subsequent upgrades retain new Planning goals.

See the [Planning workflow](user-guide.md#planning) and [API](api.md#planning).
