# AGENTS.md

## Purpose
This repository follows an upstream-first fork workflow.
The goal is to keep upstream compatibility while preserving local custom features via extension modules.

## Branch Model
- `upstream-mirror`: pure mirror of `upstream/main`, no local customization commits.
- `main`: business branch for this fork.
- Integration branches: `codex/sync-YYYYMMDD` for each upstream merge round.

## Non-Negotiable Rules
- Do not carry long-term custom behavior by overwriting upstream core files.
- Keep core patch budget minimal; prefer only `main.py` hook integration for long-term stability.
- Keep local behavior in extension layer under `app/fork_ext/` and `fork_overlays/`.
- Keep compatibility endpoints and existing public paths available.

## Extension Architecture
- Hook entrypoint: `main.py`
  - `apply_runtime_patches()`
  - `register_pre_routes(app)`
  - register upstream core routers/static
  - `register_post_routes(app)`
- Extension env: `FORK_EXTENSIONS`
  - default modules:
    - `app.fork_ext.image_edit_ext`
    - `app.fork_ext.video_compat_ext`
    - `app.fork_ext.image_compat_ext`
    - `app.fork_ext.video_runtime_ext`
    - `app.fork_ext.frontend_overlay_ext`

## Required Compatibility Surface
- Video compatibility:
  - `/v1/videos`
  - `/v1/video/create`
  - `/v1/videos/{id}`
  - `/v1/video/generations`
  - `/v1/video/content/{id}`
- Image edit public flow:
  - `/v1/public/image-edit/start`
  - `/v1/public/image-edit/sse`
  - `/v1/public/image-edit/stop`
  - `/image-edit`
- Frontend/static overlay paths:
  - `/static/common/html/public-header.html`
  - `/static/common/js/public-header.js`
  - `/static/public/js/video.js`
  - `/static/public/css/video.css`
  - `/static/public/pages/image-edit.html`
  - `/static/public/js/image-edit.js`
  - `/static/public/css/image-edit.css`

## Frontend Overlay Guardrails
- Keep `/image-edit` entry visible in public header for `chat/imagine/video/voice` pages.
- For header/navigation changes, prefer overlay files under `fork_overlays/static/common/` instead of upstream static files.
- Keep a JS fallback that injects `/image-edit` nav when header template drift or cache causes missing entry.
- When changing shared header JS, bump `public-header.js?v=` on public pages to force cache refresh.

## Upstream Sync Workflow
1. Fetch remotes:
   - `git fetch origin upstream --prune`
2. Generate upstream risk report:
   - `python scripts/sync_upstream.py --base-ref main --upstream-ref upstream/main --report-path reports/upstream-watch-local.md`
3. Create integration branch from `main`:
   - `git checkout -b codex/sync-YYYYMMDD main`
4. Merge upstream:
   - `git merge --no-ff upstream/main`
5. Resolve conflicts with upstream-first policy:
   - preserve upstream core behavior
   - replay/keep fork behavior via extension layer
6. Verify:
   - `python -m compileall app scripts`
   - `python scripts/check_touch_budget.py`
   - route smoke checks via `uv run python -c ...` when needed
7. Commit and push integration branch, then create PR to `main`.

## Deployment Policy
- Default deployment uses fork image build in `docker-compose.yml`.
- Keep only data/log mounts as regular practice.
- `docker-compose.legacy-override.yml` is emergency rollback only, not standard release path.

## CI Policy
- Upstream watch: `.github/workflows/upstream-watch.yml`
- Touch budget gate: `.github/workflows/touch-budget.yml`
- Allowlist file: `.github/touch-budget-allowlist.txt`

## Collaboration Preference
- Always communicate with users in friendly Chinese.
- Unless explicitly requested, do not auto-push.
- Default delivery: local commit + clear summary + suggested push/PR command.
