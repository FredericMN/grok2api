"""
Public Image Edit API - session-based SSE endpoints.
Modeled after app/api/v1/public_api/video.py
"""

import uuid
from typing import Optional, List

import re

import orjson
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.auth import verify_public_key, verify_public_key_value
from app.core.logger import logger
from app.fork_ext.runtime_state import (
    RuntimeStateLimitExceeded,
    delete_runtime_item,
    delete_runtime_items,
    get_runtime_item,
    put_runtime_item,
)
from app.services.grok.services.image_edit import ImageEditService
from app.services.grok.services.model import ModelService
from app.services.token import get_token_manager

router = APIRouter()

IMAGE_EDIT_SESSION_NAMESPACE = "image_edit_sessions"
IMAGE_EDIT_SESSION_TTL = 600
MAX_SESSIONS = 50
MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20MB data URI payload (~15MB raw)

ALLOWED_SIZES = {"1280x720", "720x1280", "1792x1024", "1024x1792", "1024x1024"}
ALLOWED_MIMES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
_DATA_URI_RE = re.compile(r"^data:(image/(?:png|jpe?g|webp));base64,[A-Za-z0-9+/]+=*$", re.DOTALL)


async def _new_session(prompt: str, images: List[str], size: str, n: int) -> str:
    task_id = uuid.uuid4().hex
    try:
        await put_runtime_item(
            IMAGE_EDIT_SESSION_NAMESPACE,
            task_id,
            {
                "prompt": prompt,
                "images": images,
                "size": size,
                "n": n,
            },
            ttl_seconds=IMAGE_EDIT_SESSION_TTL,
            timestamp_key="created_at",
            max_items=MAX_SESSIONS,
        )
    except RuntimeStateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail="Too many active sessions") from exc
    return task_id


async def _get_session(task_id: str) -> Optional[dict]:
    if not task_id:
        return None
    info = await get_runtime_item(
        IMAGE_EDIT_SESSION_NAMESPACE,
        task_id,
        ttl_seconds=IMAGE_EDIT_SESSION_TTL,
        timestamp_key="created_at",
    )
    return dict(info) if info else None


async def _drop_session(task_id: str) -> None:
    if not task_id:
        return
    await delete_runtime_item(IMAGE_EDIT_SESSION_NAMESPACE, task_id)


async def _drop_sessions(task_ids: List[str]) -> int:
    if not task_ids:
        return 0
    return await delete_runtime_items(IMAGE_EDIT_SESSION_NAMESPACE, task_ids)


async def _get_token(model_id: str):
    token_mgr = await get_token_manager()
    await token_mgr.reload_if_stale()
    token = None
    for pool_name in ModelService.pool_candidates_for_model(model_id):
        token = token_mgr.get_token(pool_name)
        if token:
            break
    return token_mgr, token


class ImageEditStartRequest(BaseModel):
    prompt: str
    images: List[str]
    size: Optional[str] = "1024x1024"
    n: Optional[int] = 1


@router.post("/image-edit/start", dependencies=[Depends(verify_public_key)])
async def public_image_edit_start(data: ImageEditStartRequest):
    prompt = (data.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")

    if not data.images or len(data.images) == 0:
        raise HTTPException(status_code=400, detail="At least one image is required")

    if len(data.images) > 3:
        raise HTTPException(status_code=400, detail="Maximum 3 images allowed")

    for img in data.images:
        if not img.startswith("data:image/"):
            raise HTTPException(
                status_code=400,
                detail="Images must be data URIs (data:image/...;base64,...)",
            )
        if ";base64," not in img:
            raise HTTPException(
                status_code=400,
                detail="Images must contain base64 encoded data",
            )
        # Check MIME type
        mime_part = img.split(";")[0].replace("data:", "")
        if mime_part not in ALLOWED_MIMES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported image type: {mime_part}. Allowed: png, jpg, webp",
            )
        # Check size (base64 length is ~4/3 of raw size)
        if len(img) > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=400,
                detail="Image too large. Maximum 15MB per image.",
            )

    size = (data.size or "1024x1024").strip()
    if size not in ALLOWED_SIZES:
        raise HTTPException(
            status_code=400,
            detail=f"size must be one of {sorted(ALLOWED_SIZES)}",
        )

    n = int(data.n or 1)
    if n not in (1, 2):
        raise HTTPException(status_code=400, detail="n must be 1 or 2 for streaming mode")

    task_id = await _new_session(prompt, data.images, size, n)
    return {"task_id": task_id}


@router.get("/image-edit/sse")
async def public_image_edit_sse(
    request: Request,
    task_id: str = Query(""),
    public_key: str = Query(""),
):
    # Validate public_key from query params using the same rules as header auth.
    verify_public_key_value(public_key or None)

    session = await _get_session(task_id)
    if not session:
        raise HTTPException(status_code=404, detail="Task not found")

    prompt = str(session.get("prompt", "")).strip()
    images = session.get("images", [])
    size = str(session.get("size", "1024x1024"))
    n = int(session.get("n", 1))

    async def event_stream():
        try:
            model_id = "grok-imagine-1.0-edit"
            model_info = ModelService.get(model_id)
            if not model_info:
                payload = {
                    "error": "Image edit model is not available.",
                    "code": "model_not_supported",
                }
                yield f"data: {orjson.dumps(payload).decode()}\n\n"
                yield "data: [DONE]\n\n"
                return

            token_mgr, token = await _get_token(model_id)
            if not token:
                payload = {
                    "error": "No available tokens. Please try again later.",
                    "code": "rate_limit_exceeded",
                }
                yield f"data: {orjson.dumps(payload).decode()}\n\n"
                yield "data: [DONE]\n\n"
                return

            result = await ImageEditService().edit(
                token_mgr=token_mgr,
                token=token,
                model_info=model_info,
                prompt=prompt,
                images=images,
                n=n,
                response_format="url",
                stream=True,
                size=size,
            )

            if not result.stream:
                payload = {
                    "error": "Unexpected non-stream result",
                    "code": "internal_error",
                }
                yield f"data: {orjson.dumps(payload).decode()}\n\n"
                yield "data: [DONE]\n\n"
                return

            async for chunk in result.data:
                if await request.is_disconnected():
                    break
                yield chunk

            # ImageStreamProcessor doesn't emit [DONE] in non-chat_format mode,
            # so we must append it to signal the frontend stream is complete.
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.warning(f"Public image edit SSE error: {e}")
            payload = {"error": str(e), "code": "internal_error"}
            yield f"data: {orjson.dumps(payload).decode()}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            await _drop_session(task_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


class ImageEditStopRequest(BaseModel):
    task_ids: List[str]


@router.post("/image-edit/stop", dependencies=[Depends(verify_public_key)])
async def public_image_edit_stop(data: ImageEditStopRequest):
    removed = await _drop_sessions(data.task_ids or [])
    return {"status": "success", "removed": removed}


__all__ = ["router"]
