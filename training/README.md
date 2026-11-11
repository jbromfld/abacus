# Local transaction classification

[Documentation index](../docs/README.md) · [Payee workflows](../docs/user-guide.md#payee-classification) · [Operations](../docs/operations.md)

Abacus now uses a fast baseline: **reviewed payee variant + transaction type → category**, with normalized-group matching for new variants.
There is no training job or LLM request for a known payee. Mapping a CSV applies
remembered categories automatically. The review screen also offers **Apply
remembered payees** for imports created before a label was learned.

Imported descriptions containing `PAYMENT` (case-insensitive substring) default to
`payment` before payee rules. CSV categorization does not use a model. These rows do not count
as spending and need no category. Review can explicitly override unusual matches;
retries preserve that override. The same default applies after PDF extraction.

## What learns today

- Saving a manual transaction or an edited transaction remembers its category.
- Committing selected reviewed import rows remembers their categories atomically
  with the transactions. Saving a review alone does not train anything.
- Specific variant keys retain case-folded, whitespace-normalized descriptions.
  A second key ignores explicit `#store` markers, leading years or numeric dates,
  apostrophes, and punctuation differences. This groups the Panera store-number
  examples and Holiday Hustle year variants. Unmarked brand numbers such as
  7-Eleven, Route 66, and Studio 54 remain significant. Descriptions longer than
  the specific-key limit after Unicode normalization are not remembered.
- Exact remembered variants take priority. A new normalized variant receives a
  category only when all remembered variants in its group agree. Conflicting
  groups abstain; existing specific labels are retained. Existing memory works
  without migration. This is deterministic text normalization, not NLP stemming
  or lemmatization; original descriptions, dates, and exact CSV deduplication are
  untouched.
- Rules are shared across card accounts but keyed separately for purchases,
  refunds, and fees. A category never changes the transaction's type or amount.
- A later explicit label replaces the remembered category. Conflicting categories
  for one payee/type within a single commit remove the rule and require review.
- Existing saved transactions seed rules during migration only when their
  payee/type has one unambiguous category.
- Settings lists approved groups and individual payees so you can correct or forget a rule. Forgetting
  a rule does not rewrite prior transactions. Undo/deleting an import removes
  its transactions; remembered labels persist until forgotten in Settings.
- Rules fill empty categories; they do not overwrite an existing review edit.
  Clear a category and apply rules again if you want a remembered suggestion.

CSV categorization never calls Ollama. New payees are labeled manually and then
remembered. Existing review labels are preserved when applying rules. Optional
PDF extraction still uses the local model to propose transaction rows and types;
category suggestions come from memory and manual review only. The optional Budget
advisor is separate from statement classification.

## Approved merchant groups and local review

Merchant-specific JSON normalization and automatic fuzzy category assignment were
replaced in migration 0017. There is no `payee_matching.json` to maintain. Existing
exact rules and transaction categories are retained. Generic normalization still
handles Unicode/case/whitespace, punctuation, explicit #store metadata and leading
years/dates; meaningful unmarked numbers remain significant.

The explicit **Review similar payees** action starts one background local-model
job. Generic token/prefix overlap finds candidates only, never categorizes them.
Batches contain at most 24 aliases, overlap to bridge boundaries, and keep kinds
separate. Approved group members are included when proposing an extension. Reviews
support up to 2,000 remembered variants and run independently of import jobs.

Only names, kinds, current category labels/IDs and existing group names enter the
model. Compact per-batch member IDs reduce token usage. Structured output is
validated against exactly those IDs and categories. Unknown IDs, repeated members,
extra executable/regex fields, and mixed kinds fail the review without changing
memory. The model suggests identities; the user approves membership and any category
changes separately. Model confidence is not treated as a calibrated probability.

`payee_groups` stores canonical names and kinds. Existing `payee_rules` keep exact
aliases/categories plus nullable group membership. `payee_reviews` retains the
preview snapshot and proposed/applied decisions. Applying selected changes locks
and checks current rows against that snapshot before writing all approved groups
in one transaction. Replays are idempotent. Individual category corrections keep
priority and may make a group's canonical-name match ambiguous; ambiguous matches
abstain. Saved transactions and import provenance are not rewritten.

The advisor's aggregate display uses approved exact aliases by kind. Its restricted
login can SELECT groups and remembered rules, but cannot access private review jobs
or approve changes. Runtime matching remains model-free. New unknown variants need
manual review; approved groups do not authorize arbitrary regex/prefix matching.

Cancel stops future batches and discards proposals. Restart marks unfinished jobs
interrupted without resuming them automatically. Rename/Ungroup operate on groups;
Ungroup preserves aliases and their individual categories. A new review can be
started after a cancelled, failed, interrupted or completed job.

## Export reviewed examples

```sh
uv run python scripts/export_training_data.py --output .training/examples.jsonl
```

This explicitly creates a local JSONL file, one saved labeled transaction per
line: `description`, `payee`, `kind`, `category_id`, and `date`. No statements,
amounts, account IDs, or credentials are exported. It includes accepted imports
and manual entries, not unsaved review/model proposals. It refuses to overwrite
an existing export. `.training/` is Git-ignored; the descriptions are still
private financial data. Nothing is sent to a service.

## Future training stub

`backend/abacus/classification.py::predict_unknown(description, kind)` is an
intentional abstaining stub: it returns `None`. It is not currently called by
the import pipeline. There is **no trained classifier**. Normalized grouping and conservative Python
string-similarity matching are active; neither requires a training job.

Suggested next implementation:

1. Inspect and clean exported labels; omit ambiguous/general-purpose payees
   whose category depends on what was bought. Keep purchases/refunds/fees
   separate or include transaction type as a feature.
2. Train a small character n-gram text classifier locally. A TF-IDF feature
   extractor plus a linear classifier is a reasonable starting experiment.
   This is optional future work, not a required runtime dependency.
3. Evaluate on both a chronological holdout (future statements) and a holdout
   grouped by normalized payee (unseen merchants). Random transaction splits
   alone overestimate performance because recurring merchants leak across sets.
4. Record per-category precision/recall, coverage, sample counts, and confusion
   pairs. Calibrate a confidence threshold using held-out data; abstain when
   uncertain. Do not invent a confidence score from an uncalibrated margin.
5. Persist a versioned local artifact plus category IDs, normalization version,
   training-data fingerprint, and validation report. Load only artifacts you
   trained yourself. Invalidate/retrain when categories or normalization change.
6. Implement `predict_unknown` to return an existing category ID or `None`.
   Integrate after existing deterministic memory/similarity rules, leaving unknowns for manual review. Validate the
   returned ID, mark the row's classification source, and retain manual review.
   Missing/incompatible artifacts must abstain without blocking imports.
7. Add offline tests for held-out merchants, low-confidence abstention, changed
   categories, corrupt/missing artifacts, and strict precedence: review edits →
   specific payee rules → unambiguous normalized groups → conservative similarity → trained suggestions → manual labeling.

Training/prediction must stay local. Never treat a model proposal as a reviewed
training label until the user explicitly saves its transaction.
