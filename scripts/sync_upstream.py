#!/usr/bin/env python3
"""Check upstream changes and generate a merge-risk report."""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import subprocess
import sys
from typing import Iterable


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


def parse_conflicts(merge_tree_output: str) -> list[str]:
    lines = merge_tree_output.splitlines()
    current_path = ""
    conflicts: set[str] = set()
    for line in lines:
        m = re.match(r"^  base\s+\d+\s+[0-9a-f]+\s+(.+)$", line)
        if m:
            current_path = m.group(1)
            continue
        if line.lstrip().startswith("<<<<<<<") or line.lstrip().startswith("=======") or line.lstrip().startswith(">>>>>>>"):
            if current_path:
                conflicts.add(current_path)
    return sorted(conflicts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref", default="main")
    parser.add_argument("--upstream-ref", default="upstream/main")
    parser.add_argument("--report-path", default="reports/upstream-watch.md")
    args = parser.parse_args()

    run(["git", "fetch", "upstream", "--prune"])

    left_right = run(["git", "rev-list", "--left-right", "--count", f"{args.base_ref}...{args.upstream_ref}"])
    ours, theirs = left_right.split()[:2]
    merge_base = run(["git", "merge-base", args.base_ref, args.upstream_ref])

    upstream_commits = run([
        "git",
        "log",
        "--oneline",
        "--decorate",
        f"{args.base_ref}..{args.upstream_ref}",
        "-n",
        "20",
    ])

    changed_files = run([
        "git",
        "diff",
        "--name-status",
        f"{args.base_ref}..{args.upstream_ref}",
    ])

    merge_tree = run(["git", "merge-tree", merge_base, args.base_ref, args.upstream_ref])
    conflicts = parse_conflicts(merge_tree)

    now = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%SZ")
    report = [
        "# Upstream Watch Report",
        "",
        f"- Generated (UTC): {now}",
        f"- Base ref: `{args.base_ref}`",
        f"- Upstream ref: `{args.upstream_ref}`",
        f"- Ahead/behind (`{args.base_ref}...{args.upstream_ref}`): ours={ours}, upstream={theirs}",
        f"- Merge base: `{merge_base}`",
        "",
        "## Upstream commits (latest 20)",
        "",
        "```text",
        upstream_commits or "(none)",
        "```",
        "",
        "## Changed files",
        "",
        "```text",
        changed_files or "(none)",
        "```",
        "",
        "## Simulated conflict files",
        "",
    ]

    if conflicts:
        report.extend([f"- `{item}`" for item in conflicts])
    else:
        report.append("- (none)")

    path = pathlib.Path(args.report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(report) + "\n", encoding="utf-8")

    print(path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[sync_upstream] {exc}", file=sys.stderr)
        raise SystemExit(1)
