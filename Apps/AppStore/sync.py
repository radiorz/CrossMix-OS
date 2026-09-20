#!/usr/bin/env python3
"""Partial git sync for CrossMix AppStore.

Uses git sparse-checkout when git is available. Otherwise talks to
GitHub / Gitee / GitLab APIs and downloads only the requested path.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

APPDIR = Path(os.path.dirname(os.path.abspath(__file__)))
USER_AGENT = "CrossMix-AppStore/1.0"
CACHE_TTL = 15 * 60
SKIP_DIR_NAMES = {".git", "__pycache__"}
LARGE_HINTS = {"portmaster", "retroarch", "ppsspp", "apps", "emus"}
DEFAULT_GIT_URL = "https://github.com/cizia64/CrossMix-OS.git"
DEFAULT_ROOTS = ["Apps", "Emus"]

LogFn = Callable[[str], None]
StopFn = Callable[[], bool]


def sdcard_root() -> Path:
    env = os.environ.get("APPSTORE_ROOT", "").strip()
    if env:
        return Path(env)
    if Path("/mnt/SDCARD").is_dir():
        return Path("/mnt/SDCARD")
    parent = APPDIR.parent
    root = parent.parent
    if (root / "Apps").is_dir():
        return root
    return APPDIR


def data_dir() -> Path:
    path = APPDIR / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slug(text: str) -> str:
    out = re.sub(r"[^a-zA-Z0-9._-]+", "-", text.strip()).strip("-").lower()
    return out or "repo"


def which_git() -> str | None:
    env = os.environ.get("APPSTORE_GIT", "").strip()
    candidates = [env] if env else []
    candidates.extend(
        [
            shutil.which("git") or "",
            "/mnt/SDCARD/System/bin/git",
            "/usr/bin/git",
            "/usr/local/bin/git",
        ]
    )
    for cand in candidates:
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
        if cand and os.name == "nt" and os.path.isfile(cand):
            return cand
    return None


def parse_git_url(url: str) -> dict[str, str]:
    raw = (url or "").strip()
    if raw.endswith("/"):
        raw = raw[:-1]
    if raw.endswith(".git"):
        host_url = raw
    else:
        host_url = raw
    kind = "git"
    owner = ""
    repo = ""
    host = ""
    project = ""

    m = re.match(r"^git@([^:]+):(.+?)(?:\.git)?$", raw)
    if m:
        host, project = m.group(1), m.group(2)
    else:
        m = re.match(r"^https?://([^/]+)/(.+?)(?:\.git)?$", raw)
        if m:
            host, project = m.group(1), m.group(2)
        else:
            raise ValueError(f"无法识别的 git 地址: {url}")

    host = host.lower()
    project = project.strip("/")
    parts = [p for p in project.split("/") if p]
    if "github.com" in host:
        kind = "github"
        if len(parts) < 2:
            raise ValueError("GitHub 地址需要 owner/repo")
        owner, repo = parts[0], parts[1]
        project = f"{owner}/{repo}"
    elif "gitee.com" in host:
        kind = "gitee"
        if len(parts) < 2:
            raise ValueError("Gitee 地址需要 owner/repo")
        owner, repo = parts[0], parts[1]
        project = f"{owner}/{repo}"
    elif "gitlab" in host:
        kind = "gitlab"
        if len(parts) < 2:
            raise ValueError("GitLab 地址需要 group/project")
        owner, repo = parts[0], parts[-1]
        project = "/".join(parts)
    else:
        if len(parts) >= 2:
            owner, repo = parts[0], parts[-1]
            project = "/".join(parts)

    https = f"https://{host}/{project}"
    clone = https if https.endswith(".git") else https + ".git"
    return {
        "kind": kind,
        "host": host,
        "owner": owner,
        "repo": repo,
        "project": project,
        "https": clone,
        "clone": clone,
        "url": clone,
    }


@dataclass
class Source:
    id: str
    name: str
    url: str
    branch: str = "main"
    roots: list[str] = field(default_factory=lambda: list(DEFAULT_ROOTS))
    dest: str = ""
    token: str = ""
    enabled: bool = True
    kind: str = ""
    owner: str = ""
    repo: str = ""
    project: str = ""
    host: str = ""

    def refresh_identity(self) -> None:
        info = parse_git_url(self.url)
        if not self.kind:
            self.kind = info["kind"]
        self.owner = info["owner"]
        self.repo = info["repo"]
        self.project = info["project"]
        self.host = info["host"]
        if not self.name:
            self.name = f"{self.owner}/{self.repo}" if self.owner else self.repo or self.id

    def dest_root(self) -> Path:
        if self.dest:
            return Path(self.dest)
        return sdcard_root()

    def local_path(self, rel: str) -> Path:
        rel = (rel or "").replace("\\", "/").strip("/")
        root = self.dest_root()
        return root / rel if rel else root

    def clone_url(self) -> str:
        info = parse_git_url(self.url)
        clone = info["clone"]
        token = self.token or os.environ.get("APPSTORE_TOKEN", "").strip()
        if not token or not clone.startswith("https://"):
            return clone
        rest = clone[len("https://") :]
        user = "oauth2" if self.kind == "gitlab" else "x-access-token"
        return f"https://{user}:{urllib.parse.quote(token, safe='')}@{rest}"


@dataclass
class RemoteItem:
    name: str
    path: str
    type: str
    sha: str = ""
    size: int = 0


@dataclass
class InstallRecord:
    key: str
    source: str
    path: str
    dest: str
    sha: str
    files: int = 0
    bytes: int = 0
    time: str = ""
    backend: str = ""


class HttpError(RuntimeError):
    def __init__(self, message: str, code: int = 0):
        super().__init__(message)
        self.code = code


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl._create_unverified_context()
    return ctx


def http_bytes(url: str, token: str = "", accept: str = "") -> bytes:
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60, context=_ssl_context()) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", "replace")[:240]
        except Exception:
            pass
        if exc.code in (403, 429):
            raise HttpError(
                f"接口限流或拒绝 ({exc.code})。可在仓库里填写 Token，或稍后再试。 {body}",
                exc.code,
            )
        if exc.code == 404:
            raise HttpError(f"远程没有这个路径: {url}", 404)
        raise HttpError(f"HTTP {exc.code}: {body or url}", exc.code)
    except urllib.error.URLError as exc:
        # Device Python SSL / DNS may fail; fall back to curl / wget.
        fallback = _http_bytes_cmd(url, token)
        if fallback is not None:
            return fallback
        raise HttpError(f"网络失败: {exc.reason}") from exc


def _http_bytes_cmd(url: str, token: str = "") -> bytes | None:
    curl = shutil.which("curl")
    if curl:
        cmd = [curl, "-k", "-sL", "--max-time", "90", "-A", USER_AGENT, url]
        if token:
            cmd[1:1] = ["-H", f"Authorization: Bearer {token}"]
        try:
            out = subprocess.run(cmd, capture_output=True, timeout=100)
            if out.returncode == 0 and out.stdout:
                return out.stdout
        except Exception:
            pass
    wget = shutil.which("wget")
    if wget:
        cmd = [wget, "--no-check-certificate", "-q", "-O", "-", url]
        try:
            out = subprocess.run(cmd, capture_output=True, timeout=100)
            if out.returncode == 0 and out.stdout:
                return out.stdout
        except Exception:
            pass
    return None


def http_json(url: str, token: str = "") -> object:
    raw = http_bytes(url, token=token, accept="application/json")
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HttpError(f"远程返回的不是 JSON: {url}") from exc


def download_file(url: str, dest: Path, token: str = "", log: LogFn | None = None) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    data = http_bytes(url, token=token)
    tmp.write_bytes(data)
    tmp.replace(dest)
    if log:
        log(f"  {dest.name}  {len(data)}B")
    return len(data)


def load_json(path: Path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def run_git(git: str, args: list[str], cwd: Path | None = None, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    cmd = [git, "-c", "http.sslVerify=false", *args]
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


class Store:
    def __init__(self) -> None:
        self.appdir = APPDIR
        self.root = sdcard_root()
        self.catalog = load_json(APPDIR / "catalog.json", {"sources": [], "featured": []})
        self._user_sources = load_json(data_dir() / "sources.json", [])
        self._installed: dict[str, dict] = load_json(data_dir() / "installed.json", {})
        self._list_cache: dict[str, tuple[float, list[RemoteItem]]] = {}
        self._meta: dict[str, str] = {}
        for src in self.sources():
            try:
                src.refresh_identity()
            except ValueError:
                pass

    def sources(self) -> list[Source]:
        items: dict[str, Source] = {}
        for raw in self.catalog.get("sources", []):
            src = self._source_from_dict(raw)
            items[src.id] = src
        for raw in self._user_sources:
            src = self._source_from_dict(raw)
            items[src.id] = src
        return [s for s in items.values() if s.enabled]

    def all_sources(self) -> list[Source]:
        items: dict[str, Source] = {}
        for raw in list(self.catalog.get("sources", [])) + list(self._user_sources):
            src = self._source_from_dict(raw)
            items[src.id] = src
        return list(items.values())

    def get_source(self, sid: str) -> Source | None:
        for src in self.all_sources():
            if src.id == sid:
                return src
        return None

    def _source_from_dict(self, raw: dict) -> Source:
        roots = raw.get("roots") or list(DEFAULT_ROOTS)
        if isinstance(roots, str):
            roots = [p.strip() for p in roots.split(",") if p.strip()]
        src = Source(
            id=str(raw.get("id") or slug(raw.get("url", "repo"))),
            name=str(raw.get("name") or ""),
            url=str(raw.get("url") or ""),
            branch=str(raw.get("branch") or "main"),
            roots=list(roots),
            dest=str(raw.get("dest") or ""),
            token=str(raw.get("token") or ""),
            enabled=bool(raw.get("enabled", True)),
            kind=str(raw.get("kind") or ""),
        )
        try:
            src.refresh_identity()
        except ValueError:
            pass
        return src

    def save_user_sources(self) -> None:
        save_json(data_dir() / "sources.json", self._user_sources)

    def add_source(self, url: str, branch: str = "main", name: str = "", roots: list[str] | None = None) -> Source:
        info = parse_git_url(url)
        sid = slug(f"{info['kind']}-{info['project']}")
        existing = [s for s in self._user_sources if s.get("id") == sid]
        rec = {
            "id": sid,
            "name": name or f"{info['owner']}/{info['repo']}",
            "url": info["clone"],
            "branch": branch or "main",
            "roots": roots or list(DEFAULT_ROOTS),
            "enabled": True,
            "kind": info["kind"],
        }
        if existing:
            existing[0].update(rec)
        else:
            self._user_sources.append(rec)
        self.save_user_sources()
        src = self._source_from_dict(rec)
        return src

    def remove_source(self, sid: str) -> bool:
        before = len(self._user_sources)
        self._user_sources = [s for s in self._user_sources if s.get("id") != sid]
        if len(self._user_sources) != before:
            self.save_user_sources()
            return True
        return False

    def set_source_token(self, sid: str, token: str) -> bool:
        for raw in self._user_sources:
            if raw.get("id") == sid:
                raw["token"] = token
                self.save_user_sources()
                return True
        src = self.get_source(sid)
        if not src:
            return False
        rec = asdict(src)
        rec["token"] = token
        rec["roots"] = src.roots
        self._user_sources.append(
            {k: rec[k] for k in ("id", "name", "url", "branch", "roots", "dest", "token", "enabled", "kind")}
        )
        self.save_user_sources()
        return True

    def featured(self) -> list[dict]:
        return list(self.catalog.get("featured") or [])

    def catalog_meta(self, path: str) -> dict:
        path = path.replace("\\", "/").strip("/")
        for item in self.featured():
            if str(item.get("path", "")).replace("\\", "/").strip("/") == path:
                return item
        return {}

    def installed(self) -> dict[str, InstallRecord]:
        out: dict[str, InstallRecord] = {}
        for key, raw in self._installed.items():
            out[key] = InstallRecord(
                key=key,
                source=str(raw.get("source") or ""),
                path=str(raw.get("path") or ""),
                dest=str(raw.get("dest") or ""),
                sha=str(raw.get("sha") or ""),
                files=int(raw.get("files") or 0),
                bytes=int(raw.get("bytes") or 0),
                time=str(raw.get("time") or ""),
                backend=str(raw.get("backend") or ""),
            )
        return out

    def save_installed(self) -> None:
        save_json(data_dir() / "installed.json", self._installed)

    def record_key(self, source_id: str, path: str) -> str:
        return f"{source_id}:{path.replace('\\', '/').strip('/')}"

    def local_exists(self, source: Source, path: str) -> bool:
        dest = source.local_path(path)
        return dest.is_dir() or dest.is_file()

    def status(self, source: Source, path: str, remote_sha: str = "") -> str:
        dest = source.local_path(path)
        rec = self._installed.get(self.record_key(source.id, path))
        if rec:
            if remote_sha and rec.get("sha") and rec["sha"] != remote_sha:
                return "update"
            return "installed"
        if dest.is_dir() or dest.is_file():
            return "local"
        return "missing"

    def backend_for(self, source: Source, op: str = "install") -> str:
        git = which_git()
        if op == "list" and source.kind in {"github", "gitee", "gitlab"}:
            return source.kind
        if git:
            return "git"
        if source.kind in {"github", "gitee", "gitlab"}:
            return source.kind
        return ""

    def _try_backends(self, source: Source, op: str) -> list[str]:
        order: list[str] = []
        preferred = self.backend_for(source, op)
        if preferred:
            order.append(preferred)
        if source.kind in {"github", "gitee", "gitlab"} and source.kind not in order:
            order.append(source.kind)
        if which_git() and "git" not in order:
            order.append("git")
        return order

    def list_remote(self, source: Source, path: str = "", use_cache: bool = True) -> list[RemoteItem]:
        path = path.replace("\\", "/").strip("/")
        cache_key = f"{source.id}|{source.branch}|{path}"
        now = time.time()
        if use_cache and cache_key in self._list_cache:
            ts, items = self._list_cache[cache_key]
            if now - ts < CACHE_TTL:
                return items
        disk = data_dir() / "cache" / f"{slug(cache_key)}.json"
        if use_cache and disk.is_file() and now - disk.stat().st_mtime < CACHE_TTL:
            raw = load_json(disk, [])
            items = [RemoteItem(**x) for x in raw]
            self._list_cache[cache_key] = (now, items)
            return items

        last_err: Exception | None = None
        items: list[RemoteItem] | None = None
        for backend in self._try_backends(source, "list"):
            try:
                if backend == "git":
                    items = self._git_list(source, path)
                elif backend == "github":
                    items = self._github_list(source, path)
                elif backend == "gitee":
                    items = self._gitee_list(source, path)
                elif backend == "gitlab":
                    items = self._gitlab_list(source, path)
                else:
                    continue
                break
            except HttpError as exc:
                last_err = exc
                continue
        if items is None:
            raise last_err or HttpError("这个仓库需要本机有 git，或改用 GitHub / Gitee / GitLab 地址。")

        items = [it for it in items if it.name not in SKIP_DIR_NAMES]
        items.sort(key=lambda it: (0 if it.type == "dir" else 1, it.name.lower()))
        self._list_cache[cache_key] = (now, items)
        save_json(disk, [asdict(it) for it in items])
        return items

    def remote_sha(self, source: Source, path: str = "") -> str:
        path = path.replace("\\", "/").strip("/")
        backend = self.backend_for(source)
        try:
            if backend == "git":
                return self._git_sha(source, path)
            if backend == "github":
                return self._github_sha(source, path)
            if backend == "gitee":
                return self._gitee_sha(source, path)
            if backend == "gitlab":
                return self._gitlab_sha(source, path)
        except HttpError:
            return ""
        return ""

    def install(
        self,
        source: Source,
        path: str,
        log: LogFn | None = None,
        should_stop: StopFn | None = None,
    ) -> InstallRecord:
        path = path.replace("\\", "/").strip("/")
        dest = source.local_path(path)
        if dest.resolve() == self.root.resolve() and not path:
            raise HttpError("拒绝同步到 SD 卡根目录（请指定 Apps 或 Emus）。")
        emit = log or (lambda _m: None)
        stop = should_stop or (lambda: False)
        emit(f"同步 {source.name}  {path or '/'}")
        emit(f"目标  {dest}")

        last_err: Exception | None = None
        sha, files, nbytes = "", 0, 0
        backend = ""
        for backend in self._try_backends(source, "install"):
            emit(f"方式  {'git sparse-checkout' if backend == 'git' else backend + ' API'}")
            try:
                if backend == "git":
                    sha, files, nbytes = self._git_install(source, path, dest, emit, stop)
                elif backend in {"github", "gitee", "gitlab"}:
                    sha, files, nbytes = self._api_install(source, path, dest, emit, stop)
                else:
                    continue
                last_err = None
                break
            except HttpError as exc:
                last_err = exc
                emit(f"{backend} 失败: {exc}")
                continue
        if last_err is not None:
            raise last_err
        if not files and not dest.exists():
            raise HttpError("没有可用的同步方式。请安装 git，或改用 GitHub / Gitee / GitLab。")

        rec = InstallRecord(
            key=self.record_key(source.id, path),
            source=source.id,
            path=path,
            dest=str(dest),
            sha=sha,
            files=files,
            bytes=nbytes,
            time=now_iso(),
            backend=backend,
        )
        self._installed[rec.key] = asdict(rec)
        self.save_installed()
        emit(f"完成  {files} 个文件  {nbytes} 字节  {sha[:12] if sha else ''}")
        return rec

    def uninstall(self, source: Source, path: str) -> Path:
        dest = source.local_path(path)
        store_dir = APPDIR.resolve()
        try:
            if dest.resolve() == store_dir:
                raise HttpError("不能卸载应用商店自己。")
            if store_dir in dest.resolve().parents and dest.resolve() != store_dir:
                pass
        except FileNotFoundError:
            pass
        if dest.is_dir():
            shutil.rmtree(dest)
        elif dest.is_file():
            dest.unlink()
        key = self.record_key(source.id, path)
        if key in self._installed:
            del self._installed[key]
            self.save_installed()
        return dest

    def is_large_path(self, path: str) -> bool:
        name = path.replace("\\", "/").strip("/").lower()
        if name in LARGE_HINTS:
            return True
        last = name.split("/")[-1] if name else ""
        return last in LARGE_HINTS

    # --- git backend ---

    def _git_bin(self) -> str:
        git = which_git()
        if not git:
            raise HttpError("未找到 git")
        return git

    def _repo_cache(self, source: Source) -> Path:
        return data_dir() / "repos" / source.id

    def _ensure_sparse_repo(self, source: Source, log: LogFn | None = None) -> Path:
        git = self._git_bin()
        cache = self._repo_cache(source)
        emit = log or (lambda _m: None)
        if (cache / ".git").is_dir():
            pull = run_git(git, ["-C", str(cache), "pull", "--ff-only"], timeout=180)
            if pull.returncode != 0:
                emit("git pull 失败，继续用本地缓存")
            return cache
        cache.parent.mkdir(parents=True, exist_ok=True)
        if cache.exists():
            shutil.rmtree(cache)
        emit("git clone --filter=blob:none --sparse --depth=1")
        clone = run_git(
            git,
            [
                "clone",
                "--filter=blob:none",
                "--sparse",
                "--depth",
                "1",
                "-b",
                source.branch,
                source.clone_url(),
                str(cache),
            ],
            timeout=300,
        )
        if clone.returncode != 0:
            err = (clone.stderr or clone.stdout or "").strip()
            raise HttpError(f"git clone 失败: {err[:400]}")
        init = run_git(git, ["-C", str(cache), "sparse-checkout", "init", "--cone"])
        if init.returncode != 0:
            run_git(git, ["-C", str(cache), "sparse-checkout", "init"])
        roots = [p for p in (source.roots or DEFAULT_ROOTS) if p]
        if roots:
            run_git(git, ["-C", str(cache), "sparse-checkout", "set", *roots])
        return cache

    def _sparse_add(self, source: Source, path: str, log: LogFn | None = None) -> Path:
        git = self._git_bin()
        cache = self._ensure_sparse_repo(source, log)
        listed = run_git(git, ["-C", str(cache), "sparse-checkout", "list"])
        paths = {line.strip().replace("\\", "/") for line in (listed.stdout or "").splitlines() if line.strip()}
        if path:
            paths.add(path)
        if paths:
            setcmd = run_git(git, ["-C", str(cache), "sparse-checkout", "set", *sorted(paths)])
            if setcmd.returncode != 0:
                raise HttpError((setcmd.stderr or setcmd.stdout or "sparse-checkout set 失败")[:400])
        run_git(git, ["-C", str(cache), "pull", "--ff-only"], timeout=180)
        return cache

    def _git_list(self, source: Source, path: str) -> list[RemoteItem]:
        git = self._git_bin()
        cache = self._ensure_sparse_repo(source)
        spec = f"HEAD:{path}" if path else "HEAD:"
        out = run_git(git, ["-C", str(cache), "ls-tree", "--long", spec])
        if out.returncode != 0:
            raise HttpError(f"远程没有目录 {path or '/'}: {(out.stderr or '').strip()[:200]}")
        items: list[RemoteItem] = []
        for line in (out.stdout or "").splitlines():
            # <mode> <type> <sha> <size>\t<name>
            if "\t" not in line:
                continue
            meta, name = line.split("\t", 1)
            parts = meta.split()
            if len(parts) < 3:
                continue
            typ = "dir" if parts[1] == "tree" else "file"
            sha = parts[2]
            size = 0
            if len(parts) >= 4 and parts[3].isdigit():
                size = int(parts[3])
            rel = f"{path}/{name}" if path else name
            items.append(RemoteItem(name=name, path=rel, type=typ, sha=sha, size=size))
        return items

    def _git_sha(self, source: Source, path: str) -> str:
        git = self._git_bin()
        cache = self._ensure_sparse_repo(source)
        if path:
            out = run_git(git, ["-C", str(cache), "rev-parse", f"HEAD:{path}"])
            if out.returncode == 0:
                return (out.stdout or "").strip()
        out = run_git(git, ["-C", str(cache), "rev-parse", "HEAD"])
        return (out.stdout or "").strip() if out.returncode == 0 else ""

    def _git_install(
        self,
        source: Source,
        path: str,
        dest: Path,
        log: LogFn,
        should_stop: StopFn,
    ) -> tuple[str, int, int]:
        cache = self._sparse_add(source, path, log)
        src = cache / path if path else cache
        if not src.exists():
            raise HttpError(f"sparse checkout 后找不到 {path}")
        if should_stop():
            raise HttpError("已取消")
        files, nbytes = copy_tree(src, dest, log, should_stop)
        sha = self._git_sha(source, path)
        return sha, files, nbytes

    # --- host APIs ---

    def _token(self, source: Source) -> str:
        return source.token or os.environ.get("APPSTORE_TOKEN", "").strip()

    def _github_list(self, source: Source, path: str) -> list[RemoteItem]:
        q = urllib.parse.quote(path)
        url = f"https://api.github.com/repos/{source.project}/contents/{q}?ref={urllib.parse.quote(source.branch)}"
        data = http_json(url, token=self._token(source))
        if isinstance(data, dict) and data.get("type") == "file":
            return [
                RemoteItem(
                    name=str(data.get("name") or Path(path).name),
                    path=str(data.get("path") or path),
                    type="file",
                    sha=str(data.get("sha") or ""),
                    size=int(data.get("size") or 0),
                )
            ]
        if not isinstance(data, list):
            raise HttpError("GitHub 返回了无法识别的目录列表")
        items: list[RemoteItem] = []
        for it in data:
            typ = "dir" if it.get("type") == "dir" else "file"
            items.append(
                RemoteItem(
                    name=str(it.get("name") or ""),
                    path=str(it.get("path") or ""),
                    type=typ,
                    sha=str(it.get("sha") or ""),
                    size=int(it.get("size") or 0),
                )
            )
        return items

    def _github_sha(self, source: Source, path: str) -> str:
        token = self._token(source)
        if path:
            url = (
                f"https://api.github.com/repos/{source.project}/commits"
                f"?path={urllib.parse.quote(path)}&sha={urllib.parse.quote(source.branch)}&per_page=1"
            )
        else:
            url = f"https://api.github.com/repos/{source.project}/commits/{urllib.parse.quote(source.branch)}"
        data = http_json(url, token=token)
        if isinstance(data, list) and data:
            return str(data[0].get("sha") or "")
        if isinstance(data, dict):
            return str(data.get("sha") or "")
        return ""

    def _github_tree(self, source: Source, path: str) -> list[RemoteItem]:
        token = self._token(source)
        parent = str(Path(path).parent).replace("\\", "/") if path else ""
        name = Path(path).name if path else ""
        if parent in {".", ""}:
            parent = ""
        listing = self._github_list(source, parent)
        tree_sha = ""
        if path:
            for it in listing:
                if it.name == name:
                    tree_sha = it.sha
                    break
            if not tree_sha:
                # path is a file
                return [it for it in listing if it.name == name]
        else:
            url = f"https://api.github.com/repos/{source.project}/git/ref/heads/{urllib.parse.quote(source.branch)}"
            ref = http_json(url, token=token)
            if not isinstance(ref, dict):
                raise HttpError("无法读取分支")
            commit_sha = ref.get("object", {}).get("sha")
            commit = http_json(
                f"https://api.github.com/repos/{source.project}/git/commits/{commit_sha}",
                token=token,
            )
            tree_sha = str(commit.get("tree", {}).get("sha") or "")
        if not tree_sha:
            raise HttpError(f"找不到目录 {path}")
        tree = http_json(
            f"https://api.github.com/repos/{source.project}/git/trees/{tree_sha}?recursive=1",
            token=token,
        )
        if not isinstance(tree, dict):
            raise HttpError("无法读取文件树")
        if tree.get("truncated"):
            return []
        items: list[RemoteItem] = []
        for it in tree.get("tree") or []:
            if it.get("type") != "blob":
                continue
            rel = str(it.get("path") or "")
            full = f"{path}/{rel}" if path else rel
            items.append(
                RemoteItem(
                    name=Path(rel).name,
                    path=full,
                    type="file",
                    sha=str(it.get("sha") or ""),
                    size=int(it.get("size") or 0),
                )
            )
        return items

    def _gitee_list(self, source: Source, path: str) -> list[RemoteItem]:
        q = urllib.parse.quote(path)
        url = (
            f"https://gitee.com/api/v5/repos/{source.project}/contents/{q}"
            f"?ref={urllib.parse.quote(source.branch)}"
        )
        token = self._token(source)
        if token:
            url += f"&access_token={urllib.parse.quote(token)}"
        data = http_json(url)
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise HttpError("Gitee 返回了无法识别的目录列表")
        items: list[RemoteItem] = []
        for it in data:
            typ = "dir" if it.get("type") == "dir" else "file"
            items.append(
                RemoteItem(
                    name=str(it.get("name") or ""),
                    path=str(it.get("path") or ""),
                    type=typ,
                    sha=str(it.get("sha") or ""),
                    size=int(it.get("size") or 0),
                )
            )
        return items

    def _gitee_sha(self, source: Source, path: str) -> str:
        url = f"https://gitee.com/api/v5/repos/{source.project}/commits"
        params = [f"sha={urllib.parse.quote(source.branch)}", "per_page=1"]
        if path:
            params.append(f"path={urllib.parse.quote(path)}")
        token = self._token(source)
        if token:
            params.append(f"access_token={urllib.parse.quote(token)}")
        data = http_json(url + "?" + "&".join(params))
        if isinstance(data, list) and data:
            return str(data[0].get("sha") or "")
        return ""

    def _gitlab_api(self, source: Source) -> str:
        host = source.host or "gitlab.com"
        return f"https://{host}/api/v4"

    def _gitlab_project_id(self, source: Source) -> str:
        return urllib.parse.quote(source.project, safe="")

    def _gitlab_list(self, source: Source, path: str) -> list[RemoteItem]:
        pid = self._gitlab_project_id(source)
        url = (
            f"{self._gitlab_api(source)}/projects/{pid}/repository/tree"
            f"?ref={urllib.parse.quote(source.branch)}&per_page=100&path={urllib.parse.quote(path)}"
        )
        data = http_json(url, token=self._token(source))
        if not isinstance(data, list):
            raise HttpError("GitLab 返回了无法识别的目录列表")
        items: list[RemoteItem] = []
        for it in data:
            typ = "dir" if it.get("type") == "tree" else "file"
            name = str(it.get("name") or "")
            rel = f"{path}/{name}" if path else name
            items.append(
                RemoteItem(
                    name=name,
                    path=str(it.get("path") or rel),
                    type=typ,
                    sha=str(it.get("id") or ""),
                    size=0,
                )
            )
        return items

    def _gitlab_sha(self, source: Source, path: str) -> str:
        pid = self._gitlab_project_id(source)
        url = (
            f"{self._gitlab_api(source)}/projects/{pid}/repository/commits"
            f"?ref_name={urllib.parse.quote(source.branch)}&per_page=1"
        )
        if path:
            url += f"&path={urllib.parse.quote(path)}"
        data = http_json(url, token=self._token(source))
        if isinstance(data, list) and data:
            return str(data[0].get("id") or "")
        return ""

    def _raw_url(self, source: Source, path: str) -> str:
        path_q = "/".join(urllib.parse.quote(p) for p in path.split("/"))
        if source.kind == "github":
            return f"https://raw.githubusercontent.com/{source.project}/{source.branch}/{path_q}"
        if source.kind == "gitee":
            return f"https://gitee.com/{source.project}/raw/{source.branch}/{path_q}"
        host = source.host or "gitlab.com"
        return f"https://{host}/{source.project}/-/raw/{source.branch}/{path_q}"

    def _walk_files(self, source: Source, path: str, log: LogFn, should_stop: StopFn) -> list[RemoteItem]:
        backend = source.kind
        if backend == "github":
            tree = self._github_tree(source, path)
            if tree:
                return tree
        files: list[RemoteItem] = []
        stack = [path]
        seen: set[str] = set()
        while stack:
            if should_stop():
                raise HttpError("已取消")
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            listing = self.list_remote(source, cur, use_cache=False)
            # list_remote of a file returns one file
            if len(listing) == 1 and listing[0].type == "file" and listing[0].path == cur:
                files.append(listing[0])
                continue
            for it in listing:
                if it.type == "dir":
                    stack.append(it.path)
                else:
                    files.append(it)
            log(f"列出 {cur}  ({len(listing)} 项)")
        return files

    def _api_install(
        self,
        source: Source,
        path: str,
        dest: Path,
        log: LogFn,
        should_stop: StopFn,
    ) -> tuple[str, int, int]:
        files = self._walk_files(source, path, log, should_stop)
        if not files:
            raise HttpError(f"远程目录是空的: {path or '/'}")
        token = self._token(source)
        nbytes = 0
        count = 0
        prefix = path.strip("/")
        for idx, item in enumerate(files, 1):
            if should_stop():
                raise HttpError("已取消")
            rel = item.path
            if prefix and (rel == prefix or rel.startswith(prefix + "/")):
                inner = rel[len(prefix) :].lstrip("/")
            else:
                inner = Path(rel).name
            if not inner:
                inner = item.name
            target = dest / inner if prefix else source.dest_root() / rel
            if dest.is_file() or (len(files) == 1 and item.path == path):
                target = dest
            url = self._raw_url(source, item.path)
            log(f"[{idx}/{len(files)}] {item.path}")
            try:
                nbytes += download_file(url, target, token=token)
                count += 1
            except HttpError as exc:
                log(f"失败 {item.path}: {exc}")
                raise
        sha = self.remote_sha(source, path)
        return sha, count, nbytes


def copy_tree(src: Path, dest: Path, log: LogFn | None = None, should_stop: StopFn | None = None) -> tuple[int, int]:
    emit = log or (lambda _m: None)
    stop = should_stop or (lambda: False)
    files = 0
    nbytes = 0
    if src.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return 1, src.stat().st_size
    dest.mkdir(parents=True, exist_ok=True)
    for root, dirs, filenames in os.walk(src):
        if stop():
            raise HttpError("已取消")
        dirs[:] = [d for d in dirs if d not in SKIP_DIR_NAMES]
        rel = os.path.relpath(root, src)
        rel_parts = Path(rel).parts if rel != "." else ()
        if src.name == "AppStore" and "data" in rel_parts:
            dirs[:] = []
            continue
        target_root = dest if rel == "." else dest / rel
        target_root.mkdir(parents=True, exist_ok=True)
        for name in filenames:
            if stop():
                raise HttpError("已取消")
            if name.endswith(".pyc"):
                continue
            from_file = Path(root) / name
            to_file = target_root / name
            shutil.copy2(from_file, to_file)
            size = from_file.stat().st_size
            files += 1
            nbytes += size
            emit(f"  {from_file.relative_to(src)}")
    return files, nbytes


def _cli(argv: list[str]) -> int:
    store = Store()
    if not argv or argv[0] in {"-h", "--help", "help"}:
        print(
            "AppStore 部分同步\n"
            "  sync.py sources\n"
            "  sync.py list [source] [path]\n"
            "  sync.py install <source> <path>\n"
            "  sync.py uninstall <source> <path>\n"
            "  sync.py status <source> <path>\n"
            "  sync.py update\n"
        )
        return 0
    cmd = argv[0]
    if cmd == "sources":
        git = which_git()
        print(f"git: {git or '未安装（将用 GitHub/Gitee/GitLab 接口）'}")
        print(f"root: {store.root}")
        for src in store.sources():
            print(f"  {src.id:20}  {src.kind:7}  {src.name}  {src.url}  ({src.branch})")
        return 0
    if cmd == "list":
        sid = argv[1] if len(argv) > 1 else store.sources()[0].id
        path = argv[2] if len(argv) > 2 else ""
        src = store.get_source(sid)
        if not src:
            print("未知仓库", sid)
            return 1
        for it in store.list_remote(src, path):
            mark = "DIR " if it.type == "dir" else "FILE"
            print(f"{mark}  {it.path}")
        return 0
    if cmd == "install":
        if len(argv) < 3:
            print("usage: sync.py install <source> <path>")
            return 1
        src = store.get_source(argv[1])
        if not src:
            print("未知仓库")
            return 1
        rec = store.install(src, argv[2], log=print)
        print(rec)
        return 0
    if cmd == "uninstall":
        src = store.get_source(argv[1])
        if not src:
            print("未知仓库")
            return 1
        dest = store.uninstall(src, argv[2])
        print("removed", dest)
        return 0
    if cmd == "status":
        src = store.get_source(argv[1])
        if not src:
            print("未知仓库")
            return 1
        path = argv[2] if len(argv) > 2 else ""
        sha = store.remote_sha(src, path)
        print(store.status(src, path, sha), "sha", sha)
        return 0
    if cmd == "update":
        for rec in store.installed().values():
            src = store.get_source(rec.source)
            if not src:
                continue
            sha = store.remote_sha(src, rec.path)
            if sha and sha == rec.sha:
                print("ok", rec.path)
                continue
            print("update", rec.path)
            store.install(src, rec.path, log=print)
        return 0
    print("未知命令", cmd)
    return 1


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
