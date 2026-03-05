"""Static asset overlays for fork custom UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.logger import logger

router = APIRouter(include_in_schema=False)

_OVERLAY_STATIC_ROOT = Path(__file__).resolve().parents[2] / "fork_overlays" / "static"
_UPSTREAM_STATIC_ROOT = Path(__file__).resolve().parents[1] / "static"


def _resolve_asset(rel_path: str) -> Path:
    overlay_path = _OVERLAY_STATIC_ROOT / rel_path
    if overlay_path.exists():
        return overlay_path
    fallback_path = _UPSTREAM_STATIC_ROOT / rel_path
    if fallback_path.exists():
        return fallback_path
    raise HTTPException(status_code=404, detail="Not Found")


@router.get("/static/common/html/public-header.html")
async def overlay_public_header():
    return FileResponse(_resolve_asset("common/html/public-header.html"))


@router.get("/static/public/js/video.js")
async def overlay_video_js():
    return FileResponse(_resolve_asset("public/js/video.js"))


@router.get("/static/public/css/video.css")
async def overlay_video_css():
    return FileResponse(_resolve_asset("public/css/video.css"))


@router.get("/static/public/pages/image-edit.html")
async def overlay_image_edit_page():
    return FileResponse(_resolve_asset("public/pages/image-edit.html"))


@router.get("/static/public/js/image-edit.js")
async def overlay_image_edit_js():
    return FileResponse(_resolve_asset("public/js/image-edit.js"))


@router.get("/static/public/css/image-edit.css")
async def overlay_image_edit_css():
    return FileResponse(_resolve_asset("public/css/image-edit.css"))


_FORK_OVERLAY_FLAG = "_fork_frontend_overlay_registered"


def register_pre_routes(app) -> None:
    if getattr(app.state, _FORK_OVERLAY_FLAG, False):
        return

    app.include_router(router)

    setattr(app.state, _FORK_OVERLAY_FLAG, True)
    logger.info("Fork frontend overlay extension registered")
