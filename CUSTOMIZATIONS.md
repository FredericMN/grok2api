# Grok2API Fork 自定义改动文档

> **Fork 仓库**: [FredericMN/grok2api](https://github.com/FredericMN/grok2api)
> **上游仓库**: [chenyme/grok2api](https://github.com/chenyme/grok2api)
> **当前基线**: 上游 v1.5.3（commit `cbd1642`）
> **最后更新**: 2026-03-02

本文档记录了 fork 相对于上游的所有自定义改动，便于后续开发和合并上游更新。

---

## 部署方式

使用官方 Docker 镜像（`ghcr.io/chenyme/grok2api:latest`），通过 `docker-compose.yml` 中的 **volume mount** 将自定义文件覆盖进容器，无需重新构建镜像。

```
NAS 地址: DeepThink:8100
容器内端口: 8000
SSH: Frederic@DeepThink
SMB: Z:\ → \\DeepThink\personal_folder (映射到 /home/Frederic)
项目路径: /home/Frederic/grok2api
```

---

## 自定义文件总览

### 新建文件（6 个）

这些文件是我们独立新增的，不覆盖上游任何文件，**与上游零冲突**。

| 文件 | 容器路径 | 说明 |
|------|----------|------|
| `app_public_api_image_edit.py` | `/app/app_public_api_image_edit.py` | 图像编辑公共 API（session-based SSE） |
| `app/static/public/pages/image-edit.html` | `/app/app/static/public/pages/image-edit.html` | 图像编辑页面 HTML |
| `app/static/public/css/image-edit.css` | `/app/app/static/public/css/image-edit.css` | 图像编辑页面样式 |
| `app/static/public/js/image-edit.js` | `/app/app/static/public/js/image-edit.js` | 图像编辑前端逻辑 |
| `app_services_grok_services_video.py` | `/app/app/services/grok/services/video.py` | 视频服务修复版 |
| `app_api_v1_video.py` | `/app/app/api/v1/video.py` | 视频 API 修复版（含 SDK 端点） |

### 覆盖上游文件（5 个）

这些文件用 volume mount 整体替换上游同名文件，**上游更新时需要手动 diff + merge**。

| 文件 | 容器路径 | 风险 | 改动说明 |
|------|----------|------|----------|
| `main.py` | `/app/main.py` | **高** | 新增 image-edit 路由注册 + 页面路由 |
| `app/static/common/html/public-header.html` | 同路径 | 中 | 导航栏新增"Edit 图像编辑"链接 |
| `app/api/v1/image.py` | 同路径 | 中 | size 参数自动映射 + 修复 |
| `app/static/public/js/video.js` | 同路径 | 中 | 视频并发 bug 修复 |
| `app/static/public/css/video.css` | 同路径 | 低 | 视频样式微调 |

### 覆盖上游文件（通过重命名 mount）

| 本地文件名 | 容器路径 | 说明 |
|-----------|----------|------|
| `app/services/grok/services/image_edit.py` | 同路径 | 修复 `edit()` 缺少 `size` 参数 |

---

## 各改动详细说明

### 1. 图像编辑页面（Edit 图像编辑）

**Commit**: `ce6bd57`
**涉及文件**: 7 个（4 新建 + 3 修改）

#### 后端：`app_public_api_image_edit.py`

采用与 Video 页面一致的 session-based SSE 模式：

```
POST /v1/public/image-edit/start  → 创建 session，返回 task_id
GET  /v1/public/image-edit/sse    → SSE 流（task_id + public_key 认证）
POST /v1/public/image-edit/stop   → 停止并清理 session
```

**关键实现**：
- Session 管理：内存字典 + asyncio Lock，TTL 600s，上限 50 个
- 输入校验：MIME 白名单（png/jpg/webp）、base64 格式检查、单图 20MB 限制
- 调用链：`ImageEditService().edit(stream=True)` → 透传 SSE 流 → 追加 `data: [DONE]\n\n`
- Token 获取：`ModelService.pool_candidates_for_model("grok-imagine-1.0-edit")` → `["ssoBasic", "ssoSuper"]`

> **注意**：`ImageStreamProcessor` 在非 `chat_format` 模式下不会自动发送 `[DONE]`，因此后端必须手动追加。

#### 前端：`image-edit.html` + `.css` + `.js`

- IIFE 模式，`TaskContext` 类 + `taskRegistry` Map 管理并发任务
- 多图上传：拖拽 + 点击，最多 3 张，缩略图预览，`pendingReads` 计数器防异步竞争
- SSE 使用**命名事件**监听（与 Video 的无名事件不同）：
  ```javascript
  es.addEventListener('image_generation.partial_image', handler);  // 进度
  es.addEventListener('image_generation.completed', handler);      // 完成
  es.onmessage = handler;  // [DONE] 和 error
  ```
- 支持 n=1 或 n=2，`previewItems` Map 按 index 分配 gallery 卡片

#### 路由注册：`main.py` 改动

```python
# 新增 import
from fastapi.responses import FileResponse
from fastapi import HTTPException
from app.core.auth import is_public_enabled
from app_public_api_image_edit import router as image_edit_public_router

# 新增路由注册
app.include_router(image_edit_public_router, prefix="/v1/public")

# 新增页面路由
@app.get("/image-edit", include_in_schema=False)
async def public_image_edit():
    if not is_public_enabled():
        raise HTTPException(status_code=404, detail="Not Found")
    return FileResponse(APP_DIR / "static/public/pages/image-edit.html")
```

#### 导航栏：`public-header.html` 改动

在 Video 链接后新增：
```html
<a href="/image-edit" class="nav-link text-sm" data-nav="/image-edit">Edit 图像编辑</a>
```

---

### 2. 视频并发 bug 修复

**Commits**: `9099773`, `c358609`, `04ef2ad`

#### `video.js` 改动
- 引入 `TaskContext` 类和 `taskRegistry` Map，支持多任务并发
- 每个任务独立的 EventSource、进度条、gallery 卡片
- 添加 `hasVideoContent` 标记，检测空视频完成状态
- 修复：旧代码全局只有一个 `eventSource`，新任务会覆盖前一个

#### `video.py`（后端服务）改动
- 文件：`app_services_grok_services_video.py` → 挂载为 `app/services/grok/services/video.py`
- 每次请求使用不同 token，避免 429 限流
- 添加 progress==100 但无 videoUrl 的 warning 日志和异常抛出

#### `app_api_v1_video.py`（视频 API）
- 恢复 Video SDK API 端点（`/v1/video/generations`、`/v1/video/content/{id}`）
- 兼容 waoowaoo 等外部调用方

---

### 3. 图像 API 修复

**Commits**: `3e81939`, `ffe2b93`

#### `app/api/v1/image.py` 改动
- 兼容非标准 size 参数（如 `512x512`），自动映射到 Grok 支持的最近似尺寸
- 映射逻辑：按面积最接近原则匹配 `ALLOWED_SIZES` 中的值

#### `app/services/grok/services/image_edit.py` 改动
- 修复 `ImageEditService.edit()` 缺少 `size` 参数导致 500 错误
- 将 `size` 参数透传到 Grok API 请求体

---

### 4. UpstreamException 修复

**Commit**: `985f5d8`

修复 `UpstreamException` 构造函数 `status_code` 参数传递错误（4 处调用点）。

---

## Docker Volume Mounts

`docker-compose.yml` 中的所有自定义 volume mount：

```yaml
volumes:
  # 数据和日志（标准）
  - ./data:/app/data
  - ./logs:/app/logs

  # === 视频修复 ===
  - ./app/static/public/js/video.js:/app/app/static/public/js/video.js:ro
  - ./app/static/public/css/video.css:/app/app/static/public/css/video.css:ro
  - ./app_services_grok_services_video.py:/app/app/services/grok/services/video.py:ro
  - ./app_api_v1_video.py:/app/app/api/v1/video.py:ro

  # === 图像 API 修复 ===
  - ./app/api/v1/image.py:/app/app/api/v1/image.py:ro
  - ./app/services/grok/services/image_edit.py:/app/app/services/grok/services/image_edit.py:ro

  # === 路由注册（含 image-edit）===
  - ./main.py:/app/main.py:ro

  # === 图像编辑页面 ===
  - ./app/static/public/pages/image-edit.html:/app/app/static/public/pages/image-edit.html:ro
  - ./app/static/public/css/image-edit.css:/app/app/static/public/css/image-edit.css:ro
  - ./app/static/public/js/image-edit.js:/app/app/static/public/js/image-edit.js:ro
  - ./app_public_api_image_edit.py:/app/app_public_api_image_edit.py:ro
  - ./app/static/common/html/public-header.html:/app/app/static/common/html/public-header.html:ro
```

---

## 合并上游更新指南

### 步骤

```bash
# 1. 添加上游远程（仅首次）
git remote add upstream https://github.com/chenyme/grok2api.git

# 2. 拉取上游最新代码
git fetch upstream

# 3. 查看上游更新了哪些文件
git diff main..upstream/main --stat

# 4. 重点检查覆盖文件是否有变化
git diff main..upstream/main -- main.py
git diff main..upstream/main -- app/static/common/html/public-header.html
git diff main..upstream/main -- app/api/v1/image.py
git diff main..upstream/main -- app/static/public/js/video.js
git diff main..upstream/main -- app/static/public/css/video.css
git diff main..upstream/main -- app/services/grok/services/image_edit.py
git diff main..upstream/main -- app/api/v1/video.py
git diff main..upstream/main -- app/services/grok/services/video.py

# 5. 合并（可能需要手动解决冲突）
git merge upstream/main

# 6. 解决冲突后，确保自定义改动仍然存在
# 7. 重新部署
ssh Frederic@DeepThink
cd ~/grok2api && docker compose up -d
```

### 冲突风险矩阵

| 文件 | 风险 | 处理策略 |
|------|------|----------|
| `main.py` | **高** | 上游经常添加路由。合并后检查我们的 3 个 import + 2 行路由注册 + 页面路由是否保留 |
| `public-header.html` | 中 | 上游可能加新页面导航。合并后确认"Edit 图像编辑"链接存在 |
| `app/api/v1/image.py` | 中 | 上游可能修改图像 API。合并后确认 size 映射逻辑保留 |
| `video.js` / `video.css` | 中 | 上游可能修复视频 UI。需要 diff 检查我们的并发修复是否被覆盖 |
| `image_edit.py` | 中 | 上游可能修复 edit 服务。检查 size 参数透传是否保留 |
| `video.py`（服务 + API） | 中 | 上游可能改视频逻辑。检查 token 轮换和 SDK 端点是否保留 |
| `docker-compose.yml` | 低 | 仅需保留自定义 volume mount 行 |
| 新建文件（6 个） | **无** | 与上游无交集，不会冲突 |

### main.py 合并速查

合并上游 `main.py` 后，确认以下内容存在：

```python
# === 我们的 import（在文件顶部 import 区域）===
from fastapi.responses import FileResponse
from fastapi import HTTPException
from app.core.auth import is_public_enabled
from app_public_api_image_edit import router as image_edit_public_router

# === 我们的路由注册（在 create_app() 中）===
app.include_router(image_edit_public_router, prefix="/v1/public")

# === 我们的页面路由（在 create_app() 末尾，return app 之前）===
@app.get("/image-edit", include_in_schema=False)
async def public_image_edit():
    if not is_public_enabled():
        raise HTTPException(status_code=404, detail="Not Found")
    return FileResponse(APP_DIR / "static/public/pages/image-edit.html")
```

---

## 提交历史（按时间倒序）

| Commit | 说明 |
|--------|------|
| `ce6bd57` | feat: 新增图像编辑页面（Edit 图像编辑） |
| `aeaf88f` | 恢复 Video SDK API 端点，兼容 waoowaoo 调用 |
| `ffe2b93` | fix: 挂载 image_edit.py 修复缺少 size 参数的 500 错误 |
| `3e81939` | feat: 兼容非标准 size 参数，自动映射到最近似尺寸 |
| `cbd1642` | merge: 合并上游 v1.5.3，保留自定义 volume mounts |
| `985f5d8` | fix: 修复 UpstreamException 构造函数参数错误 |
| `04ef2ad` | fix: 检测无视频返回的完成状态，后端异常不再静默吞掉 |
| `4c6532c` | fix: 添加 video.js/video.css 的 volume mount |
| `c358609` | fix: 修复视频并发多个 bug |
| `9099773` | fix: 修复视频页面并发生成时只有最后一个任务能完成 |
