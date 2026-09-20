#!/usr/bin/env python3
"""Convert Apps text files to Unix LF.

TrimUI MainUI execs launch.sh. A CRLF shebang (#!/bin/sh\\r) shows up as 架构错误.
Run from anywhere:

    python _assets/scripts/fix_apps_lf.py
    python _assets/scripts/fix_apps_lf.py --dry-run
    python _assets/scripts/fix_apps_lf.py --all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

TEXT_EXT = {
    ".sh",
    ".json",
    ".py",
    ".txt",
    ".md",
    ".gptk",
    ".conf",
    ".cfg",
    ".ini",
    ".css",
    ".js",
    ".html",
    ".htm",
    ".xml",
    ".yml",
    ".yaml",
    ".csv",
    ".svg",
}

SKIP_DIRS = {
    "__pycache__",
    ".git",
    "node_modules",
}

# Huge upstream trees. launch.sh / config.json above them are still converted.
SKIP_DIR_PARTS = {
    ("PortMaster", "PortMaster", "exlibs"),
    ("PortMaster", "PortMaster", "pylibs"),
}

ALWAYS_NAMES = {
    "launch.sh",
    "run.sh",
    "play.sh",
    "config.json",
    "keys.gptk",
    "thd.conf",
}


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "Apps").is_dir():
            return parent
    return here.parents[2]


def skip_dir(path: Path, apps: Path, include_vendor: bool) -> bool:
    if path.name in SKIP_DIRS:
        return True
    if include_vendor:
        return False
    try:
        parts = path.relative_to(apps).parts
    except ValueError:
        return False
    for skip in SKIP_DIR_PARTS:
        if parts[: len(skip)] == skip:
            return True
    return False


def looks_text(path: Path) -> bool:
    if path.name in ALWAYS_NAMES:
        return True
    if path.suffix.lower() in TEXT_EXT:
        return True
    if path.suffix:
        return False
    try:
        head = path.read_bytes()[:2]
    except OSError:
        return False
    return head == b"#!"


def convert(path: Path, dry_run: bool) -> str:
    try:
        data = path.read_bytes()
    except OSError as exc:
        return f"error:{exc}"
    if b"\0" in data[:4096]:
        return "skip-binary"
    if b"\r\n" not in data and not data.endswith(b"\r"):
        return "ok"
    if dry_run:
        return "would-fix"
    path.write_bytes(data.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
    return "fixed"


def walk(apps: Path, include_vendor: bool):
    stack = [apps]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                if not skip_dir(entry, apps, include_vendor):
                    stack.append(entry)
                continue
            if looks_text(entry):
                yield entry


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert Apps text files to Unix LF")
    parser.add_argument(
        "root",
        nargs="?",
        default=None,
        help="Apps directory (default: <repo>/Apps)",
    )
    parser.add_argument("--dry-run", action="store_true", help="list files only")
    parser.add_argument(
        "--all",
        action="store_true",
        help="also convert PortMaster vendor trees (exlibs/pylibs)",
    )
    args = parser.parse_args()

    apps = Path(args.root).resolve() if args.root else repo_root() / "Apps"
    if not apps.is_dir():
        print(f"not a directory: {apps}", file=sys.stderr)
        return 1

    counts = {"fixed": 0, "would-fix": 0, "ok": 0, "skip-binary": 0, "error": 0}
    changed = []
    for path in sorted(walk(apps, args.all)):
        status = convert(path, args.dry_run)
        key = status.split(":", 1)[0]
        counts[key] = counts.get(key, 0) + 1
        if status in {"fixed", "would-fix"} or status.startswith("error"):
            rel = path.relative_to(apps)
            print(f"{status:10} {rel}")
            changed.append(rel)

    print()
    print(f"Apps: {apps}")
    print(
        f"fixed={counts['fixed']} would-fix={counts['would-fix']} "
        f"already-lf={counts['ok']} binary={counts['skip-binary']} error={counts['error']}"
    )
    if args.dry_run and counts["would-fix"]:
        print("re-run without --dry-run to write LF")
    return 0 if counts["error"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
