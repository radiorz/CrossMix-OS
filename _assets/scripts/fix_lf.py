#!/usr/bin/env python3
"""Convert the CrossMix-OS tree to Unix LF.

TrimUI MainUI execs launch.sh. A CRLF shebang shows up as 架构错误.

    python _assets/scripts/fix_lf.py
    python _assets/scripts/fix_lf.py --dry-run
    python _assets/scripts/fix_lf.py --staged
    python _assets/scripts/fix_lf.py --install-hook
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter
from pathlib import Path

TEXT_EXT = {
    ".sh",
    ".bash",
    ".json",
    ".py",
    ".txt",
    ".md",
    ".rst",
    ".gptk",
    ".conf",
    ".cfg",
    ".ini",
    ".css",
    ".js",
    ".mjs",
    ".html",
    ".htm",
    ".xml",
    ".yml",
    ".yaml",
    ".csv",
    ".svg",
    ".toml",
    ".ps1",
    ".bat",
    ".cmd",
    ".glsl",
    ".vert",
    ".frag",
    ".vsh",
    ".fsh",
    ".slang",
    ".slangp",
    ".info",
    ".nanorc",
    ".desktop",
    ".service",
    ".map",
    ".lst",
    ".list",
    ".log",
    ".in",
    ".am",
    ".ac",
    ".m3u",
    ".cue",
    ".srt",
    ".ass",
    ".ssa",
    ".gpl",
    ".theme",
    ".layout",
}

BINARY_EXT = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".bmp",
    ".tga",
    ".dds",
    ".7z",
    ".zip",
    ".gz",
    ".xz",
    ".bz2",
    ".rar",
    ".tar",
    ".so",
    ".a",
    ".o",
    ".exe",
    ".dll",
    ".dylib",
    ".pyc",
    ".pyo",
    ".pyd",
    ".bin",
    ".elf",
    ".pbp",
    ".iso",
    ".img",
    ".wad",
    ".pak",
    ".pk3",
    ".rom",
    ".nes",
    ".sfc",
    ".smc",
    ".gba",
    ".gbc",
    ".gb",
    ".nds",
    ".n64",
    ".z64",
    ".v64",
    ".mp3",
    ".mp4",
    ".flac",
    ".ogg",
    ".wav",
    ".aac",
    ".wma",
    ".avi",
    ".mkv",
    ".webm",
    ".ttf",
    ".otf",
    ".woff",
    ".woff2",
    ".pdf",
    ".pjpf",
    ".trimui",
}

SKIP_DIRS = {".git", "__pycache__", "node_modules"}

VENDOR_DIR_PARTS = (
    ("Apps", "PortMaster", "PortMaster", "exlibs"),
    ("Apps", "PortMaster", "PortMaster", "pylibs"),
    ("System", "lib", "python3.11", "site-packages"),
    ("System", "sftpgo"),
)

ALWAYS_NAMES = {
    "launch.sh",
    "run.sh",
    "play.sh",
    "config.json",
    "keys.gptk",
    "thd.conf",
    ".gitattributes",
    ".editorconfig",
    ".gitignore",
}

MAX_BYTES = 16 * 1024 * 1024
HOOK_MARKER = "fix_lf.py --staged"

HOOK = """#!/bin/sh
# Convert staged text files to Unix LF before commit.
# TrimUI MainUI treats CRLF shebangs as 架构错误.
repo=$(git rev-parse --show-toplevel) || exit 1
cd "$repo" || exit 1

py=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1; then
    py=$c
    break
  fi
done
if [ -z "$py" ]; then
  echo "pre-commit: python not found, cannot normalize LF" >&2
  exit 1
fi

"$py" "$repo/_assets/scripts/fix_lf.py" --staged --quiet
"""


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "Apps").is_dir() and (parent / "Emus").is_dir():
            return parent
    return here.parents[2]


def skip_dir(path: Path, root: Path, skip_vendor: bool) -> bool:
    if path.name in SKIP_DIRS:
        return True
    if not skip_vendor:
        return False
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return False
    for skip in VENDOR_DIR_PARTS:
        if parts[: len(skip)] == skip:
            return True
    return False


def looks_text(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in BINARY_EXT:
        return False
    if path.name in ALWAYS_NAMES or suffix in TEXT_EXT:
        return True
    if suffix:
        return False
    try:
        head = path.read_bytes()[:2]
    except OSError:
        return False
    return head == b"#!"


def convert(path: Path, dry_run: bool) -> str:
    try:
        size = path.stat().st_size
    except OSError as exc:
        return f"error:{exc}"
    if size > MAX_BYTES:
        return "skip-large"
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


def walk(root: Path, skip_vendor: bool):
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                if not skip_dir(entry, root, skip_vendor):
                    stack.append(entry)
                continue
            if looks_text(entry):
                yield entry


def staged_files(repo: Path, limit: Path | None) -> list[Path]:
    out = subprocess.check_output(
        [
            "git",
            "-C",
            str(repo),
            "diff",
            "--cached",
            "--name-only",
            "-z",
            "--diff-filter=ACMR",
        ],
    )
    paths: list[Path] = []
    for raw in out.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8", "surrogateescape")
        path = repo / rel
        if not path.is_file() or not looks_text(path):
            continue
        if limit is not None:
            try:
                path.resolve().relative_to(limit.resolve())
            except ValueError:
                continue
        paths.append(path)
    return paths


def restage(repo: Path, paths: list[Path]) -> None:
    if not paths:
        return
    rels = [p.resolve().relative_to(repo.resolve()).as_posix() for p in paths]
    subprocess.check_call(["git", "-C", str(repo), "add", "--"] + rels)


def write_lf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8"))


def install_hook(repo: Path) -> int:
    hook_text = HOOK.replace("\r\n", "\n")
    if not hook_text.endswith("\n"):
        hook_text += "\n"
    tracked = repo / ".githooks" / "pre-commit"
    active = repo / ".git" / "hooks" / "pre-commit"
    write_lf(tracked, hook_text)
    if active.exists():
        old = active.read_text(encoding="utf-8", errors="replace")
        if HOOK_MARKER not in old:
            write_lf(active, old.rstrip() + "\n\n" + hook_text)
        else:
            write_lf(active, hook_text)
    else:
        write_lf(active, hook_text)
    try:
        active.chmod(active.stat().st_mode | 0o111)
        tracked.chmod(tracked.stat().st_mode | 0o111)
    except OSError:
        pass
    print(f"installed {tracked.relative_to(repo)}")
    print(f"installed {active}")
    return 0


def report(
    root: Path,
    counts: Counter[str],
    by_top: Counter[str],
    dry_run: bool,
    quiet: bool,
) -> int:
    if not quiet:
        print()
        print(f"root: {root}")
        if by_top:
            print("changed by top-level:")
            for name, n in by_top.most_common():
                print(f"  {n:5}  {name}")
        print(
            f"fixed={counts['fixed']} would-fix={counts['would-fix']} "
            f"already-lf={counts['ok']} binary={counts['skip-binary']} "
            f"large={counts['skip-large']} error={counts['error']}"
        )
        if dry_run and counts["would-fix"]:
            print("re-run without --dry-run to write LF")
    elif counts["fixed"] or counts["would-fix"] or counts["error"]:
        print(
            f"LF normalize: fixed={counts['fixed']} "
            f"would-fix={counts['would-fix']} error={counts['error']}"
        )
    return 0 if counts["error"] == 0 else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert the repo to Unix LF")
    parser.add_argument("root", nargs="?", default=None, help="directory (default: repo root)")
    parser.add_argument("--dry-run", action="store_true", help="list files only")
    parser.add_argument("--quiet", action="store_true", help="print only when something changes")
    parser.add_argument("--staged", action="store_true", help="only staged files, then git add them")
    parser.add_argument("--install-hook", action="store_true", help="install git pre-commit hook")
    parser.add_argument(
        "--skip-vendor",
        action="store_true",
        help="skip PortMaster vendor libs and System Python packages",
    )
    args = parser.parse_args()

    repo = repo_root()
    if args.install_hook:
        return install_hook(repo)

    root = Path(args.root).resolve() if args.root else repo
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 1

    counts: Counter[str] = Counter()
    by_top: Counter[str] = Counter()
    shown = 0
    fixed_paths: list[Path] = []
    paths = staged_files(repo, root) if args.staged else list(walk(root, args.skip_vendor))
    for path in paths:
        status = convert(path, args.dry_run)
        key = status.split(":", 1)[0]
        counts[key] += 1
        if status == "fixed":
            fixed_paths.append(path)
        if status not in {"fixed", "would-fix"} and not status.startswith("error"):
            continue
        try:
            rel = path.relative_to(repo)
        except ValueError:
            rel = path
        by_top[rel.parts[0] if rel.parts else "."] += 1
        if not args.quiet:
            if shown < 80:
                print(f"{status:10} {rel}")
                shown += 1
            elif shown == 80:
                print("... (more files, see summary)")
                shown += 1

    if args.staged and fixed_paths and not args.dry_run:
        restage(repo, fixed_paths)

    return report(root, counts, by_top, args.dry_run, args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
