# Argo operations

Abacus runs as one UID-1000 API worker with its bundled Babar stdio child in
namespace `abacus`. Access it at http://127.0.0.1:8017 through the managed loopback
forward. PostgreSQL and Ollama remain host services. The chart explicitly sets
`OLLAMA_HOST_GATEWAY` to its private host gateway; `OLLAMA_URL` must use that exact
address or a loopback host. Native setups remain loopback-only by default.
Redirects and environment proxies remain disabled for model requests. Financial schema is 0020;
Babar schema is 3. Database placement is configured independently of the image.

From `local-agent-environment`:

```sh
.venv/bin/python scripts/abacus_gitops.py status
.venv/bin/python scripts/abacus_gitops.py check-images
.venv/bin/python scripts/abacus_gitops.py recover
.venv/bin/python scripts/abacus_gitops.py restart
```

Restart performs controlled scale-to-zero, waits for old pods/children to exit,
then starts one replacement and reconnects forwarding. Interrupted imports may
need retry. It preserves other applications and their forwards. Never force-delete
an Abacus pod to bypass a process shutdown problem.

## Releases

Commit Babar changes first, then Abacus changes. From Abacus:

```sh
python3 scripts/publish_images.py --babar-revision FULL_BABAR_COMMIT
```

The publisher builds committed archives; local edits are excluded. Publish source
commits to their repositories. From `agent-platform-gitops`:

```sh
python3 scripts/promote.py --environment local --release ../abacus/build/release.json
```

Review, commit and push the values/release files to `main`. Argo reconciles the
pinned digest with `Recreate`. Bundled Babar provenance is mandatory. There are
no migration hooks. Stop the application under its transition owner before
required financial migrations or Babar schema/grant maintenance. Use
`ABACUS_ADMIN_DATABASE_URL` for Alembic/advisor maintenance and independent
administrator `PG*` settings for Babar; administrator credentials never belong in
runtime Secrets. Do not run a second server against live databases as a preview.

## Secrets and endpoints

Private preparation input is stored under
`local-agent-environment/.local/abacus/prepare.json`, mode 0600. Its `environment`
object contains runtime values; `memory_profile` names a separate container-ready
profile. Optional `files` maps simple filenames to certificate/key sources.
Container endpoints must be explicit: arbitrary remote hostnames are never
rewritten. Certificate paths in URLs/profiles refer to `/run/abacus/<filename>`.
The chart copies private files into memory-backed storage as UID 1000, mode 0600.

After changing private configuration, from `local-agent-environment`:

```sh
.venv/bin/python scripts/abacus_gitops.py prepare --config .local/abacus/prepare.json
.venv/bin/python scripts/abacus_gitops.py restart
```

The restart refreshes copied Secret files. Host-local profiles explicitly use
`sslmode=disable`; remote production endpoints should use `verify-full` with the
correct CA and hostname. Models are pinned, offline, and mounted read-only.
Missing models cause unavailable memory; runtime does not download replacements.

## Ownership and rollback

`.local/abacus-owner` is independent of Lalaland/Lassy ownership. `gitops` permits
recovery and restart; `transition` reports an incomplete operation without starting
another writer. Unadopted installations are skipped by shared recovery. The current
controller provides no native activation or rollback commands.

For image rollback, promote a previous compatible digest/release record through
GitOps. If schemas changed, review compatibility before changing images. Recovery
never restores backups or rolls back schemas automatically.

Native macOS service support is archived in
[v0.2.0](https://github.com/jbromfld/abacus/tree/v0.2.0). Any historical native
rollback requires stopping Argo reconciliation, scaling to zero, waiting for all
pods/children to exit, stopping the Abacus forward, and reviewing financial and
Babar schema compatibility before using the tagged checkout. Never run both
owners against the same live databases or restore old data over newer writes.

Version 0.3.0 retains foreground development, setup, API generation, training
export, and performance/model checks. The native service controller, runner and
service-specific tests have been removed.
