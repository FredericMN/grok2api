"""Image edit public APIs and page registration."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.core.auth import is_public_enabled
from app.core.logger import logger
from app_public_api_image_edit import router as image_edit_public_router


_FORK_IMAGE_EDIT_FLAG = "_fork_image_edit_registered"
_IMAGE_EDIT_PAGE = Path(__file__).resolve().parents[2] / "fork_overlays" / "static" / "public" / "pages" / "image-edit.html"


def register_post_routes(app) -> None:
    if getattr(app.state, _FORK_IMAGE_EDIT_FLAG, False):
        return

    app.include_router(image_edit_public_router, prefix="/v1/public")

    @app.get("/image-edit", include_in_schema=False)
    async def public_image_edit():
        if not is_public_enabled():
            raise HTTPException(status_code=404, detail="Not Found")
        if _IMAGE_EDIT_PAGE.exists():
            return FileResponse(_IMAGE_EDIT_PAGE)
        raise HTTPException(status_code=404, detail="Not Found")

    setattr(app.state, _FORK_IMAGE_EDIT_FLAG, True)
    logger.info("Fork image-edit extension registered")
