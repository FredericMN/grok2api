# Grok2API Fork Customizations

> Fork: [FredericMN/grok2api](https://github.com/FredericMN/grok2api)
> Upstream: [chenyme/grok2api](https://github.com/chenyme/grok2api)
> Model: upstream-first + extension layer
> Updated: 2026-03-05

## 1) Design Goal

This fork follows an "upstream-first" strategy:

- Keep upstream code as the integration baseline.
- Keep core patch budget minimal (mainly `main.py` extension hook).
- Move local custom behavior to extension modules.
- Preserve local API compatibility and UI entrances.

## 2) Runtime Extension Architecture

Core hook entry is in `main.py`:

- `apply_runtime_patches()`
- `register_pre_routes(app)`
- upstream core router/static mounts
- `register_post_routes(app)`

Extension loading is controlled by env var `FORK_EXTENSIONS`.

Default value:

```env
FORK_EXTENSIONS=app.fork_ext.image_edit_ext,app.fork_ext.video_compat_ext,app.fork_ext.image_compat_ext,app.fork_ext.video_runtime_ext,app.fork_ext.frontend_overlay_ext
```

## 3) Local Capability Mapping

### `app.fork_ext.image_edit_ext`

- Preserves `/v1/public/image-edit/start`
- Preserves `/v1/public/image-edit/sse`
- Preserves `/v1/public/image-edit/stop`
- Preserves `/image-edit` page route

Code source:

- `app_public_api_image_edit.py`
- `fork_overlays/static/public/pages/image-edit.html`

### `app.fork_ext.video_compat_ext`

Dual-track video compatibility endpoints:

- `/v1/videos`
- `/v1/video/create`
- `/v1/videos/{id}`
- `/v1/video/generations`
- `/v1/video/content/{id}`

Code source:

- `app_api_v1_video.py`

### `app.fork_ext.image_compat_ext`

- Non-standard `size` compatibility mapping.
- Multipart `image[]` compatibility for `/v1/images/edits`.
- Edit size/aspect passthrough to image-edit runtime.

### `app.fork_ext.video_runtime_ext`

- Video token reuse avoidance under concurrency.
- "No video content" warning/failure protection.

### `app.fork_ext.frontend_overlay_ext`

Overlay static resources without modifying upstream static files:

- `/static/common/html/public-header.html`
- `/static/public/js/video.js`
- `/static/public/css/video.css`
- `/static/public/pages/image-edit.html`
- `/static/public/js/image-edit.js`
- `/static/public/css/image-edit.css`

Overlay files are in `fork_overlays/static/...`.

## 4) Deployment Model

Primary deployment is fork-image build (`docker-compose.yml`):

- `build: .` + fork image tag
- keep only data/log mounts
- no long-term app-code override mounts

Emergency rollback only:

- `docker-compose.legacy-override.yml`
- legacy file overlay strategy (not for regular release)

## 5) Upstream Sync Workflow

See `FORK_WORKFLOW.md`.

Branch model:

- `upstream-mirror`: pure upstream mirror branch
- `main`: fork business branch

Recommended sync loop:

1. Refresh `upstream-mirror` from `upstream/main`.
2. Create integration branch from `upstream-mirror`.
3. Replay extension-layer commits + `main.py` hook commit.
4. Run compatibility checks before merge.

## 6) CI Automation

### Upstream watch

- Workflow: `.github/workflows/upstream-watch.yml`
- Script: `scripts/sync_upstream.py`
- Output: merge-tree conflict and key diff report (artifact + summary)
- No auto-merge and no auto-PR creation

### Touch budget gate

- Workflow: `.github/workflows/touch-budget.yml`
- Script: `scripts/check_touch_budget.py`
- Allowlist: `.github/touch-budget-allowlist.txt`
- Blocks PRs that touch non-budget core paths

## 7) API Compatibility Commitments

This fork keeps existing external compatibility contracts:

- Legacy and upstream endpoints are both available.
- `/video`, `/image-edit`, `/v1/public/*` remain reachable.
- Auth key behavior is unchanged.
