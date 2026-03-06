"""Persistent runtime state helpers for fork extensions."""

from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path
from typing import Any

import aiofiles
import orjson

from app.core.logger import logger
from app.core.storage import DATA_DIR, get_storage

_RUNTIME_ROOT = DATA_DIR / "fork_runtime"


class RuntimeStateLimitExceeded(Exception):
    """Raised when a bounded runtime state namespace is full."""


def _namespace_dir(namespace: str) -> Path:
    return _RUNTIME_ROOT / namespace


def _item_path(namespace: str, key: str) -> Path:
    normalized = (key or "").strip()
    if not normalized:
        raise ValueError("Runtime state key cannot be empty")
    safe_name = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return _namespace_dir(namespace) / f"{safe_name}.json"


def _payload_timestamp(payload: dict[str, Any], timestamp_key: str) -> float:
    raw = payload.get(timestamp_key, payload.get("_saved_at", 0))
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


async def _unlink(path: Path) -> bool:
    try:
        await asyncio.to_thread(path.unlink)
        return True
    except FileNotFoundError:
        return False


async def _read_payload(path: Path) -> dict[str, Any] | None:
    try:
        async with aiofiles.open(path, "rb") as handle:
            raw = await handle.read()
        payload = orjson.loads(raw)
        if isinstance(payload, dict):
            return payload
    except FileNotFoundError:
        return None
    except Exception as exc:
        logger.warning("Fork runtime state read failed: %s (%s)", path, exc)

    await _unlink(path)
    return None


async def _write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{time.time_ns()}.tmp")
    async with aiofiles.open(temp_path, "wb") as handle:
        await handle.write(orjson.dumps(payload))
    await asyncio.to_thread(temp_path.replace, path)


async def _list_entries(
    namespace: str,
    *,
    ttl_seconds: int | None,
    timestamp_key: str,
) -> list[tuple[Path, dict[str, Any], float]]:
    root = _namespace_dir(namespace)
    if not root.exists():
        return []

    now = time.time()
    entries: list[tuple[Path, dict[str, Any], float]] = []
    for path in root.glob("*.json"):
        payload = await _read_payload(path)
        if payload is None:
            continue

        saved_at = _payload_timestamp(payload, timestamp_key)
        if ttl_seconds is not None and saved_at > 0 and now - saved_at > ttl_seconds:
            await _unlink(path)
            continue

        entries.append((path, payload, saved_at))

    return entries


async def put_runtime_item(
    namespace: str,
    key: str,
    payload: dict[str, Any],
    *,
    ttl_seconds: int | None = None,
    timestamp_key: str = "_saved_at",
    max_items: int | None = None,
    evict_oldest: bool = False,
) -> None:
    path = _item_path(namespace, key)
    now = time.time()
    item = dict(payload)
    item.setdefault(timestamp_key, now)
    item["_saved_at"] = now

    storage = get_storage()
    lock_name = f"fork_runtime_{namespace}"
    async with storage.acquire_lock(lock_name, timeout=5):
        entries = await _list_entries(
            namespace,
            ttl_seconds=ttl_seconds,
            timestamp_key=timestamp_key,
        )

        path_exists = any(existing_path == path for existing_path, _, _ in entries)
        if max_items is not None and not path_exists and len(entries) >= max_items:
            if not evict_oldest:
                raise RuntimeStateLimitExceeded(
                    f"Runtime state limit reached for namespace '{namespace}'"
                )

            overflow = len(entries) - max_items + 1
            for stale_path, _, _ in sorted(entries, key=lambda entry: entry[2])[:overflow]:
                await _unlink(stale_path)

        await _write_payload(path, item)


async def get_runtime_item(
    namespace: str,
    key: str,
    *,
    ttl_seconds: int | None = None,
    timestamp_key: str = "_saved_at",
) -> dict[str, Any] | None:
    path = _item_path(namespace, key)
    payload = await _read_payload(path)
    if payload is None:
        return None

    saved_at = _payload_timestamp(payload, timestamp_key)
    if ttl_seconds is not None and saved_at > 0 and time.time() - saved_at > ttl_seconds:
        await _unlink(path)
        return None

    return payload


async def delete_runtime_item(namespace: str, key: str) -> bool:
    return await _unlink(_item_path(namespace, key))


async def delete_runtime_items(namespace: str, keys: list[str]) -> int:
    removed = 0
    for key in keys:
        if key and await delete_runtime_item(namespace, key):
            removed += 1
    return removed

