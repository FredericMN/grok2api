"""Fork extension loader utilities."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Iterable

DEFAULT_FORK_EXTENSIONS = (
    "app.fork_ext.image_edit_ext",
    "app.fork_ext.video_compat_ext",
    "app.fork_ext.image_compat_ext",
    "app.fork_ext.video_runtime_ext",
    "app.fork_ext.frontend_overlay_ext",
)


def parse_fork_extensions(raw: str | None) -> list[str]:
    value = (raw or "").strip()
    if not value:
        return list(DEFAULT_FORK_EXTENSIONS)
    if value.lower() in {"0", "off", "none", "false", "disabled"}:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def load_fork_extensions(extension_names: Iterable[str], logger) -> list[ModuleType]:
    modules: list[ModuleType] = []
    for name in extension_names:
        try:
            mod = import_module(name)
            modules.append(mod)
            logger.info(f"Fork extension loaded: {name}")
        except Exception as exc:
            logger.exception(f"Fork extension load failed: {name}, error={exc}")
    return modules


def _run_hook(modules: Iterable[ModuleType], hook_name: str, logger, *args) -> None:
    for mod in modules:
        hook = getattr(mod, hook_name, None)
        if callable(hook):
            try:
                hook(*args)
            except Exception as exc:
                logger.exception(
                    f"Fork extension hook failed: module={mod.__name__}, hook={hook_name}, error={exc}"
                )


def apply_runtime_patches(modules: Iterable[ModuleType], logger) -> None:
    _run_hook(modules, "apply_runtime_patches", logger)


def register_pre_routes(modules: Iterable[ModuleType], logger, app) -> None:
    _run_hook(modules, "register_pre_routes", logger, app)


def register_post_routes(modules: Iterable[ModuleType], logger, app) -> None:
    _run_hook(modules, "register_post_routes", logger, app)
