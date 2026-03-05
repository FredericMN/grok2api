# Fork Upstream Sync Workflow

This repository uses an upstream-first sync model designed for long-term compatibility.

## Branch model

- `upstream-mirror`: pure mirror of `upstream/main` (no local custom code).
- `main`: fork business branch with extension-layer customizations.

## Sync procedure

1. Update mirror branch:
   - `git checkout upstream-mirror`
   - `git fetch upstream --prune`
   - `git reset --hard upstream/main`
2. Create integration branch from mirror:
   - `git checkout -b sync-upstream-<date> upstream-mirror`
3. Re-apply only extension-layer commits:
   - `main.py` extension hook commit
   - `app/fork_ext/**`
   - `fork_overlays/**`
4. Run checks:
   - `python scripts/sync_upstream.py`
   - API compatibility tests
5. Merge integration branch into `main`.

## Notes

- Do not use long-term full-file override mounts for app code.
- Keep core touch budget minimal and enforced by CI.
- Use `FORK_EXTENSIONS` to enable/disable local custom modules.
