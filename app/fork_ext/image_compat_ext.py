"""Image API compatibility patches and route overrides."""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.core.auth import verify_api_key
from app.core.exceptions import AppException, ErrorType, ValidationException
from app.core.logger import logger
from app.services.grok.services.image_edit import ImageEditResult, ImageEditService
from app.services.grok.services.model import ModelService

_PATCH_FLAG = "_fork_image_compat_patched"
_ROUTES_FLAG = "_fork_image_compat_routes_registered"

SIZE_COMPAT_MAP = {
    "1536x1024": "1792x1024",
    "1024x1536": "1024x1792",
    "256x256": "1024x1024",
    "512x512": "1024x1024",
    "auto": "1024x1024",
}

SIZE_TO_ASPECT = {
    "1280x720": "16:9",
    "720x1280": "9:16",
    "1792x1024": "3:2",
    "1024x1792": "2:3",
    "1024x1024": "1:1",
}

compat_router = APIRouter(tags=["ImagesCompat"])


@compat_router.post("/v1/images/edits")
async def edit_image_compat(
    request: Request,
    prompt: str = Form(...),
    model: Optional[str] = Form("grok-imagine-1.0-edit"),
    n: int = Form(1),
    size: str = Form("720x1280"),
    quality: str = Form("standard"),
    response_format: Optional[str] = Form(None),
    style: Optional[str] = Form(None),
    stream: Optional[bool] = Form(False),
):
    import app.api.v1.image as image_api

    form = await request.form()
    image_items = list(form.getlist("image")) or list(form.getlist("image[]"))
    if not image_items:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": "image field required",
                    "param": "image",
                    "code": "missing_field",
                }
            },
        )

    if response_format is None:
        response_format = image_api.resolve_response_format(None)

    try:
        edit_request = image_api.ImageEditRequest(
            prompt=prompt,
            model=model,
            n=n,
            size=size,
            quality=quality,
            response_format=response_format,
            style=style,
            stream=stream,
        )
    except ValidationError as exc:
        errors = exc.errors()
        if errors:
            first = errors[0]
            loc = first.get("loc", [])
            msg = first.get("msg", "Invalid request")
            code = first.get("type", "invalid_value")
            param_parts = [
                str(item) for item in loc if not (isinstance(item, int) or str(item).isdigit())
            ]
            param = ".".join(param_parts) if param_parts else None
            raise ValidationException(message=msg, param=param, code=code)
        raise ValidationException(message="Invalid request", code="invalid_value")

    if edit_request.stream is None:
        edit_request.stream = False

    response_format = image_api.resolve_response_format(edit_request.response_format)
    if response_format == "base64":
        response_format = "b64_json"
    edit_request.response_format = response_format
    response_field = image_api.response_field_name(response_format)

    # request.form() returns Starlette UploadFile objects.
    upload_files = [item for item in image_items if isinstance(item, StarletteUploadFile)]
    image_api.validate_edit_request(edit_request, upload_files)

    max_image_bytes = 50 * 1024 * 1024
    allowed_types = {"image/png", "image/jpeg", "image/webp", "image/jpg"}

    images: List[str] = []
    for item in upload_files:
        content = await item.read()
        await item.close()
        if not content:
            raise ValidationException(
                message="File content is empty",
                param="image",
                code="empty_file",
            )
        if len(content) > max_image_bytes:
            raise ValidationException(
                message="Image file too large. Maximum is 50MB.",
                param="image",
                code="file_too_large",
            )
        mime = (item.content_type or "").lower()
        if mime == "image/jpg":
            mime = "image/jpeg"
        ext = Path(item.filename or "").suffix.lower()
        if mime not in allowed_types:
            if ext in (".jpg", ".jpeg"):
                mime = "image/jpeg"
            elif ext == ".png":
                mime = "image/png"
            elif ext == ".webp":
                mime = "image/webp"
            else:
                raise ValidationException(
                    message="Unsupported image type. Supported: png, jpg, webp.",
                    param="image",
                    code="invalid_image_type",
                )
        b64 = base64.b64encode(content).decode()
        images.append(f"data:{mime};base64,{b64}")

    effective_model = (
        "grok-imagine-1.0-edit" if edit_request.model == "grok-imagine-1.0" else edit_request.model
    )
    token_mgr, token = await image_api._get_token(effective_model)
    model_info = ModelService.get(effective_model)

    result = await ImageEditService().edit(
        token_mgr=token_mgr,
        token=token,
        model_info=model_info,
        prompt=edit_request.prompt,
        images=images,
        n=edit_request.n,
        response_format=response_format,
        stream=bool(edit_request.stream),
        size=edit_request.size or "720x1280",
    )

    if result.stream:
        return StreamingResponse(
            result.data,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    data = [{response_field: img} for img in result.data]
    return JSONResponse(
        content={
            "created": int(time.time()),
            "data": data,
            "usage": {
                "total_tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "input_tokens_details": {"text_tokens": 0, "image_tokens": 0},
            },
        }
    )


def _apply_size_map(value: Optional[str]) -> Optional[str]:
    if not isinstance(value, str):
        return value
    mapped = SIZE_COMPAT_MAP.get(value.strip())
    return mapped or value


async def _patched_edit(
    self,
    *,
    token_mgr,
    token: str,
    model_info,
    prompt: str,
    images: List[str],
    n: int,
    response_format: str,
    stream: bool,
    chat_format: bool = False,
    size: str = "720x1280",
) -> ImageEditResult:
    import app.services.grok.services.image_edit as image_edit_mod

    if len(images) > 3:
        image_edit_mod.logger.info(
            "Image edit received %d references; using the most recent 3",
            len(images),
        )
        images = images[-3:]

    max_token_retries = int(image_edit_mod.get_config("retry.max_retry") or 3)
    tried_tokens: set[str] = set()
    last_error: Exception | None = None

    for attempt in range(max_token_retries):
        preferred = token if attempt == 0 else None
        current_token = await image_edit_mod.pick_token(
            token_mgr, model_info.model_id, tried_tokens, preferred=preferred
        )
        if not current_token:
            if last_error:
                raise last_error
            raise AppException(
                message="No available tokens. Please try again later.",
                error_type=ErrorType.RATE_LIMIT.value,
                code="rate_limit_exceeded",
                status_code=429,
            )

        tried_tokens.add(current_token)
        try:
            image_urls = await self._upload_images(images, current_token)
            parent_post_id = await self._get_parent_post_id(current_token, image_urls)

            aspect_ratio = SIZE_TO_ASPECT.get(_apply_size_map(size), "9:16")
            model_config_override = {
                "modelMap": {
                    "imageEditModel": "imagine",
                    "imageEditModelConfig": {
                        "imageReferences": image_urls,
                        "aspectRatio": aspect_ratio,
                    },
                }
            }
            if parent_post_id:
                model_config_override["modelMap"]["imageEditModelConfig"][
                    "parentPostId"
                ] = parent_post_id

            tool_overrides = {"imageGen": True}

            if stream:
                response = await image_edit_mod.GrokChatService().chat(
                    token=current_token,
                    message=prompt,
                    model=model_info.grok_model,
                    mode=None,
                    stream=True,
                    tool_overrides=tool_overrides,
                    model_config_override=model_config_override,
                )
                processor = image_edit_mod.ImageStreamProcessor(
                    model_info.model_id,
                    current_token,
                    n=n,
                    response_format=response_format,
                    chat_format=chat_format,
                )
                return ImageEditResult(
                    stream=True,
                    data=image_edit_mod.wrap_stream_with_usage(
                        processor.process(response),
                        token_mgr,
                        current_token,
                        model_info.model_id,
                    ),
                )

            images_out = await self._collect_images(
                token=current_token,
                prompt=prompt,
                model_info=model_info,
                n=n,
                response_format=response_format,
                tool_overrides=tool_overrides,
                model_config_override=model_config_override,
            )
            try:
                effort = (
                    image_edit_mod.EffortType.HIGH
                    if (model_info and model_info.cost.value == "high")
                    else image_edit_mod.EffortType.LOW
                )
                await token_mgr.consume(current_token, effort)
                image_edit_mod.logger.debug(
                    "Image edit completed, recorded usage (effort=%s)",
                    effort.value,
                )
            except Exception as exc:
                image_edit_mod.logger.warning(
                    "Failed to record image edit usage: %s", exc
                )
            return ImageEditResult(stream=False, data=images_out)

        except image_edit_mod.UpstreamException as exc:
            last_error = exc
            if image_edit_mod.rate_limited(exc):
                await token_mgr.mark_rate_limited(current_token)
                image_edit_mod.logger.warning(
                    "Token %s... rate limited (429), trying next token (attempt %s/%s)",
                    current_token[:10],
                    attempt + 1,
                    max_token_retries,
                )
                continue
            raise

    if last_error:
        raise last_error
    raise AppException(
        message="No available tokens. Please try again later.",
        error_type=ErrorType.RATE_LIMIT.value,
        code="rate_limit_exceeded",
        status_code=429,
    )


def apply_runtime_patches() -> None:
    import app.api.v1.image as image_api
    import app.services.grok.services.image_edit as image_edit_mod

    if getattr(image_api, _PATCH_FLAG, False):
        return

    original_validate_common = image_api._validate_common_request

    def _validate_common_with_compat(request_obj, *, allow_ws_stream=False):
        if hasattr(request_obj, "size"):
            request_obj.size = _apply_size_map(request_obj.size)
        return original_validate_common(request_obj, allow_ws_stream=allow_ws_stream)

    original_validate_edit = image_api.validate_edit_request

    def _validate_edit_with_model_alias(request_obj, images):
        if getattr(request_obj, "model", None) == "grok-imagine-1.0":
            request_obj.model = "grok-imagine-1.0-edit"
        return original_validate_edit(request_obj, images)

    existing = dict(getattr(image_api, "SIZE_COMPAT_MAP", {}))
    existing.update(SIZE_COMPAT_MAP)
    image_api.SIZE_COMPAT_MAP = existing
    image_api._validate_common_request = _validate_common_with_compat
    image_api.validate_edit_request = _validate_edit_with_model_alias
    image_edit_mod.ImageEditService.edit = _patched_edit

    setattr(image_api, _PATCH_FLAG, True)
    logger.info("Fork image compatibility patch applied")


def register_pre_routes(app) -> None:
    if getattr(app.state, _ROUTES_FLAG, False):
        return

    app.include_router(compat_router, dependencies=[Depends(verify_api_key)])

    setattr(app.state, _ROUTES_FLAG, True)
    logger.info("Fork image compatibility routes registered")
