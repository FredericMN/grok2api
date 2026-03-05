"""Video runtime behavior patching."""

from __future__ import annotations

import inspect
from collections import deque
from typing import Optional

from app.core.logger import logger

_PATCH_FLAG = "_fork_video_runtime_patched"

_USED_VIDEO_TOKENS = deque(maxlen=128)


def _remember_video_token(token: str) -> None:
    raw = (token or "").removeprefix("sso=")
    if raw:
        _USED_VIDEO_TOKENS.append(raw)


def _select_video_token_with_exclude(
    token_mgr,
    resolution: str,
    video_length: int,
    pool_candidates,
    exclude: set[str],
):
    requires_super = resolution == "720p" or video_length > 6
    primary_pool = "ssoSuper" if requires_super else "ssoBasic"

    if pool_candidates:
        ordered_pools = list(pool_candidates)
        if primary_pool in ordered_pools:
            ordered_pools.remove(primary_pool)
            ordered_pools.insert(0, primary_pool)
    else:
        fallback_pool = "ssoBasic" if requires_super else "ssoSuper"
        ordered_pools = [primary_pool, fallback_pool]

    for idx, pool_name in enumerate(ordered_pools):
        pool = token_mgr.pools.get(pool_name)
        if not pool:
            continue
        token_info = pool.select(exclude=exclude)
        if token_info:
            if idx == 0:
                logger.info(
                    "Video token routing (fork): resolution=%s, length=%ss -> pool=%s (token=%s...)",
                    resolution,
                    video_length,
                    pool_name,
                    token_info.token[:10],
                )
            else:
                logger.info(
                    "Video token routing (fork): fallback from %s -> %s (token=%s...)",
                    ordered_pools[0],
                    pool_name,
                    token_info.token[:10],
                )
            return token_info

        if idx == 0 and requires_super and pool_name == primary_pool:
            next_pool = ordered_pools[1] if len(ordered_pools) > 1 else None
            if next_pool:
                logger.warning(
                    "Video token routing (fork): %s pool has no available token for resolution=%s, length=%ss. Falling back to %s pool.",
                    primary_pool,
                    resolution,
                    video_length,
                    next_pool,
                )

    return None


def apply_runtime_patches() -> None:
    import app.services.grok.services.video as core_video
    import app.services.token.manager as token_manager_mod

    if getattr(core_video, _PATCH_FLAG, False):
        return

    original_get_token_for_video = token_manager_mod.TokenManager.get_token_for_video
    original_collect_process = core_video.VideoCollectProcessor.process
    original_stream_process = core_video.VideoStreamProcessor.process

    signature = inspect.signature(original_get_token_for_video)
    has_exclude = "exclude" in signature.parameters

    def _patched_get_token_for_video(
        self,
        resolution: str = "480p",
        video_length: int = 6,
        pool_candidates: Optional[list[str]] = None,
        exclude: Optional[set[str]] = None,
    ):
        recent = set(_USED_VIDEO_TOKENS)
        if exclude:
            recent.update((item or "").removeprefix("sso=") for item in exclude)

        token_info = None
        if has_exclude:
            kwargs = {
                "resolution": resolution,
                "video_length": video_length,
                "pool_candidates": pool_candidates,
                "exclude": recent or None,
            }
            token_info = original_get_token_for_video(self, **kwargs)
            if not token_info and recent:
                kwargs["exclude"] = None
                token_info = original_get_token_for_video(self, **kwargs)
        else:
            token_info = _select_video_token_with_exclude(
                self,
                resolution,
                video_length,
                pool_candidates,
                recent,
            )
            if not token_info:
                token_info = original_get_token_for_video(
                    self,
                    resolution=resolution,
                    video_length=video_length,
                    pool_candidates=pool_candidates,
                )

        if token_info and getattr(token_info, "token", None):
            _remember_video_token(token_info.token)
        return token_info

    async def _patched_collect_process(self, response):
        result = await original_collect_process(self, response)
        choices = result.get("choices") or []
        first = choices[0] if choices else {}
        message = first.get("message") if isinstance(first, dict) else {}
        content = ""
        if isinstance(message, dict):
            content = (message.get("content") or "").strip()

        if not content:
            logger.warning("Video completed without content; forcing failure path")
            raise core_video.UpstreamException(
                message="Video generation completed without a usable result",
                details={"code": "video_empty_result"},
            )

        return result

    async def _patched_stream_process(self, response):
        has_video_content = False
        async for chunk in original_stream_process(self, response):
            if isinstance(chunk, str) and (
                ".mp4" in chunk or "generated_video" in chunk or "<video" in chunk
            ):
                has_video_content = True
            if chunk == "data: [DONE]\n\n" and not has_video_content:
                logger.warning("Video stream finished without video content")
            yield chunk

    token_manager_mod.TokenManager.get_token_for_video = _patched_get_token_for_video
    core_video.VideoCollectProcessor.process = _patched_collect_process
    core_video.VideoStreamProcessor.process = _patched_stream_process

    setattr(core_video, _PATCH_FLAG, True)
    logger.info("Fork video runtime patch applied")
