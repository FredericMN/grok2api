#!/usr/bin/env python3
"""Enforce core-file touch budget for pull requests."""

from __future__ import annotations

import fnmatch
import os
import pathlib
import subprocess
import sys
from typing import Iterable

ALLOWLIST_FILE = pathlib.Path(".github/touch-budget-allowlist.txt")


def run(cmd: Iterable[str]) -> str:
    proc = subprocess.run(
        list(cmd),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{proc.stderr.strip()}")
    return proc.stdout.strip()


def load_allowlist() -> list[str]:
    if not ALLOWLIST_FILE.exists():
        return []
    lines = []
    for raw in ALLOWLIST_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def is_allowed(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pat) for pat in patterns)


def is_core_path(path: str) -> bool:
    return (
        path.startswith("app/")
        or path in {"main.py", "app_api_v1_video.py", "app_public_api_image_edit.py", "app_services_grok_services_video.py"}
    )


def main() -> int:
    if os.getenv("TOUCH_BUDGET_BYPASS", "").lower() in {"1", "true", "yes"}:
        print("touch-budget bypassed")
        return 0

    base_ref = os.getenv("GITHUB_BASE_REF", "main")
    run(["git", "fetch", "origin", base_ref, "--depth", "1"])

    changed_raw = run(["git", "diff", "--name-only", f"origin/{base_ref}...HEAD"])
    changed = [line.strip() for line in changed_raw.splitlines() if line.strip()]

    allowlist = load_allowlist()
    violations = [
        path for path in changed if is_core_path(path) and not is_allowed(path, allowlist)
    ]

    if violations:
        print("Core touch budget violated. The following files are not allowed:")
        for item in violations:
            print(f"- {item}")
        print("\nAllowed patterns are defined in .github/touch-budget-allowlist.txt")
        return 1

    print("touch-budget check passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[touch-budget] {exc}", file=sys.stderr)
        raise SystemExit(1)
