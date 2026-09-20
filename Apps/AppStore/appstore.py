#!/usr/bin/env python3
# AppStore — browse / install / update / uninstall CrossMix Apps & Emus
# from a git repo (sparse-checkout or GitHub/Gitee/GitLab API).

from __future__ import annotations

import os
import shutil
import struct
import sys
import threading
import time
from pathlib import Path

from icons import CARD_H, THUMB_W, category_icon, package_info, thumb_lines
from sync import DEFAULT_GIT_URL, DEFAULT_ROOTS, HttpError, Source, Store, which_git

IS_WIN = os.name == "nt"

RESET = "\033[0m"
BOLD = "\033[1m"
FG_TEXT = "\033[38;5;189m"
FG_MUTED = "\033[38;5;103m"
FG_ACCENT = "\033[38;5;79m"
FG_GREEN = "\033[38;5;114m"
FG_PEACH = "\033[38;5;216m"
FG_RED = "\033[38;5;210m"
FG_YELLOW = "\033[38;5;222m"
FG_BLUE = "\033[38;5;111m"
BG_BAR = "\033[48;5;236m"
BG_SEL = "\033[48;5;23m"
BG_KEY = "\033[48;5;238m"
BG_KEYSEL = "\033[48;5;29m"
BG_PANEL = "\033[48;5;234m"

STATUS_LABEL = {
    "missing": ("未安装", FG_MUTED),
    "installed": ("已安装", FG_GREEN),
    "update": ("可更新", FG_YELLOW),
    "local": ("本地有", FG_BLUE),
}


def disp_w(text: str) -> int:
    w = 0
    for ch in text:
        o = ord(ch)
        if o < 32:
            continue
        w += 2 if o > 127 else 1
    return w


def clip(text: str, width: int) -> str:
    if width <= 0:
        return ""
    out = []
    used = 0
    for ch in text:
        cw = disp_w(ch)
        if used + cw > width:
            break
        out.append(ch)
        used += cw
    if used < width:
        out.append(" " * (width - used))
    return "".join(out)


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "K", "M", "G", "T"):
        if size < 1024 or unit == "T":
            if unit == "B":
                return f"{int(size)}{unit}"
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{n}B"


class Key:
    __slots__ = ("label", "kind", "value", "wide")

    def __init__(self, label: str, kind: str, value: str = "", wide: int = 1):
        self.label = label
        self.kind = kind
        self.value = value if value else label
        self.wide = wide


def build_keyboard(shift: bool, sym: bool, kind: str) -> list[list[Key]]:
    if sym:
        rows = [
            [Key(c, "char") for c in "`~|\\/?<>"],
            [Key(c, "char") for c in "()[]{}#$"],
            [Key(c, "char") for c in "%&*=+;:"],
            [Key(c, "char") for c in "\"'_-@^"],
        ]
    elif shift:
        rows = [
            [Key(c, "char") for c in "!@#$%^&*()_+"],
            [Key(c, "char") for c in "QWERTYUIOP{}"],
            [Key(c, "char") for c in "ASDFGHJKL:\""],
            [Key(c, "char") for c in "ZXCVBNM<>?"],
        ]
    else:
        rows = [
            [Key(c, "char") for c in "1234567890-="],
            [Key(c, "char") for c in "qwertyuiop[]"],
            [Key(c, "char") for c in "asdfghjkl;'"],
            [Key(c, "char") for c in "zxcvbnm,./"],
        ]
    extras = [
        Key("TAB", "special", "tab", 2),
        Key("SPC", "special", "space", 2),
        Key("⌫", "special", "backspace", 2),
        Key("SHFT", "special", "shift", 2),
        Key("SYM", "special", "sym", 2),
        Key("OK", "special", "enter", 2),
    ]
    if kind == "url":
        prefixes = [
            Key("gh", "char", "https://github.com/", 2),
            Key("gitee", "char", "https://gitee.com/", 3),
            Key("gl", "char", "https://gitlab.com/", 2),
            Key(".git", "char", ".git", 2),
        ]
    elif kind == "path":
        prefixes = [
            Key("Apps", "char", "Apps", 2),
            Key("Emus", "char", "Emus", 2),
            Key("/", "char", "/", 1),
            Key("VLC", "char", "VLC", 2),
        ]
    else:
        prefixes = [
            Key("main", "char", "main", 2),
            Key("master", "char", "master", 3),
        ]
    return rows + [extras, prefixes]


class Box:
    __slots__ = ("x", "y", "w", "h")

    def __init__(self, x: int, y: int, w: int, h: int):
        self.x, self.y, self.w, self.h = x, y, w, h

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x + self.w and self.y <= y < self.y + self.h


class AppStoreUI:
    MORE = [
        ("看里面的应用 / 模拟器", "browse"),
        ("精选", "featured"),
        ("已安装", "installed"),
        ("更新全部", "update_all"),
        ("仓库管理", "sources"),
        ("帮助", "help"),
        ("退出", "quit"),
    ]

    def __init__(self) -> None:
        self.store = Store()
        self.screen = "home"
        self.status = f"默认 {DEFAULT_GIT_URL}"
        self.running = True
        self.w = 80
        self.h = 24
        self.idx = 0
        self.scroll = 0
        self.rows: list[dict] = []
        self.stack: list[tuple[str, str, int]] = []
        self.source: Source | None = self.store.sources()[0] if self.store.sources() else None
        self.remote_path = ""
        self.detail: dict | None = None
        self.confirm_title = ""
        self.confirm_body: list[str] = []
        self.confirm_action = ""
        self.confirm_payload: dict = {}
        self.confirm_idx = 0
        self.logs: list[str] = []
        self.log_lock = threading.Lock()
        self.busy = False
        self.progress_done = False
        self.stop_flag = False
        self.type_kind = "url"
        self.type_value = ""
        self.type_title = ""
        self.show_keys = True
        self.shift = False
        self.sym = False
        self.key_r = 0
        self.key_c = 0
        self.last_click = (0, 0, 0.0)
        self.help_lines = self._help_text()
        self.browse_all_root = False
        self._thumb_cache: dict[str, list[str]] = {}
        self.refresh_rows()

    def _help_text(self) -> list[str]:
        git = which_git() or "未安装"
        return [
            "AppStore  —  用 git 同步部分目录",
            "",
            "Git 可以只拉仓库里的一部分：",
            "  git clone --filter=blob:none --sparse --depth=1",
            "  git sparse-checkout set Apps   或   Emus/PSP",
            "",
            f"本机 git: {git}",
            "没有 git 时，商店会走 GitHub / Gitee / GitLab 接口，",
            "同样只下载你选的目录，不会拉整个 CrossMix。",
            "",
            f"默认仓库: {DEFAULT_GIT_URL}",
            f"默认稀疏路径: {'  '.join(DEFAULT_ROOTS)}",
            "自己的 fork：仓库管理 → 添加仓库（会优先存成 https://...git）",
            "",
            "A 同步选中的 Apps / Emus    → 进入看里面的包",
            "Y 同步    X 卸载    B 返回    MENU 退出",
        ]

    def log(self, msg: str) -> None:
        with self.log_lock:
            self.logs.append(msg)
            if len(self.logs) > 400:
                self.logs = self.logs[-300:]

    def should_stop(self) -> bool:
        return self.stop_flag

    def refresh_rows(self) -> None:
        if self.screen == "home":
            self.rows = self._home_rows()
        elif self.screen == "featured":
            self.rows = []
            for item in self.store.featured():
                src = self.store.get_source(str(item.get("source") or "")) or self.source
                if item.get("extra"):
                    others = [s for s in self.store.sources() if s.id != "crossmix"]
                    if others:
                        src = others[0]
                path = str(item.get("path") or "")
                st = self.store.status(src, path) if src else "missing"
                self.rows.append(self._pkg_row(src, path, str(item.get("name") or ""), str(item.get("desc") or ""), extra=bool(item.get("extra"))))
        elif self.screen == "browse":
            self.rows = self._browse_rows()
        elif self.screen == "installed":
            self.rows = []
            for rec in self.store.installed().values():
                src = self.store.get_source(rec.source)
                self.rows.append(self._pkg_row(src, rec.path, rec.path, rec.dest, status="installed", record=rec))
            if not self.rows:
                self.rows = [{"kind": "info", "label": "还没有从商店安装过东西"}]
        elif self.screen == "sources":
            self.rows = [{"kind": "action", "label": "+ 添加仓库", "action": "add_source"}]
            for src in self.store.all_sources():
                mark = "" if src.enabled else " [关]"
                self.rows.append(
                    {
                        "kind": "source",
                        "label": src.name + mark,
                        "desc": f"{src.kind}  {src.url}  ({src.branch})",
                        "source": src,
                    }
                )
        elif self.screen == "sync_roots":
            self.rows = []
            for src in self.store.sources():
                for root in src.roots:
                    self.rows.append(self._pkg_row(src, root, card=True, large=True))
            self.rows.append({"kind": "action", "label": "输入自定义路径…", "action": "type_path"})
        elif self.screen == "help":
            self.rows = [{"kind": "info", "label": line} for line in self.help_lines]
        self.idx = max(0, min(self.idx, max(0, len(self.rows) - 1)))

    def _home_rows(self) -> list[dict]:
        rows: list[dict] = []
        src = self.source or (self.store.sources()[0] if self.store.sources() else None)
        roots = list(src.roots) if src and src.roots else list(DEFAULT_ROOTS)
        for root in roots:
            if src:
                rows.append(self._pkg_row(src, root, card=True, large=True, action="sync_root"))
            else:
                rows.append({"kind": "info", "label": f"{root}  （还没有仓库）"})
        for label, action in self.MORE:
            rows.append({"kind": "home", "label": label, "action": action})
        return rows

    def _pkg_row(
        self,
        src: Source | None,
        path: str,
        label: str = "",
        desc: str = "",
        extra: bool = False,
        status: str = "",
        record=None,
        card: bool = False,
        large: bool = False,
        action: str = "",
        kind: str = "pkg",
    ) -> dict:
        path = (path or "").replace("\\", "/").strip("/")
        dest = src.local_path(path) if src else Path()
        info = package_info(dest, path) if src else {"label": path, "desc": "", "icon": None, "kind": "app"}
        icon = info.get("icon")
        if card and path in DEFAULT_ROOTS:
            cat = category_icon(path)
            if cat.is_file():
                icon = cat
        return {
            "kind": kind,
            "label": label or str(info.get("label") or path),
            "desc": desc or str(info.get("desc") or ""),
            "path": path,
            "source": src,
            "status": status or (self.store.status(src, path) if src else "missing"),
            "extra": extra,
            "record": record,
            "card": card,
            "large": large,
            "icon": icon,
            "icon_kind": str(info.get("kind") or "app"),
            "action": action,
        }

    def _browse_rows(self) -> list[dict]:
        if self.source is None:
            return [{"kind": "info", "label": "没有仓库。先到「仓库管理」添加。"}]
        rows: list[dict] = []
        if self.remote_path:
            rows.append({"kind": "action", "label": "..", "action": "up"})
            rows.append(
                self._pkg_row(
                    self.source,
                    self.remote_path,
                    label=f"同步当前目录  {self.remote_path}",
                    desc=str(self.source.local_path(self.remote_path)),
                    large=self.store.is_large_path(self.remote_path),
                    card=self.remote_path in DEFAULT_ROOTS,
                )
            )
        elif self.source.roots and not getattr(self, "browse_all_root", False):
            for root in self.source.roots:
                rows.append(
                    self._pkg_row(
                        self.source,
                        root,
                        card=True,
                        large=True,
                        action="sync_root",
                        kind="dir",
                    )
                )
            rows.append({"kind": "action", "label": "浏览仓库根目录（高级）", "action": "browse_all"})
            return rows
        if not self.remote_path and getattr(self, "browse_all_root", False):
            rows.append({"kind": "action", "label": "..", "action": "up"})
        try:
            items = self.store.list_remote(self.source, self.remote_path)
        except HttpError as exc:
            return rows + [{"kind": "info", "label": f"列出失败: {exc}"}]
        except Exception as exc:
            return rows + [{"kind": "info", "label": f"列出失败: {exc}"}]
        for it in items:
            meta = self.store.catalog_meta(it.path)
            if it.type == "dir":
                rows.append(
                    self._pkg_row(
                        self.source,
                        it.path,
                        label=str(meta.get("name") or ""),
                        desc=str(meta.get("desc") or ""),
                        kind="dir",
                    )
                )
            else:
                rows.append(
                    {
                        "kind": "file",
                        "label": it.name,
                        "desc": it.path,
                        "path": it.path,
                        "source": self.source,
                        "status": "missing",
                    }
                )
        return rows or [{"kind": "info", "label": "这个目录是空的"}]

    def current(self) -> dict:
        if not self.rows:
            return {}
        return self.rows[self.idx]

    def open_featured(self) -> None:
        self.screen = "featured"
        self.idx = 0
        self.scroll = 0
        self.status = "精选"
        self.refresh_rows()

    def open_browse(self, source: Source | None = None, path: str = "", push: bool = True) -> None:
        if source is None:
            srcs = self.store.sources()
            if not srcs:
                self.status = "没有仓库"
                return
            if len(srcs) > 1 and path == "" and source is None and self.screen != "sources":
                self.screen = "pick_source"
                self.rows = [
                    {
                        "kind": "source",
                        "label": s.name,
                        "desc": s.url,
                        "source": s,
                        "action": "browse_source",
                    }
                    for s in srcs
                ]
                self.idx = 0
                self.scroll = 0
                self.status = "选一个仓库浏览"
                return
            source = srcs[0]
        if push:
            self.stack.append((self.screen, self.remote_path, self.idx))
        self.source = source
        self.remote_path = path
        if path:
            self.browse_all_root = False
        self.screen = "browse"
        self.idx = 0
        self.scroll = 0
        self.status = f"{source.name}  /  {path or '根'}"
        self.refresh_rows()

    def browse_up(self) -> None:
        if not self.remote_path:
            if getattr(self, "browse_all_root", False):
                self.browse_all_root = False
                self.open_browse(self.source, "", push=False)
                return
            self.go_home()
            return
        parent = str(Path(self.remote_path).parent).replace("\\", "/")
        if parent in {".", ""}:
            parent = ""
        self.open_browse(self.source, parent, push=False)

    def open_installed(self) -> None:
        self.screen = "installed"
        self.idx = 0
        self.scroll = 0
        self.status = "已安装"
        self.refresh_rows()

    def open_sources(self) -> None:
        self.screen = "sources"
        self.idx = 0
        self.scroll = 0
        self.status = "仓库"
        self.refresh_rows()

    def open_sync_roots(self) -> None:
        self.screen = "sync_roots"
        self.idx = 0
        self.scroll = 0
        self.status = "同步整个目录"
        self.refresh_rows()

    def open_help(self) -> None:
        self.screen = "help"
        self.idx = 0
        self.scroll = 0
        self.status = "帮助"
        self.refresh_rows()

    def go_home(self) -> None:
        self.screen = "home"
        self.idx = 0
        self.scroll = 0
        self.stack = []
        self.status = "应用商店"
        self.refresh_rows()

    def open_detail(self, row: dict) -> None:
        src: Source | None = row.get("source")
        path = str(row.get("path") or "")
        if not src or not path:
            self.status = "没有可打开的包"
            return
        st = self.store.status(src, path)
        meta = self.store.catalog_meta(path)
        dest = src.local_path(path)
        self.detail = {
            "source": src,
            "path": path,
            "name": row.get("label") or meta.get("name") or Path(path).name,
            "desc": row.get("desc") or meta.get("desc") or "",
            "status": st,
            "dest": str(dest),
            "backend": self.store.backend_for(src) or "无",
        }
        self.stack.append((self.screen, self.remote_path, self.idx))
        self.screen = "detail"
        self.rows = [
            {"kind": "action", "label": "安装 / 更新", "action": "install"},
            {"kind": "action", "label": "卸载", "action": "uninstall"},
            {"kind": "action", "label": "进入目录", "action": "enter"},
            {"kind": "action", "label": "返回", "action": "back"},
        ]
        self.idx = 0
        self.scroll = 0
        self.status = path

    def ask_confirm(self, title: str, body: list[str], action: str, payload: dict) -> None:
        if self.screen != "confirm":
            self.stack.append((self.screen, self.remote_path, self.idx))
        self.confirm_title = title
        self.confirm_body = body
        self.confirm_action = action
        self.confirm_payload = payload
        self.confirm_idx = 0
        self.screen = "confirm"

    def begin_type(self, kind: str, title: str, value: str = "") -> None:
        self.stack.append((self.screen, self.remote_path, self.idx))
        self.screen = "type"
        self.type_kind = kind
        self.type_title = title
        self.type_value = value
        self.show_keys = True
        self.shift = False
        self.sym = False
        self.key_r = 0
        self.key_c = 0
        self.status = title

    def submit_type(self) -> None:
        value = self.type_value.strip()
        kind = self.type_kind
        self.screen = "home"
        if self.stack:
            prev = self.stack.pop()
            self.screen = prev[0]
            self.remote_path = prev[1]
            self.idx = prev[2]
        if kind == "url":
            if not value:
                self.status = "地址为空"
                self.refresh_rows()
                return
            self._pending_url = value
            self.begin_type("branch", "分支（默认 main）", "main")
            return
        if kind == "branch":
            url = getattr(self, "_pending_url", "")
            try:
                src = self.store.add_source(url, branch=value or "main")
                self.source = src
                self.status = f"已添加 {src.name}"
            except Exception as exc:
                self.status = f"添加失败: {exc}"
            self.screen = "sources"
            self.idx = 0
            self.refresh_rows()
            return
        if kind == "token":
            src = self.confirm_payload.get("source") or self.source
            if src and self.store.set_source_token(src.id, value):
                self.status = "已保存 Token"
            else:
                self.status = "保存 Token 失败"
            self.screen = "sources"
            self.refresh_rows()
            return
        if kind == "path":
            src = self.source or (self.store.sources()[0] if self.store.sources() else None)
            if not src or not value:
                self.status = "路径或仓库为空"
                self.refresh_rows()
                return
            self.ask_install(src, value)
            return
        self.refresh_rows()

    def ask_install(self, source: Source, path: str) -> None:
        dest = source.local_path(path)
        body = [
            f"仓库: {source.name}",
            f"远程: {path}",
            f"本地: {dest}",
            f"方式: {self.store.backend_for(source) or '无后端'}",
        ]
        if self.store.is_large_path(path):
            body.append("")
            body.append("这个目录可能很大，只同步这一棵子树，")
            body.append("不会下载整个 CrossMix 仓库。")
        self.ask_confirm("确认同步？", body, "install", {"source": source, "path": path})

    def ask_uninstall(self, source: Source, path: str) -> None:
        dest = source.local_path(path)
        self.ask_confirm(
            "确认卸载？",
            [f"将删除 {dest}", "本地改过的文件也会没。"],
            "uninstall",
            {"source": source, "path": path},
        )

    def run_confirm(self) -> None:
        action = self.confirm_action
        payload = self.confirm_payload
        if action == "install":
            self.start_job("install", payload)
        elif action == "uninstall":
            src, path = payload["source"], payload["path"]
            try:
                dest = self.store.uninstall(src, path)
                self.status = f"已删除 {dest}"
            except HttpError as exc:
                self.status = str(exc)
            if self.stack:
                prev = self.stack.pop()
                self.screen = prev[0]
                self.remote_path = prev[1]
                self.idx = prev[2]
            self.refresh_rows()
        elif action == "update_all":
            self.start_job("update_all", {})
        elif action == "remove_source":
            sid = payload["source"].id
            if self.store.remove_source(sid):
                self.status = "已移除仓库"
            else:
                self.status = "内置仓库不能删，只能在 data/sources.json 里关"
            if self.stack:
                prev = self.stack.pop()
                self.screen = prev[0]
                self.idx = prev[2]
            else:
                self.screen = "sources"
            self.refresh_rows()
        else:
            self.go_back()

    def start_job(self, kind: str, payload: dict) -> None:
        if self.busy:
            self.status = "正在忙"
            return
        self.busy = True
        self.progress_done = False
        self.stop_flag = False
        with self.log_lock:
            self.logs = []
        self.screen = "progress"
        self.status = "同步中"
        threading.Thread(target=self._job, args=(kind, payload), daemon=True).start()

    def _job(self, kind: str, payload: dict) -> None:
        try:
            if kind == "install":
                self.store.install(payload["source"], payload["path"], log=self.log, should_stop=self.should_stop)
            elif kind == "update_all":
                recs = list(self.store.installed().values())
                if not recs:
                    self.log("没有已安装的包")
                for rec in recs:
                    if self.stop_flag:
                        raise HttpError("已取消")
                    src = self.store.get_source(rec.source)
                    if not src:
                        self.log(f"跳过 {rec.path}（仓库没了）")
                        continue
                    sha = ""
                    try:
                        sha = self.store.remote_sha(src, rec.path)
                    except Exception as exc:
                        self.log(f"检查失败 {rec.path}: {exc}")
                    if sha and sha == rec.sha:
                        self.log(f"已是最新  {rec.path}")
                        continue
                    self.log(f"更新  {rec.path}")
                    self.store.install(src, rec.path, log=self.log, should_stop=self.should_stop)
        except HttpError as exc:
            self.log(f"错误: {exc}")
            self.status = str(exc)
        except Exception as exc:
            self.log(f"错误: {exc}")
            self.status = str(exc)
        finally:
            self.busy = False
            self.progress_done = True
            if self.status == "同步中":
                self.status = "完成，按 B 返回"

    def activate(self) -> None:
        if self.screen == "confirm":
            if self.confirm_idx == 0:
                self.run_confirm()
            else:
                self.go_back()
            return
        if self.screen == "type":
            if self.show_keys:
                rows = self.keyboard()
                self.press_key(rows[self.key_r][self.key_c])
            else:
                self.submit_type()
            return
        if self.screen == "progress":
            if self.progress_done:
                self.go_back()
            return
        if self.screen == "detail":
            action = self.current().get("action")
            src = self.detail["source"] if self.detail else None
            path = self.detail["path"] if self.detail else ""
            if action == "install" and src:
                self.ask_install(src, path)
            elif action == "uninstall" and src:
                self.ask_uninstall(src, path)
            elif action == "enter" and src:
                self.open_browse(src, path if True else path, push=True)
                # if path is a file, stay
            elif action == "back":
                self.go_back()
            return
        row = self.current()
        kind = row.get("kind")
        action = row.get("action")
        if self.screen == "home":
            if action == "sync_root" or row.get("card"):
                if row.get("source") and row.get("path"):
                    self.ask_install(row["source"], row["path"])
                return
            self.handle_home(action or "")
            return
        if action == "sync_root":
            if row.get("source") and row.get("path"):
                self.ask_install(row["source"], row["path"])
            return
        if action == "add_source":
            self.begin_type("url", "仓库 git 地址")
            return
        if action == "type_path":
            self.begin_type("path", "要同步的路径，例如 Apps 或 Emus/PSP")
            return
        if action == "up":
            self.browse_up()
            return
        if action == "browse_all":
            self.browse_all_root = True
            self.open_browse(self.source, "", push=False)
            return
        if action == "browse_source" or (kind == "source" and self.screen == "pick_source"):
            self.open_browse(row.get("source"), "", push=False)
            return
        if kind == "dir":
            self.open_browse(row.get("source"), row.get("path") or "", push=True)
            return
        if kind == "pkg":
            self.open_detail(row)
            return
        if kind == "source" and self.screen == "sources":
            src = row.get("source")
            if src:
                self.open_browse(src, "", push=True)
            return

    def handle_home(self, action: str) -> None:
        if action == "featured":
            self.open_featured()
        elif action == "browse":
            self.open_browse()
        elif action == "installed":
            self.open_installed()
        elif action == "update_all":
            n = len(self.store.installed())
            self.ask_confirm("更新全部已安装？", [f"共 {n} 个包，只拉有变动的目录。"], "update_all", {})
        elif action == "sync_roots":
            self.open_sync_roots()
        elif action == "sources":
            self.open_sources()
        elif action == "help":
            self.open_help()
        elif action == "quit":
            self.running = False

    def go_back(self) -> None:
        if self.screen == "progress" and self.busy:
            self.stop_flag = True
            self.status = "正在取消…"
            return
        if self.screen == "type":
            if self.stack:
                prev = self.stack.pop()
                self.screen = prev[0]
                self.remote_path = prev[1]
                self.idx = prev[2]
                self.refresh_rows()
                return
        if self.screen == "confirm":
            if self.stack:
                prev = self.stack.pop()
                self.screen = prev[0]
                self.remote_path = prev[1]
                self.idx = prev[2]
            else:
                self.screen = "home"
            self.refresh_rows()
            return
        if self.screen == "browse" and self.remote_path:
            self.browse_up()
            return
        if self.stack:
            prev = self.stack.pop()
            self.screen = prev[0]
            self.remote_path = prev[1]
            self.idx = prev[2]
            if self.screen == "browse":
                self.refresh_rows()
                return
            self.refresh_rows()
            return
        if self.screen != "home":
            self.go_home()
            return
        self.running = False

    def yank_install(self) -> None:
        row = self.current()
        if self.screen == "detail" and self.detail:
            self.ask_install(self.detail["source"], self.detail["path"])
            return
        if row.get("kind") in {"pkg", "dir"} and row.get("source") and row.get("path"):
            self.ask_install(row["source"], row["path"])
            return
        self.status = "这一行不能安装"

    def yank_uninstall(self) -> None:
        row = self.current()
        if self.screen == "sources":
            src = row.get("source")
            if src:
                self.ask_confirm("移除这个仓库？", [src.name, src.url], "remove_source", {"source": src})
            return
        if self.screen == "detail" and self.detail:
            self.ask_uninstall(self.detail["source"], self.detail["path"])
            return
        if row.get("kind") in {"pkg", "dir"} and row.get("source") and row.get("path"):
            self.ask_uninstall(row["source"], row["path"])
            return
        self.status = "这一行不能卸载"

    def keyboard(self) -> list[list[Key]]:
        return build_keyboard(self.shift, self.sym, self.type_kind)

    def press_key(self, key: Key) -> None:
        if key.kind == "char":
            self.type_value += key.value
            if self.shift:
                self.shift = False
            return
        act = key.value
        if act == "space":
            self.type_value += " "
        elif act == "tab":
            self.type_value += "/"
        elif act == "backspace":
            self.type_value = self.type_value[:-1]
        elif act == "enter":
            self.submit_type()
        elif act == "shift":
            self.shift = not self.shift
            self.sym = False
        elif act == "sym":
            self.sym = not self.sym
            self.shift = False

    def move(self, delta: int) -> None:
        if self.screen == "confirm":
            self.confirm_idx = 0 if delta < 0 else 1
            return
        if not self.rows:
            return
        self.idx = max(0, min(len(self.rows) - 1, self.idx + delta))

    def move_key(self, dr: int, dc: int) -> None:
        rows = self.keyboard()
        self.key_r = max(0, min(len(rows) - 1, self.key_r + dr))
        row = rows[self.key_r]
        self.key_c = max(0, min(len(row) - 1, self.key_c + dc))

    def handle_key(self, key: str) -> None:
        if key in ("CTRL_C", "CTRL_Q"):
            self.running = False
            return
        if self.screen == "type":
            self.handle_type_key(key)
            return
        if key == "ESC":
            self.go_back()
            return
        if self.screen == "progress":
            if key in ("ESC", "BACKSPACE", "ENTER"):
                self.go_back()
            return
        if key == "UP":
            self.move(-1)
        elif key == "DOWN":
            self.move(1)
        elif key == "PGUP":
            self.move(-8)
        elif key == "PGDN":
            self.move(8)
        elif key == "HOME":
            self.idx = 0
        elif key == "END":
            self.idx = max(0, len(self.rows) - 1)
        elif key in ("ENTER", " "):
            self.activate()
        elif key == "RIGHT":
            row = self.current()
            if row.get("card") and row.get("source") and row.get("path"):
                self.open_browse(row["source"], row["path"], push=True)
            else:
                self.activate()
        elif key in ("LEFT", "BACKSPACE"):
            self.go_back()
        elif key in ("y", "Y"):
            if self.screen == "confirm":
                self.confirm_idx = 0
                self.run_confirm()
            elif self.screen == "sources":
                self.begin_type("url", "仓库 git 地址")
            else:
                self.yank_install()
        elif key in ("x", "X"):
            if self.screen == "confirm":
                self.go_back()
            else:
                self.yank_uninstall()
        elif key in ("n", "N"):
            src = None
            if self.current().get("source"):
                src = self.current()["source"]
            elif self.source:
                src = self.source
            if src:
                self.confirm_payload = {"source": src}
                self.begin_type("token", f"{src.name} 的 Token（可空）")
        elif key == "F5":
            self.store._list_cache.clear()
            self.refresh_rows()
            self.status = "已刷新"
        elif key in ("h", "H"):
            self.open_help()

    def handle_type_key(self, key: str) -> None:
        if key == "ESC":
            self.go_back()
            return
        if self.show_keys and key in ("UP", "DOWN", "LEFT", "RIGHT"):
            dr = -1 if key == "UP" else 1 if key == "DOWN" else 0
            dc = -1 if key == "LEFT" else 1 if key == "RIGHT" else 0
            self.move_key(dr, dc)
            return
        if key in ("ENTER", " "):
            if self.show_keys:
                rows = self.keyboard()
                self.press_key(rows[self.key_r][self.key_c])
            else:
                self.submit_type()
            return
        if key == "BACKSPACE":
            self.type_value = self.type_value[:-1]
            return
        if key == "TAB":
            self.show_keys = not self.show_keys
            return
        if len(key) == 1 and key.isprintable():
            self.type_value += key

    def handle_click(self, x: int, y: int, button: int) -> None:
        now = time.time()
        double = (x, y) == self.last_click[:2] and now - self.last_click[2] < 0.45
        self.last_click = (x, y, now)
        lay = self.layout()
        if button in (64, 65):
            self.move(-3 if button == 64 else 3)
            return
        if self.screen == "type" and self.show_keys and lay["keys"].contains(x, y):
            hit = self.key_at(x, y, lay["keys"])
            if hit is not None:
                self.key_r, self.key_c = hit
                self.press_key(self.keyboard()[self.key_r][self.key_c])
            return
        if lay["list"].contains(x, y):
            rel = y - lay["list"].y
            if self.screen == "confirm":
                self.confirm_idx = 0 if rel < lay["list"].h - 2 else 1
                if double:
                    self.activate()
                return
            idx = self._index_at_y(rel)
            if idx is not None:
                self.idx = idx
                if double:
                    self.activate()

    def key_at(self, x: int, y: int, box: Box) -> tuple[int, int] | None:
        rows = self.keyboard()
        inner_w = max(8, box.w - 2)
        rel_y = y - box.y
        if rel_y < 0 or rel_y >= len(rows):
            return None
        row = rows[rel_y]
        total = sum(max(3, k.wide * 3 + 1) for k in row)
        pad = max(0, (inner_w - total) // 2)
        cx = box.x + 1 + pad
        for c, key in enumerate(row):
            kw = max(3, key.wide * 3 + 1)
            if cx <= x < cx + kw:
                return rel_y, c
            cx += kw
        return None

    def size(self) -> tuple[int, int]:
        try:
            if not IS_WIN:
                import fcntl
                import termios

                h, w, _, _ = struct.unpack(
                    "HHHH",
                    fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, b"\x00" * 8),
                )
                if w and h:
                    return max(60, w), max(18, h)
        except Exception:
            pass
        sz = shutil.get_terminal_size((100, 32))
        return max(60, sz.columns), max(18, sz.lines)

    def layout(self) -> dict[str, Box]:
        w, h = self.w, self.h
        key_h = 8 if self.screen == "type" and self.show_keys else 0
        return {
            "title": Box(0, 0, w, 1),
            "list": Box(0, 1, w, max(4, h - 2 - key_h)),
            "keys": Box(0, h - 1 - key_h, w, key_h),
            "help": Box(0, h - 1, w, 1),
        }

    def bar(self, left: str, right: str, width: int, style: str) -> str:
        room = max(0, width - disp_w(right))
        return style + clip(left, room) + clip(right, min(disp_w(right), width)) + RESET

    def draw(self) -> str:
        self.w, self.h = self.size()
        lay = self.layout()
        titles = {
            "home": "应用商店  ·  Apps / Emus",
            "featured": "精选应用",
            "browse": f"浏览  {self.source.name if self.source else ''} / {self.remote_path or ''}",
            "pick_source": "选择仓库",
            "installed": "已安装",
            "sources": "仓库管理",
            "sync_roots": "同步 Apps / Emus",
            "detail": (self.detail or {}).get("name") or "详情",
            "confirm": self.confirm_title or "确认",
            "progress": "同步进度",
            "type": self.type_title or "输入",
            "help": "帮助",
        }
        buf = ["\033[?25l\033[H"]
        buf.append(self.bar("  " + titles.get(self.screen, "AppStore"), f"{self.status}  ", self.w, BG_BAR + BOLD + FG_ACCENT))
        if self.screen == "confirm":
            self.draw_confirm(buf, lay["list"])
        elif self.screen == "progress":
            self.draw_progress(buf, lay["list"])
        elif self.screen == "type":
            self.draw_type(buf, lay["list"])
            if self.show_keys:
                self.draw_keys(buf, lay["keys"])
        elif self.screen == "detail":
            self.draw_detail(buf, lay["list"])
        else:
            self.draw_list(buf, lay["list"])
        help_l = self.help_line()
        buf.append(f"\033[{self.h};1H")
        git = "git" if which_git() else "API"
        buf.append(self.bar(help_l, f" {git} ", self.w, BG_BAR + FG_MUTED))
        return "".join(buf)

    def help_line(self) -> str:
        if self.screen == "type":
            return " 方向选键  A输入/确定  B退格  Select关键盘  MENU取消 "
        if self.screen == "confirm":
            return " 左右选  A确定  B取消 "
        if self.screen == "progress":
            return " B返回/取消   同步只拉当前目录 "
        if self.screen == "sources":
            return " A浏览  Y添加仓库  X移除  N填Token  B返回 "
        if self.screen in {"featured", "browse", "installed", "sync_roots"}:
            return " A详情/进入  Y安装  X卸载  B返回  MENU退出 "
        if self.screen == "detail":
            return " A执行  Y安装  X卸载  B返回 "
        if self.screen == "home":
            return " A同步 Apps/Emus   →看里面   Y同步   X卸载   MENU退出 "
        return " A确认  B返回  Y安装  X卸载  MENU退出 "

    def _item_h(self, item: dict) -> int:
        return CARD_H if item.get("card") else 1

    def _ensure_scroll(self, view_h: int) -> None:
        if not self.rows:
            self.scroll = 0
            return
        self.idx = max(0, min(len(self.rows) - 1, self.idx))
        if self.idx < self.scroll:
            self.scroll = self.idx
            return
        used = 0
        start = self.scroll
        while start <= self.idx:
            used += self._item_h(self.rows[start])
            start += 1
        while used > view_h and self.scroll < self.idx:
            used -= self._item_h(self.rows[self.scroll])
            self.scroll += 1

    def _index_at_y(self, rel_y: int) -> int | None:
        y = 0
        for i in range(self.scroll, len(self.rows)):
            h = self._item_h(self.rows[i])
            if y <= rel_y < y + h:
                return i
            y += h
        return None

    def _thumb(self, item: dict) -> list[str]:
        icon = item.get("icon")
        key = str(icon) if icon else f"fb:{item.get('icon_kind')}"
        cached = self._thumb_cache.get(key)
        if cached:
            return cached
        path = Path(icon) if icon else None
        lines = thumb_lines(path if path and path.is_file() else None, str(item.get("icon_kind") or "app"))
        self._thumb_cache[key] = lines
        return lines

    def draw_list(self, buf: list[str], box: Box) -> None:
        view_h = max(1, box.h)
        self._ensure_scroll(view_h)
        y_off = 0
        idx = self.scroll
        while y_off < view_h:
            y = box.y + y_off
            if idx >= len(self.rows):
                buf.append(f"\033[{y + 1};1H")
                buf.append(BG_PANEL + clip("", box.w) + RESET)
                y_off += 1
                continue
            item = self.rows[idx]
            h = self._item_h(item)
            if item.get("card"):
                self.draw_card(buf, box, y, h, item, idx == self.idx)
            else:
                self.draw_plain(buf, box, y, item, idx == self.idx)
            y_off += h
            idx += 1

    def draw_plain(self, buf: list[str], box: Box, y: int, item: dict, selected: bool) -> None:
        st = item.get("status")
        badge = ""
        badge_w = 0
        style_badge = ""
        if st in STATUS_LABEL:
            label, color = STATUS_LABEL[st]
            badge = f" {label} "
            badge_w = disp_w(badge)
            style_badge = color
        mark = "▸ " if item.get("kind") in {"dir", "home", "action"} else "  "
        text = mark + str(item.get("label") or "")
        desc = str(item.get("desc") or "")
        if desc and item.get("kind") != "info":
            room = box.w - badge_w - disp_w(text) - 2
            if room > 8:
                text = text + "  " + desc
        if selected:
            style = BG_SEL + BOLD + FG_TEXT
        elif item.get("kind") == "info":
            style = BG_PANEL + FG_MUTED
        elif item.get("kind") in {"dir", "action", "home"}:
            style = BG_PANEL + FG_ACCENT
        else:
            style = BG_PANEL + FG_TEXT
        buf.append(f"\033[{y + 1};1H")
        if badge:
            buf.append(style + clip(text, box.w - badge_w) + (style if selected else BG_PANEL) + style_badge + clip(badge, badge_w) + RESET)
        else:
            buf.append(style + clip(text, box.w) + RESET)

    def draw_card(self, buf: list[str], box: Box, y: int, h: int, item: dict, selected: bool) -> None:
        thumb = self._thumb(item)
        st = item.get("status")
        badge, bcolor = STATUS_LABEL.get(st, ("", FG_MUTED))
        title = str(item.get("label") or item.get("path") or "")
        desc = str(item.get("desc") or "")
        path = str(item.get("path") or "")
        bg = BG_SEL if selected else BG_PANEL
        fg = BOLD + FG_TEXT if selected else FG_TEXT
        icon_w = THUMB_W
        texts = [
            title,
            desc or path,
            "A 同步这一项    → 看里面的包",
            f"路径 {path}" if path else "",
        ]
        style = bg + fg
        for row in range(h):
            yy = y + row
            if yy >= box.y + box.h:
                break
            buf.append(f"\033[{yy + 1};1H")
            icon = thumb[row] if row < len(thumb) else (bg + (" " * icon_w) + RESET)
            mid = bg + " "
            if row == 0:
                badge_txt = f" {badge} " if badge else ""
                room = box.w - icon_w - 2 - disp_w(badge_txt)
                buf.append(bg + " " + RESET + icon + mid + style + clip(title, room) + bcolor + badge_txt + RESET)
            else:
                line = texts[row] if row < len(texts) else ""
                buf.append(bg + " " + RESET + icon + mid + style + clip(line, box.w - icon_w - 2) + RESET)

    def draw_detail(self, buf: list[str], box: Box) -> None:
        d = self.detail or {}
        st = d.get("status") or "missing"
        slabel, scolor = STATUS_LABEL.get(st, (st, FG_MUTED))
        info = [
            f"名称   {d.get('name')}",
            f"路径   {d.get('path')}",
            f"仓库   {getattr(d.get('source'), 'name', '')}  {getattr(d.get('source'), 'url', '')}",
            f"状态   {slabel}",
            f"安装到 {d.get('dest')}",
            f"后端   {d.get('backend')}",
            "",
            str(d.get("desc") or ""),
        ]
        actions_from = max(0, box.h - 4)
        for row in range(box.h):
            buf.append(f"\033[{box.y + 1 + row};1H")
            if row < actions_from and row < len(info):
                style = BG_PANEL + (scolor if row == 3 else FG_TEXT)
                buf.append(style + clip("  " + info[row], box.w) + RESET)
                continue
            aidx = row - actions_from
            if 0 <= aidx < len(self.rows):
                item = self.rows[aidx]
                sel = self.idx == aidx
                style = (BG_SEL + BOLD + FG_TEXT) if sel else (BG_PANEL + FG_ACCENT)
                buf.append(style + clip("  › " + item["label"], box.w) + RESET)
            else:
                buf.append(BG_PANEL + clip("", box.w) + RESET)

    def draw_confirm(self, buf: list[str], box: Box) -> None:
        lines = [self.confirm_title, ""] + self.confirm_body
        for row in range(box.h):
            buf.append(f"\033[{box.y + 1 + row};1H")
            if row < len(lines):
                buf.append(BG_PANEL + FG_TEXT + clip("  " + lines[row], box.w) + RESET)
            elif row == box.h - 2:
                yes = "  确定  " if self.confirm_idx == 0 else "  确定  "
                no = "  取消  "
                ystyle = (BG_SEL + BOLD + FG_GREEN) if self.confirm_idx == 0 else (BG_PANEL + FG_GREEN)
                nstyle = (BG_SEL + BOLD + FG_RED) if self.confirm_idx == 1 else (BG_PANEL + FG_RED)
                pad = max(0, box.w - disp_w(yes) - disp_w(no) - 4)
                buf.append(BG_PANEL + "  " + ystyle + yes + RESET + BG_PANEL + (" " * pad) + nstyle + no + RESET + BG_PANEL + clip("", 2) + RESET)
            else:
                buf.append(BG_PANEL + clip("", box.w) + RESET)

    def draw_progress(self, buf: list[str], box: Box) -> None:
        with self.log_lock:
            logs = list(self.logs)
        view_h = max(1, box.h)
        start = max(0, len(logs) - view_h)
        for row in range(view_h):
            buf.append(f"\033[{box.y + 1 + row};1H")
            idx = start + row
            if idx >= len(logs):
                buf.append(BG_PANEL + clip("", box.w) + RESET)
                continue
            line = logs[idx]
            style = BG_PANEL + (FG_RED if line.startswith("错误") else FG_TEXT)
            if idx == len(logs) - 1:
                style = BG_SEL + FG_YELLOW
            buf.append(style + clip("  " + line, box.w) + RESET)

    def draw_type(self, buf: list[str], box: Box) -> None:
        prompt = "  " + self.type_title
        value = "  > " + self.type_value + "█"
        for row in range(box.h):
            buf.append(f"\033[{box.y + 1 + row};1H")
            if row == 0:
                buf.append(BG_PANEL + FG_ACCENT + clip(prompt, box.w) + RESET)
            elif row == 1:
                buf.append(BG_SEL + BOLD + FG_YELLOW + clip(value, box.w) + RESET)
            elif row == 2:
                buf.append(BG_PANEL + FG_MUTED + clip("  底部键盘输入，OK 确认。GitHub / Gitee / GitLab 均可。", box.w) + RESET)
            else:
                buf.append(BG_PANEL + clip("", box.w) + RESET)

    def draw_keys(self, buf: list[str], box: Box) -> None:
        rows = self.keyboard()
        self.key_r = max(0, min(len(rows) - 1, self.key_r))
        self.key_c = max(0, min(len(rows[self.key_r]) - 1, self.key_c))
        inner_w = max(8, box.w - 2)
        for r, row in enumerate(rows):
            y = box.y + r
            if y >= box.y + box.h:
                break
            total = sum(max(3, k.wide * 3 + 1) for k in row)
            pad = max(0, (inner_w - total) // 2)
            parts = [BG_PANEL + " " * pad]
            for c, key in enumerate(row):
                kw = max(3, key.wide * 3 + 1)
                label = clip(key.label.center(kw), kw)
                sel = r == self.key_r and c == self.key_c
                style = (BG_KEYSEL + BOLD + FG_TEXT) if sel else (BG_KEY + FG_MUTED)
                parts.append(style + label + RESET + BG_PANEL)
            used = pad + total
            if used < box.w:
                parts.append(" " * (box.w - used))
            buf.append(f"\033[{y + 1};1H")
            buf.append("".join(parts) + RESET)

    def enable_mouse(self) -> None:
        sys.stdout.write("\033[?1000h\033[?1002h\033[?1006h")
        sys.stdout.flush()

    def disable_mouse(self) -> None:
        sys.stdout.write("\033[?1000l\033[?1002l\033[?1006l")
        sys.stdout.flush()


class Input:
    def __init__(self) -> None:
        self.fd = sys.stdin.fileno() if not IS_WIN else None
        self.old = None
        self.queue: list[str] = []

    def __enter__(self) -> "Input":
        if IS_WIN:
            return self
        import termios
        import tty

        self.old = termios.tcgetattr(self.fd)
        tty.setraw(self.fd)
        return self

    def __exit__(self, *args) -> None:
        if self.old is not None:
            import termios

            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)

    def read(self) -> str | None:
        if self.queue:
            return self.queue.pop(0)
        if IS_WIN:
            return self._read_win()
        return self._read_unix()

    def _read_win(self) -> str | None:
        import msvcrt

        if not msvcrt.kbhit():
            time.sleep(0.02)
            if not msvcrt.kbhit():
                return None
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            ch2 = msvcrt.getwch()
            return {"H": "UP", "P": "DOWN", "K": "LEFT", "M": "RIGHT", "I": "PGUP", "Q": "PGDN", "G": "HOME", "O": "END"}.get(ch2, "")
        return {"\r": "ENTER", "\n": "ENTER", "\x08": "BACKSPACE", "\t": "TAB", "\x1b": "ESC", "\x03": "CTRL_C"}.get(ch, ch)

    def _read_unix(self) -> str | None:
        import select

        ready, _, _ = select.select([self.fd], [], [], 0.12)
        if not ready:
            return None
        data = os.read(self.fd, 64)
        if not data:
            return None
        keys = self._decode_many(data)
        if not keys:
            return None
        self.queue.extend(keys[1:])
        return keys[0]

    def _decode_many(self, data: bytes) -> list[str]:
        keys: list[str] = []
        i = 0
        while i < len(data):
            key, used = self._decode_one(data[i:])
            if used <= 0:
                break
            if key:
                keys.append(key)
            i += used
        return keys

    def _decode_one(self, data: bytes) -> tuple[str, int]:
        if not data:
            return "", 0
        if data.startswith(b"\x1b[<"):
            end = -1
            for i, byte in enumerate(data):
                if byte in (ord("M"), ord("m")) and i >= 5:
                    end = i
                    break
            if end < 0:
                return "", 0
            return self._mouse(data[: end + 1]), end + 1
        if data[0] == 0x1B:
            if len(data) == 1:
                return "ESC", 1
            table = {
                b"[A": "UP",
                b"[B": "DOWN",
                b"[C": "RIGHT",
                b"[D": "LEFT",
                b"[H": "HOME",
                b"[F": "END",
                b"[5~": "PGUP",
                b"[6~": "PGDN",
                b"[3~": "DEL",
                b"[15~": "F5",
            }
            rest = data[1:]
            for seq, name in table.items():
                if rest.startswith(seq):
                    return name, 1 + len(seq)
            return "ESC", 1
        mapping = {
            3: "CTRL_C",
            4: "ESC",
            9: "TAB",
            8: "BACKSPACE",
            127: "BACKSPACE",
            13: "ENTER",
            10: "ENTER",
        }
        b0 = data[0]
        if b0 in mapping:
            return mapping[b0], 1
        if b0 < 0x80:
            return chr(b0), 1
        need = 2 if b0 < 0xE0 else 3 if b0 < 0xF0 else 4
        chunk = data[:need]
        try:
            return chunk.decode("utf-8"), len(chunk)
        except UnicodeDecodeError:
            return "?", 1

    def _mouse(self, data: bytes) -> str:
        try:
            s = data.decode("ascii", "ignore")
            if not s.endswith(("M", "m")):
                return ""
            body = s[3:-1]
            btn_s, x_s, y_s = body.split(";")
            btn = int(btn_s)
            x = int(x_s) - 1
            y = int(y_s) - 1
            press = s.endswith("M")
            if not press and btn not in (64, 65):
                return ""
            return f"MOUSE:{btn}:{x}:{y}"
        except Exception:
            return ""


def main() -> int:
    os.environ.setdefault("TERM", "xterm-256color")
    app = AppStoreUI()
    sys.stdout.write("\033[?1049h\033[?25l")
    sys.stdout.flush()
    inp = Input()
    try:
        with inp:
            app.enable_mouse()
            while app.running:
                sys.stdout.write(app.draw())
                sys.stdout.flush()
                key = inp.read()
                if not key:
                    continue
                if key.startswith("MOUSE:"):
                    _, btn, x, y = key.split(":")
                    app.handle_click(int(x), int(y), int(btn))
                else:
                    app.handle_key(key)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            app.disable_mouse()
        except Exception:
            pass
        sys.stdout.write("\033[?25h\033[?1049l" + RESET)
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
