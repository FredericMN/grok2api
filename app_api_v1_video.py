"""
Video Generation API 路由 - OpenAI 兼容
支持 multipart/form-data 和 JSON 两种格式
"""

import uuid
import base64
import time
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.services.grok.services.video import VideoService
from app.core.exceptions import ValidationException, AppException
from app.core.logger import logger


router = APIRouter(tags=["Videos"])

# 内存缓存：存储已完成的视频结果，供轮询使用
_video_cache: dict = {}
VIDEO_CACHE_TTL_SECONDS = 1800
VIDEO_CACHE_MAX_ITEMS = 200

SIZE_TO_ASPECT = {
    "1280x720": "16:9",
    "720x1280": "9:16",
    "1792x1024": "3:2",
    "1024x1792": "2:3",
    "1024x1024": "1:1",
}

SECONDS_MAP = {4: 6, 8: 10, 12: 15, 6: 6, 10: 10, 15: 15}


def _resolve_params(prompt, model, seconds, size, aspect_ratio=None, resolution=None, preset=None):
    if not prompt or not prompt.strip():
        raise ValidationException(message="Prompt cannot be empty", param="prompt", code="empty_prompt")
    if seconds in (None, ""):
        seconds_int = 4
    else:
        if isinstance(seconds, bool):
            raise ValidationException(
                message="seconds must be an integer",
                param="seconds",
                code="invalid_value",
            )
        try:
            seconds_int = int(seconds)
        except (TypeError, ValueError):
            raise ValidationException(
                message="seconds must be an integer",
                param="seconds",
                code="invalid_value",
            )
    video_length = SECONDS_MAP.get(seconds_int, 6)
    if aspect_ratio:
        ar = aspect_ratio
    elif size and size in SIZE_TO_ASPECT:
        ar = SIZE_TO_ASPECT[size]
    else:
        ar = "9:16"
    return {
        "model": model or "grok-imagine-1.0-video",
        "aspect_ratio": ar,
        "video_length": video_length,
        "resolution": resolution or "480p",
        "preset": preset or "normal",
    }


def _cleanup_video_cache(now: float) -> None:
    expired_ids = [
        key
        for key, value in _video_cache.items()
        if now - float(value.get("_cached_at", now)) > VIDEO_CACHE_TTL_SECONDS
    ]
    for key in expired_ids:
        _video_cache.pop(key, None)

    overflow = len(_video_cache) - VIDEO_CACHE_MAX_ITEMS
    if overflow > 0:
        oldest_keys = sorted(
            _video_cache.keys(),
            key=lambda key: float(_video_cache[key].get("_cached_at", now)),
        )[:overflow]
        for key in oldest_keys:
            _video_cache.pop(key, None)


def _sanitize_cached_payload(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if not str(k).startswith("_")}


def _cache_video_result(response_id: str, payload: dict) -> None:
    now = time.time()
    item = dict(payload)
    item["_cached_at"] = now
    _video_cache[response_id] = item
    _cleanup_video_cache(now)


def _get_cached_video(video_id: str) -> Optional[dict]:
    now = time.time()
    _cleanup_video_cache(now)
    return _video_cache.get(video_id)


async def _run_video(prompt, params, image_url=None):
    messages = [{"role": "user", "content": prompt}]
    if image_url:
        messages[0]["content"] = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]
    logger.info(
        f"Video API: prompt='{prompt[:50]}', model={params['model']}, "
        f"ar={params['aspect_ratio']}, length={params['video_length']}s"
    )
    result = await VideoService.completions(
        model=params["model"],
        messages=messages,
        stream=False,
        aspect_ratio=params["aspect_ratio"],
        video_length=params["video_length"],
        resolution=params["resolution"],
        preset=params["preset"],
    )
    choices = result.get("choices", [])
    if not choices:
        raise AppException(message="No video generated", error_type="server_error", code="no_video", status_code=500)

    content = choices[0].get("message", {}).get("content", "")
    response_id = result.get("id", "") or f"video-{uuid.uuid4().hex[:24]}"

    # 提取视频 URL（content 可能是 markdown 格式或直接 URL）
    video_url = None
    if content:
        import re
        # 尝试从 markdown 链接中提取 URL
        m = re.search(r'https?://\S+\.mp4[^\s\)\"]*', content)
        if m:
            video_url = m.group(0).rstrip(')')
        elif content.startswith("http"):
            video_url = content.strip()

    # 缓存结果供轮询使用
    _cache_video_result(response_id, {
        "id": response_id,
        "status": "completed",
        "video_url": video_url,
        "content": content,
        "model": params["model"],
        "created": result.get("created", 0),
    })

    return JSONResponse(content={
        "id": response_id,
        "object": "video.created",
        "created": result.get("created", 0),
        "model": params["model"],
        "status": "completed",
        "video_url": video_url,
        "content": content,
    })


@router.post("/v1/videos")
async def create_video_sdk(request: Request):
    """OpenAI SDK 兼容端点 - 支持 multipart/form-data 和 JSON"""
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        prompt = form.get("prompt", "")
        model = form.get("model") or None
        seconds = form.get("seconds")
        size = form.get("size") or None
        image_url = None
        input_ref = form.get("input_reference")
        if input_ref and hasattr(input_ref, "read"):
            data = await input_ref.read()
            mime = getattr(input_ref, "content_type", None) or "image/png"
            image_url = f"data:{mime};base64,{base64.b64encode(data).decode()}"
    else:
        body = await request.json()
        prompt = body.get("prompt", "")
        model = body.get("model")
        seconds = body.get("seconds")
        size = body.get("size")
        image_url = body.get("image_url")

    params = _resolve_params(prompt, model, seconds, size)
    return await _run_video(prompt, params, image_url)


@router.post("/v1/video/create")
async def create_video_fallback(request: Request):
    """Fallback 端点 - JSON 格式"""
    body = await request.json()
    prompt = body.get("prompt", "")
    model = body.get("model")
    seconds = body.get("seconds")
    size = body.get("size")
    image_url = body.get("image_url")
    params = _resolve_params(prompt, model, seconds, size)
    return await _run_video(prompt, params, image_url)


@router.get("/v1/videos/{video_id}")
async def get_video(video_id: str):
    """轮询视频状态 - waoowaoo 用此接口查询结果"""
    cached = _get_cached_video(video_id)
    if cached:
        return JSONResponse(content=_sanitize_cached_payload(cached))
    # 不在缓存中（可能是重启后），返回 completed 但无 URL
    # waoowaoo 会 fallback 到 /videos/{id}/content
    return JSONResponse(content={
        "id": video_id,
        "status": "completed",
        "video_url": None,
    })


@router.get("/v1/videos/{video_id}/content")
async def get_video_content(video_id: str):
    """视频文件下载 - 重定向到实际视频 URL"""
    cached = _get_cached_video(video_id)
    if cached and cached.get("video_url"):
        return RedirectResponse(url=cached["video_url"])
    raise AppException(
        message="Video not found",
        error_type="not_found",
        code="video_not_found",
        status_code=404,
    )


__all__ = ["router"]
