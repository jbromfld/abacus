# Optional local advisor memory

Memora retains **notes you approve**, not full conversations. A later answer can
recall “On November 8, I intended to cut discretionary spending by USD 50/month.”
That is an intention, not evidence it happened. Notes never change forecasts,
transactions, savings balances, or plans. Formal goal tracking is outside v1.

## Setup

1. In the sibling Babar repository, run `uv sync --locked --extra dev`. Memora runs
   in Babar's separate environment; Abacus installs only the MCP client, without
   the embedding/PyTorch dependencies. Babar has no cloud/orchestration providers.
2. Ensure local PostgreSQL has pgvector available. Provisioning enables it only in
   the new memory database. The admin login needs database/role creation and
   extension-install permissions.
3. Make the pinned embedding weights available in advance: default
   `sentence-transformers/all-MiniLM-L6-v2`, revision
   `c9745ed1d9f207416be6d2e6f8de32d1f16199bf`, dimension 384. If absent, acquire
   that exact revision manually using your model-management tools. Runtime and
   setup never download models, use cloud embeddings, or enable remote tracing.
4. In Abacus run `uv run --no-sync python scripts/setup_memory.py`. Use
   `--babar /absolute/path/to/babar` for a different checkout. The helper creates
   `abacus_memory` as a separate database with a managed, restricted runtime login.
   It writes owner-only `.memora-abacus.json` in Babar and atomically saves local
   executable/config paths in Abacus's ignored `.env`, preserving unrelated values.
5. Apply migration 0013 and rebuild/restart normally. Enable **optional local
   advisor memory (Memora)** in Settings, save, and check the memory connection.
   The toggle defaults **off**. Provisioning does not enable it.

`MEMORA_PYTHON` is an absolute venv Python executable, not a shell command;
`MEMORA_CONFIG` is an absolute runtime JSON path. `MEMORA_TIMEOUT_SECONDS` defaults
to 30 (1–120). The MCP SDK launches one persistent local stdio subprocess and
cleans it up at shutdown/disable; no additional HTTP port is opened. Abacus starts
normally without Memora installed. Disabling retains saved notes.

## Remember, recall, and manage

- Choose **Remember this** after an exchange. A separate local model call drafts
  a note. Review its wording, type, date, retained source excerpt, and topic cues.
  Only **Save memory** persists it. A recommendation is not an accepted intention
  unless you approve that wording. Failed drafting allows manual entry; failed
  saves preserve your edited draft.
- **Check for similar notes** offers candidates. Explicitly choose **Replace** to
  revise one, or save a separate note. Similarity never merges goals automatically.
- Settings supports manual notes, editing, revision history, completed/abandoned
  status, and confirmed forgetting. Stale revisions return a conflict.
- Each question retrieves at most three active notes, using the question and latest
  user follow-up, within a 1,500-character serialized context budget. Ordinary
  answers do not run another generative extraction step. **Memory used for this
  answer** shows dates and `[M1]`, `[M2]` references supplied to the model.
- Completed/abandoned notes remain inspectable but are excluded from recall. There
  is no automatic expiration. Full chat stays ephemeral; new conversation, reload,
  or restart clears chat but preserves approved notes.

## Privacy and permissions

Financial snapshots still use the existing `abacus_advisor` SELECT allowlist and
read-only repeatable-read transaction. Its grants are unchanged. The model gets
quoted notes, not MCP tools, SQL access, credentials, or permission to save memory.

The memory runtime login has CRUD only on note/revision tables and SELECT on
model/migration metadata. It owns no objects, cannot create schemas/tables or
grant memberships, and has no access to budget tables. The service fixes its
namespace in configuration and scopes every search/read/write/UUID lookup.
Abacus uses the `abacus-advisor` namespace; other consumers use their own profiles
and namespaces. Its dedicated memory database is separate from financial storage.

The child receives only its runtime file/offline flags plus the SDK's OS environment
allowlist. No financial database credentials, Brave key, admin password, cloud
configuration, or tracing settings are passed. Babar is an application-independent
memory service without workflow agents. Errors omit private text and connection details;
child stderr is not forwarded into app logs.

Memories, excerpts, drafts, and retrieval queries never enter Brave. Research still
accepts only the separately entered, previewed, approved public topic. No automatic
model downloads or cloud fallback exist.

**MCP is not an OS sandbox.** The child runs with your OS user's file/network access.
The Abacus backend still holds its normal writable credentials. These restrictions
protect application capabilities and database grants, not a compromised backend
or OS account.

## Forgetting and failures

**Forget note → Confirm forget** deletes the note, all revisions, source excerpts,
and embedding atomically. Updates/forgetting invalidate pending answers and clear
the current advisor conversation/context. Other open tabs are notified without
persisting private content. Stale API clients receive 409 and must start a new
conversation; a restart also changes the memory generation ID.

There is no persistent recall cache. Older database/filesystem backups and exports
can still retain forgotten notes; manage those separately.

If Memora fails, chat continues with a warning and no recalled notes. A failed save
never claims success. Check configuration ownership/permissions (`chmod 600`), local
PostgreSQL, migrations, the Babar environment, and cached pinned weights. Broken
transport connections are recreated on the next attempt.

An unavailable-recall warning belongs to the answer that omitted memory; it is not
a live connection indicator. In **Settings → Advisor memory**, use **Refresh memory**
to check the current connection, then ask the question again. A successful status
check also verifies the cached embedding model and memory database without changing
saved notes. A later successful connection does not retroactively add recalled
notes to an older answer.

## Maintenance, recovery, and backups

Abacus's restart script maintains its own migrations/advisor permissions. Memora
is independently versioned: sync Babar and rerun `setup_memory.py` when its schema
or permission allowlist changes. Setup preserves existing passwords and refuses
unrelated roles. Use `--rotate-password` explicitly to recover a managed role
with lost/unusable credentials; ordinary setup never rotates.

Changing model identity/revision/dimensions requires explicit reindexing: disable
memory, back up the database/runtime file, edit the owner-only model configuration,
and follow Babar's `python -m memora.reindex` instructions with separate admin
credentials. Embeddings and identity change in one transaction; failure preserves
the old data. Runtime never re-embeds automatically.

Back up the memory database separately, using PostgreSQL tools with interactive
credentials or an owner-only `.pgpass`, not password-bearing command lines:

```sh
pg_dump --host=127.0.0.1 --username=YOUR_ADMIN --format=custom abacus_memory > memory.dump
# Restore into a separately created empty database:
pg_restore --host=127.0.0.1 --username=YOUR_ADMIN --no-owner --no-acl --dbname=RESTORED_MEMORY memory.dump
```

Preserve the runtime model identity/cache. After restoration to a new database,
provision a **new runtime role**; managed markers bind to the original database OID.
Keep runtime files/dumps out of Git. Do not alter shared PUBLIC permissions to
make verification pass.

## Verification

Abacus tests cover bounded recall, drafts, unavailable services, explicit writes,
conflicts, forgetting during answers, stale history, Brave isolation, financial
read-only grants, and real subprocess lifecycle/environment isolation. Frontend
tests cover approval, failed-save retention, and confirmed forgetting. Babar's
synthetic PostgreSQL/stdio tests cover persistence, namespaces, lifecycle,
idempotency, revisions, permissions, pagination, redaction, and atomic reindexing.


## Optional dreaming

Dreaming defaults off. Upgrade Babar first by rerunning its setup (or
`uv run --no-sync python scripts/setup_memory.py`), which preserves its managed
password and existing notes while migrating memory storage to schema 2 and
refreshing grants. Apply Abacus migration 0020, rebuild, and restart normally.
Do not turn it on until memory status advertises `dreaming-v1`.

In Settings → Advisor memory → Memory dreaming, enable the toggle. Saving or
editing a note queues a pass after a 60-second debounce. “Dream now” queues one
immediate pass. Each pass considers at most five disjoint pairs drawn from 200
recent active notes. Interactive local-model calls get priority between groups;
a generation already in progress finishes before the next caller starts.

The local model has no tools or web access. Compatible same-kind notes can consolidate automatically when their combined
verbatim text fits 400 characters and amounts/periods/constraints agree. Conflicting
details, question-like/missing evidence, unsupported numbers,
and existing consolidated families go to review. This deliberately conservative
first policy treats model confidence as a suggestion, never authorization. Review
shows the proposed editable summary, originals, reasons and preserved facts;
choose “Approve consolidation” or “Keep separate.” New source revisions invalidate
stale proposals instead of silently overwriting them.

One active canonical memory is recalled. Sources retain their own dates, exact
text, excerpts and revisions; consolidation uses the earliest source date, not
today. Relevant dated source details fit within the existing 1,500-character
recall budget. A warning identifies omitted detail. Inspect retained sources when
reasoning about specific amounts, periods, or constraints.

Superseded records remain inspectable and cannot be edited. “Undo consolidation”
restores unchanged originals; an edited or subsequently consolidated result
requires manual review. Family-wide forgetting explicitly deletes source notes,
all their revisions/embeddings, and Babar's content-bearing consolidation history.
Abacus purges its pending/recent dreaming payloads before forwarding a forget
request, including uncertain failures. Older backups can still retain copies.

Jobs/proposals are persisted before external writes. On restart, operation keys
reconcile a possibly completed write before resuming. Turning dreaming off cancels
queued/review work and prevents later commits; stopping Abacus also prevents a
running model result from committing after shutdown. No dreaming pass recursively
schedules itself. Saving memories, consolidation, undo and forgetting invalidate
advisor context; the memory management panel notices background changes on its
next 15-second status refresh.

The example with specific Entertainment/Dining cuts and a later broader savings
question becomes a review item, retaining mortgage/car constraints and dated
amounts in the sources. Neither a question nor an advisor recommendation becomes
an accepted commitment or achieved savings automatically.
