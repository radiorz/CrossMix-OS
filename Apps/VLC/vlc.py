#!/usr/bin/env python3
# VLC — media browser + network stream picker for TrimUI Smart Pro.
# Writes a selection file, then launch.sh plays it with mpv / stock player.

from __future__ import annotations

import os
import sys
import shutil
import struct
import tempfile
import time
from pathlib import Path

IS_WIN = os.name == "nt"

RESET = "\033[0m"
BOLD = "\033[1m"
FG_TEXT = "\033[38;5;189m"
FG_MUTED = "\033[38;5;103m"
FG_ACCENT = "\033[38;5;208m"
FG_GREEN = "\033[38;5;114m"
FG_PEACH = "\033[38;5;216m"
FG_RED = "\033[38;5;210m"
FG_YELLOW = "\033[38;5;222m"
FG_BLUE = "\033[38;5;111m"
BG_BAR = "\033[48;5;236m"
BG_SEL = "\033[48;5;130m"
BG_KEY = "\033[48;5;238m"
BG_KEYSEL = "\033[48;5;166m"
BG_PANEL = "\033[48;5;234m"

MEDIA_EXT = {
    ".mp4", ".mkv", ".avi", ".mpg", ".mpeg", ".wmv", ".asf", ".rm", ".rmvb",
    ".m4v", ".ts", ".webm", ".mov", ".flv", ".vob", ".3gp",
    ".mp3", ".m3u", ".m3u8", ".wma", ".flac", ".ogg", ".wav", ".aac", ".opus",
    ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp",
}

APPDIR = os.path.dirname(os.path.abspath(__file__))
SEL_PATH = os.environ.get("VLC_SEL", "/tmp/crossmix_vlc.sel")
LAST_DIR = os.path.join(APPDIR, "last_dir.txt")
STREAMS = os.path.join(APPDIR, "streams.txt")


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


def default_cwd() -> str:
    if os.path.isfile(LAST_DIR):
        try:
            saved = Path(LAST_DIR).read_text(encoding="utf-8").strip()
            if saved and os.path.isdir(saved):
                return os.path.abspath(saved)
        except OSError:
            pass
    for cand in (
        "/mnt/SDCARD/Roms/VIDEOS",
        "/mnt/SDCARD/Videos",
        "/mnt/SDCARD/Videos/ScreenRecorder",
        "/mnt/SDCARD",
        os.path.expanduser("~"),
        os.getcwd(),
    ):
        if cand and os.path.isdir(cand):
            return os.path.abspath(cand)
    return os.path.abspath(".")


def remember_dir(path: str) -> None:
    try:
        Path(LAST_DIR).write_text(path + "\n", encoding="utf-8")
    except OSError:
        pass


def load_streams() -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    if not os.path.isfile(STREAMS):
        return items
    try:
        raw = Path(STREAMS).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return items
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            name, url = line.split("|", 1)
            items.append((name.strip() or url.strip(), url.strip()))
        else:
            items.append((line, line))
    return items


def save_stream(url: str) -> None:
    url = url.strip()
    if not url:
        return
    existing = {u for _, u in load_streams()}
    if url in existing:
        return
    try:
        with open(STREAMS, "a", encoding="utf-8") as fh:
            fh.write(url + "\n")
    except OSError:
        pass


class Key:
    __slots__ = ("label", "kind", "value", "wide")

    def __init__(self, label: str, kind: str, value: str = "", wide: int = 1):
        self.label = label
        self.kind = kind
        self.value = value if value else label
        self.wide = wide


def build_keyboard(shift: bool, sym: bool) -> list[list[Key]]:
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
        Key("://", "char", "://", 2),
        Key("SPC", "special", "space", 2),
        Key("⌫", "special", "backspace", 2),
        Key("SHFT", "special", "shift", 2),
        Key("SYM", "special", "sym", 2),
        Key("播放", "special", "enter", 2),
    ]
    prefixes = [
        Key("http", "char", "http://", 2),
        Key("https", "char", "https://", 2),
        Key("rtsp", "char", "rtsp://", 2),
        Key(".m3u8", "char", ".m3u8", 2),
    ]
    return rows + [extras, prefixes]


class Box:
    __slots__ = ("x", "y", "w", "h")

    def __init__(self, x: int, y: int, w: int, h: int):
        self.x, self.y, self.w, self.h = x, y, w, h

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x + self.w and self.y <= y < self.y + self.h


class VLCApp:
    JUMPS = [
        ("网络串流", ":stream"),
        ("系统播放器", ":stock"),
        ("播放本文件夹", ":folder"),
        ("VIDEOS", "/mnt/SDCARD/Roms/VIDEOS"),
        ("Videos", "/mnt/SDCARD/Videos"),
        ("录屏", "/mnt/SDCARD/Videos/ScreenRecorder"),
        ("MUSIC", "/mnt/SDCARD/Roms/MUSIC"),
        ("SD卡", "/mnt/SDCARD"),
    ]

    def __init__(self) -> None:
        self.mode = os.environ.get("VLC_MODE", "browse")  # browse | stream
        if self.mode not in ("browse", "stream"):
            self.mode = "browse"
        self.cwd = default_cwd()
        self.entries: list[tuple[str, bool, int]] = []
        self.idx = 0
        self.scroll = 0
        self.show_all = False
        self.status = "选文件后按 A 播放"
        self.running = True
        self.w = 80
        self.h = 24
        self.url = ""
        self.streams = load_streams()
        self.stream_idx = 0
        self.typing = self.mode == "stream" and not self.streams
        self.show_keys = self.typing
        self.shift = False
        self.sym = False
        self.key_r = 0
        self.key_c = 0
        self.show_jumps = False
        self.jump_idx = 0
        self.last_click = (0, 0, 0.0)
        self.refresh_files()
        if self.mode == "stream":
            self.status = "选串流或输入地址"

    def refresh_files(self) -> None:
        items: list[tuple[str, bool, int]] = []
        parent = os.path.dirname(self.cwd)
        if parent != self.cwd:
            items.append(("..", True, 0))
        try:
            names = os.listdir(self.cwd)
        except OSError as exc:
            names = []
            self.status = str(exc)
        dirs: list[tuple[str, bool, int]] = []
        files: list[tuple[str, bool, int]] = []
        for name in names:
            if not self.show_all and name.startswith("."):
                continue
            full = os.path.join(self.cwd, name)
            try:
                is_dir = os.path.isdir(full)
                size = 0 if is_dir else os.path.getsize(full)
            except OSError:
                is_dir = False
                size = 0
            if is_dir:
                dirs.append((name, True, 0))
            else:
                ext = os.path.splitext(name)[1].lower()
                if self.show_all or ext in MEDIA_EXT:
                    files.append((name, False, size))
        key = lambda e: e[0].lower()
        items.extend(sorted(dirs, key=key))
        items.extend(sorted(files, key=key))
        self.entries = items or [("..", True, 0)]
        self.idx = max(0, min(self.idx, len(self.entries) - 1))

    def current(self) -> tuple[str, bool, int]:
        return self.entries[self.idx]

    def current_path(self) -> str:
        name, _, _ = self.current()
        if name == "..":
            return os.path.dirname(self.cwd)
        return os.path.join(self.cwd, name)

    def write_sel(self, kind: str, payload: str = "") -> None:
        try:
            Path(SEL_PATH).write_text(f"{kind}\n{payload}\n", encoding="utf-8")
        except OSError:
            pass
        if kind == "file" and payload:
            remember_dir(os.path.dirname(payload))
        elif kind == "playlist":
            remember_dir(self.cwd)
        self.running = False

    def play_file(self, path: str) -> None:
        self.write_sel("file", path)

    def play_url(self, url: str) -> None:
        url = url.strip()
        if not url:
            self.status = "地址为空"
            return
        save_stream(url)
        self.write_sel("url", url)

    def play_folder(self) -> None:
        files = [
            os.path.join(self.cwd, name)
            for name, is_dir, _ in self.entries
            if not is_dir
        ]
        if not files:
            self.status = "这个文件夹没有可播放文件"
            return
        playlist = os.path.join(tempfile.gettempdir(), "crossmix_vlc.m3u")
        try:
            with open(playlist, "w", encoding="utf-8") as fh:
                fh.write("#EXTM3U\n")
                for item in files:
                    fh.write(item + "\n")
        except OSError as exc:
            self.status = str(exc)
            return
        self.write_sel("playlist", playlist)

    def open_selected(self) -> None:
        name, is_dir, _ = self.current()
        target = self.current_path()
        if is_dir:
            if os.path.isdir(target):
                self.cwd = os.path.abspath(target)
                self.idx = 0
                self.scroll = 0
                self.refresh_files()
                self.status = self.cwd
            return
        self.play_file(target)

    def jump_to(self, path: str) -> None:
        self.show_jumps = False
        if path == ":stream":
            self.mode = "stream"
            self.typing = not self.streams
            self.show_keys = self.typing
            self.status = "网络串流"
            return
        if path == ":stock":
            self.write_sel("stock")
            return
        if path == ":folder":
            self.play_folder()
            return
        if os.path.isdir(path):
            self.cwd = os.path.abspath(path)
            self.idx = 0
            self.scroll = 0
            self.refresh_files()
            self.status = self.cwd
            return
        self.status = f"目录不存在: {path}"

    def stream_rows(self) -> list[tuple[str, str]]:
        rows = [("+ 输入新地址", "")]
        rows.extend(self.streams)
        return rows

    def keyboard(self) -> list[list[Key]]:
        return build_keyboard(self.shift, self.sym)

    def press_key(self, key: Key) -> None:
        if key.kind == "char":
            self.url += key.value
            if self.shift:
                self.shift = False
            return
        act = key.value
        if act == "space":
            self.url += " "
        elif act == "tab":
            self.url += "://"
        elif act == "backspace":
            self.url = self.url[:-1]
        elif act == "enter":
            self.play_url(self.url)
        elif act == "shift":
            self.shift = not self.shift
            self.sym = False
        elif act == "sym":
            self.sym = not self.sym
            self.shift = False

    def move(self, delta: int) -> None:
        if self.mode == "stream" and not self.typing:
            rows = self.stream_rows()
            if not rows:
                return
            self.stream_idx = max(0, min(len(rows) - 1, self.stream_idx + delta))
            return
        if not self.entries:
            return
        self.idx = max(0, min(len(self.entries) - 1, self.idx + delta))

    def move_key(self, dr: int, dc: int) -> None:
        rows = self.keyboard()
        self.key_r = max(0, min(len(rows) - 1, self.key_r + dr))
        row = rows[self.key_r]
        self.key_c = max(0, min(len(row) - 1, self.key_c + dc))

    def handle_key(self, key: str) -> None:
        if key in ("CTRL_C", "CTRL_Q"):
            self.running = False
            return
        if key == "ESC":
            if self.show_jumps:
                self.show_jumps = False
                return
            if self.mode == "stream":
                if self.typing:
                    self.typing = False
                    self.show_keys = False
                    if not self.streams:
                        self.mode = "browse"
                    return
                self.mode = "browse"
                self.status = "文件浏览"
                return
            self.running = False
            return
        if self.show_jumps:
            if key in ("UP",):
                self.jump_idx = max(0, self.jump_idx - 1)
            elif key in ("DOWN",):
                self.jump_idx = min(len(self.JUMPS) - 1, self.jump_idx + 1)
            elif key in ("ENTER", " "):
                self.jump_to(self.JUMPS[self.jump_idx][1])
            elif key in ("BACKSPACE", "ESC"):
                self.show_jumps = False
            return

        if key == "CTRL_K":
            if self.mode != "stream":
                self.mode = "stream"
                self.typing = not self.streams
                self.show_keys = self.typing
                self.status = "网络串流"
            else:
                self.mode = "browse"
                self.typing = False
                self.show_keys = False
                self.status = "文件浏览"
            return
        if key == "F5":
            self.streams = load_streams()
            self.refresh_files()
            self.status = "已刷新"
            return

        if self.mode == "stream":
            self.handle_stream_key(key)
            return

        if key == "UP":
            self.move(-1)
        elif key == "DOWN":
            self.move(1)
        elif key == "PGUP":
            self.move(-10)
        elif key == "PGDN":
            self.move(10)
        elif key == "HOME":
            self.idx = 0
        elif key == "END":
            self.idx = len(self.entries) - 1
        elif key in ("LEFT", "BACKSPACE"):
            parent = os.path.dirname(self.cwd)
            if parent != self.cwd and os.path.isdir(parent):
                old = os.path.basename(self.cwd)
                self.cwd = parent
                self.refresh_files()
                for i, (name, _, _) in enumerate(self.entries):
                    if name == old:
                        self.idx = i
                        break
        elif key in ("RIGHT", "ENTER"):
            self.open_selected()
        elif key in ("y", "Y"):
            self.write_sel("stock")
        elif key in ("x", "X"):
            self.show_all = not self.show_all
            self.refresh_files()
            self.status = "显示全部文件" if self.show_all else "只显示媒体文件"
        elif key in ("s", "S"):
            self.mode = "stream"
            self.typing = not self.streams
            self.show_keys = self.typing
            self.status = "网络串流"
        elif key in ("j", "J", "TAB"):
            self.show_jumps = True
            self.jump_idx = 0
        elif key in ("p", "P"):
            self.play_folder()
        elif key == " ":
            self.open_selected()

    def handle_stream_key(self, key: str) -> None:
        if self.typing:
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
                    self.play_url(self.url)
                return
            if key == "BACKSPACE":
                self.url = self.url[:-1]
                return
            if key == "TAB":
                self.show_keys = not self.show_keys
                return
            if len(key) == 1 and key.isprintable():
                self.url += key
            return

        if key == "UP":
            self.move(-1)
        elif key == "DOWN":
            self.move(1)
        elif key in ("ENTER", " ", "RIGHT"):
            rows = self.stream_rows()
            if not rows:
                self.typing = True
                self.show_keys = True
                return
            name, url = rows[self.stream_idx]
            if not url:
                self.typing = True
                self.show_keys = True
                self.status = "输入 http(s)/rtsp 地址"
            else:
                self.play_url(url)
        elif key in ("LEFT", "BACKSPACE"):
            self.mode = "browse"
            self.status = "文件浏览"
        elif key in ("n", "N", "y", "Y"):
            self.typing = True
            self.show_keys = True

    def handle_click(self, x: int, y: int, button: int) -> None:
        now = time.time()
        double = (x, y) == self.last_click[:2] and now - self.last_click[2] < 0.45
        self.last_click = (x, y, now)
        lay = self.layout()
        if button in (64, 65):
            self.move(-3 if button == 64 else 3)
            return
        if self.show_jumps and lay["list"].contains(x, y):
            rel = y - lay["list"].y
            if 0 <= rel < len(self.JUMPS):
                self.jump_idx = rel
                if double:
                    self.jump_to(self.JUMPS[self.jump_idx][1])
            return
        if self.mode == "stream" and self.show_keys and lay["keys"].contains(x, y):
            hit = self.key_at(x, y, lay["keys"])
            if hit is not None:
                self.key_r, self.key_c = hit
                self.press_key(self.keyboard()[self.key_r][self.key_c])
            return
        if lay["list"].contains(x, y):
            rel = y - lay["list"].y
            if self.mode == "stream" and not self.typing:
                rows = self.stream_rows()
                idx = rel
                if 0 <= idx < len(rows):
                    self.stream_idx = idx
                    if double:
                        self.handle_key("ENTER")
            else:
                idx = self.scroll + rel
                if 0 <= idx < len(self.entries):
                    self.idx = idx
                    if double:
                        self.open_selected()

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
        key_h = 8 if self.mode == "stream" and self.show_keys else 0
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
        buf = ["\033[?25l\033[H"]
        title = "  VLC   文件浏览" if self.mode == "browse" else "  VLC   网络串流"
        if self.show_jumps:
            title = "  VLC   快速跳转"
        buf.append(self.bar(title + "  " + ("" if self.mode == "stream" else self.cwd), f"{self.status}  ", self.w, BG_BAR + BOLD + FG_ACCENT))
        if self.show_jumps:
            self.draw_jumps(buf, lay["list"])
        elif self.mode == "stream":
            self.draw_streams(buf, lay["list"])
            if self.show_keys:
                self.draw_keys(buf, lay["keys"])
        else:
            self.draw_files(buf, lay["list"])
        if self.mode == "browse":
            help_l = " A播放  B返回  Y系统播放器  X全部文件  Select跳转/串流  MENU退出 "
        elif self.typing:
            help_l = " 方向键选键  A输入/播放  B退格  Select关键盘  MENU退出 "
        else:
            help_l = " A播放  B返回浏览  Y新地址  MENU退出 "
        buf.append(f"\033[{self.h};1H")
        buf.append(self.bar(help_l, f" {self.mode.upper()} ", self.w, BG_BAR + FG_MUTED))
        return "".join(buf)

    def draw_files(self, buf: list[str], box: Box) -> None:
        view_h = max(1, box.h)
        if self.idx < self.scroll:
            self.scroll = self.idx
        if self.idx >= self.scroll + view_h:
            self.scroll = self.idx - view_h + 1
        for row in range(view_h):
            y = box.y + row
            idx = self.scroll + row
            buf.append(f"\033[{y + 1};1H")
            if idx >= len(self.entries):
                buf.append(BG_PANEL + clip("", box.w) + RESET)
                continue
            name, is_dir, size = self.entries[idx]
            mark = "▸ " if is_dir else "▶ "
            extra = " <DIR>" if is_dir else f" {human_size(size)}"
            line = clip(mark + name, box.w - disp_w(extra)) + extra
            if idx == self.idx:
                style = BG_SEL + BOLD + FG_TEXT
            elif is_dir:
                style = BG_PANEL + FG_BLUE
            else:
                style = BG_PANEL + FG_TEXT
            buf.append(style + clip(line, box.w) + RESET)

    def draw_streams(self, buf: list[str], box: Box) -> None:
        if self.typing:
            prompt = " 地址: " + self.url + "█"
            buf.append(f"\033[{box.y + 1};1H")
            buf.append(BG_SEL + BOLD + FG_YELLOW + clip(prompt, box.w) + RESET)
            hint = "  用底部键盘输入 Jellyfin / DLNA / m3u8 地址，按「播放」。"
            buf.append(f"\033[{box.y + 2};1H")
            buf.append(BG_PANEL + FG_MUTED + clip(hint, box.w) + RESET)
            for row in range(2, box.h):
                buf.append(f"\033[{box.y + 1 + row};1H")
                buf.append(BG_PANEL + clip("", box.w) + RESET)
            return
        rows = self.stream_rows()
        for row in range(box.h):
            buf.append(f"\033[{box.y + 1 + row};1H")
            if row >= len(rows):
                buf.append(BG_PANEL + clip("", box.w) + RESET)
                continue
            name, url = rows[row]
            label = f"  {name}"
            if url and url != name:
                label += f"  {url}"
            style = BG_SEL + BOLD + FG_TEXT if row == self.stream_idx else BG_PANEL + FG_TEXT
            if row == 0:
                style = (BG_SEL + BOLD + FG_GREEN) if row == self.stream_idx else (BG_PANEL + FG_GREEN)
            buf.append(style + clip(label, box.w) + RESET)

    def draw_jumps(self, buf: list[str], box: Box) -> None:
        for row in range(box.h):
            buf.append(f"\033[{box.y + 1 + row};1H")
            if row >= len(self.JUMPS):
                buf.append(BG_PANEL + clip("", box.w) + RESET)
                continue
            name, path = self.JUMPS[row]
            exists = path.startswith(":") or os.path.isdir(path)
            extra = "" if path.startswith(":") else f"   {path}"
            label = f"  {name}{extra}"
            if row == self.jump_idx:
                style = BG_SEL + BOLD + FG_TEXT
            elif path.startswith(":"):
                style = BG_PANEL + FG_PEACH
            elif exists:
                style = BG_PANEL + FG_GREEN
            else:
                style = BG_PANEL + FG_MUTED
            buf.append(style + clip(label, box.w) + RESET)

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
            11: "CTRL_K",
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
    app = VLCApp()
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
