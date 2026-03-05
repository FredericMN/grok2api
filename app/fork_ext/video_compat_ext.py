"""Video compatibility endpoints registration."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.auth import verify_api_key
from app.core.logger import logger
from app_api_v1_video import (
    router as video_compat_router,
    create_video_sdk,
    get_video_content,
)

router = APIRouter(tags=["VideosCompat"])


@router.post("/v1/video/generations")
async def create_video_generations_compat(request: Request):
    return await create_video_sdk(request)


@router.get("/v1/video/content/{video_id}")
async def get_video_content_compat(video_id: str):
    return await get_video_content(video_id)


_FORK_VIDEO_COMPAT_FLAG = "_fork_video_compat_registered"


def register_post_routes(app) -> None:
    if getattr(app.state, _FORK_VIDEO_COMPAT_FLAG, False):
        return

    app.include_router(video_compat_router, dependencies=[Depends(verify_api_key)])
    app.include_router(router, dependencies=[Depends(verify_api_key)])

    setattr(app.state, _FORK_VIDEO_COMPAT_FLAG, True)
    logger.info("Fork video compatibility extension registered")
