#!/usr/bin/env python3
# Gamepad file / media / script picker for TrimUI Smart Pro (TermSP).
# Writes HUB_SEL then exits so launch.sh can play or run the choice.

from __future__ import annotations

import os
import shutil
import struct
import sys
import tempfile
import time
from pathlib import Path

IS_WIN = os.name == "nt"

RESET = "\033[0m"
BOLD = "\033[1m"
FG_TEXT = "\033[38;5;189m"
FG_MUTED = "\033[38;5;103m"
FG_ACCENT = "\033[38;5;183m"
FG_GREEN = "\033[38;5;114m"
FG_PEACH = "\033[38;5;216m"
FG_RED = "\033[38;5;210m"
FG_YELLOW = "\033[38;5;222m"
FG_BLUE = "\033[38;5;111m"
BG_BAR = "\033[48;5;236m"
BG_SEL = "\033[48;5;54m"
BG_PANEL = "\033[48;5;235m"
BG_TAB = "\033[48;5;238m"
BG_TABSEL = "\033[48;5;61m"

VIDEO_EXT = {
    ".mp4", ".mkv", ".avi", ".mpg", ".mpeg", ".wmv", ".asf", ".rm", ".rmvb",
    ".m4v", ".ts", ".webm", ".mov", ".flv", ".vob", ".3gp",
}
AUDIO_EXT = {
    ".mp3", ".m3u", ".m3u8", ".wma", ".flac", ".ogg", ".wav", ".aac", ".opus",
    ".m4a", ".oga", ".spc", ".nsf", ".vgm", ".mod", ".it", ".xm", ".s3m",
}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}
SCRIPT_EXT = {".sh"}

MODE = os.environ.get("HUB_MODE", "xmb")
TITLE = os.environ.get("HUB_TITLE", "Media")
SEL_PATH = os.environ.get("HUB_SEL", "/tmp/crossmix_hub.sel")
APPDIR = os.environ.get("HUB_APPDIR", os.path.dirname(os.path.abspath(__file__)))
EXTRA_ROOTS = [p for p in os.environ.get("HUB_ROOTS", "").split("|") if p]


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


class Box:
    __slots__ = ("x", "y", "w", "h")

    def __init__(self, x: int, y: int, w: int, h: int) -> None:
        self.x, self.y, self.w, self.h = x, y, w, h

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x + self.w and self.y <= y < self.y + self.h


class Tab:
    __slots__ = ("key", "label", "roots", "exts")

    def __init__(self, key: str, label: str, roots: list[str], exts: set[str] | None) -> None:
        self.key = key
        self.label = label
        self.roots = roots
        self.exts = exts


def existing_roots(cands: list[str]) -> list[str]:
    out = []
    for p in cands:
        if p and os.path.isdir(p) and p not in out:
            out.append(os.path.abspath(p))
    return out or ["/mnt/SDCARD" if os.path.isdir("/mnt/SDCARD") else os.getcwd()]


def build_tabs() -> list[Tab]:
    if MODE == "music":
        return [Tab("music", "音乐", existing_roots([
            "/mnt/SDCARD/Roms/MUSIC", "/mnt/SDCARD/Music", "/mnt/SDCARD",
        ]), AUDIO_EXT)]
    if MODE == "scripts":
        roots = existing_roots(EXTRA_ROOTS + [
            os.path.join(APPDIR, "games"),
            "/mnt/SDCARD/Roms/RENPY",
            "/mnt/SDCARD/Roms/PORTS",
            "/mnt/SDCARD/Data/ports",
        ])
        return [Tab("scripts", "游戏", roots, SCRIPT_EXT)]
    return [
        Tab("video", "视频", existing_roots([
            "/mnt/SDCARD/Roms/VIDEOS", "/mnt/SDCARD/Videos",
            "/mnt/SDCARD/Videos/ScreenRecorder", "/mnt/SDCARD",
        ]), VIDEO_EXT),
        Tab("music", "音乐", existing_roots([
            "/mnt/SDCARD/Roms/MUSIC", "/mnt/SDCARD/Music", "/mnt/SDCARD",
        ]), AUDIO_EXT),
        Tab("photo", "图片", existing_roots([
            "/mnt/SDCARD/Pictures", "/mnt/SDCARD/Photos", "/mnt/SDCARD/Roms/VIDEOS",
        ]), IMAGE_EXT),
    ]


class Hub:
    def __init__(self) -> None:
        self.tabs = build_tabs()
        self.tab_i = 0
        self.cwd = self.tabs[0].roots[0]
        self.entries: list[tuple[str, bool, int, str]] = []
        self.idx = 0
        self.scroll = 0
        self.show_all = False
        self.show_jumps = False
        self.jump_idx = 0
        self.status = "A 打开   B 返回   Select 切换"
        self.running = True
        self.w = 80
        self.h = 24
        self.last_click = (0, 0, 0.0)
        self.load_last()
        self.refresh()

    @property
    def tab(self) -> Tab:
        return self.tabs[self.tab_i]

    def last_path(self) -> str:
        return os.path.join(APPDIR, f"last_{MODE}_{self.tab.key}.txt")

    def load_last(self) -> None:
        try:
            saved = Path(self.last_path()).read_text(encoding="utf-8").strip()
            if saved and os.path.isdir(saved):
                self.cwd = saved
        except OSError:
            pass

    def remember(self) -> None:
        try:
            Path(self.last_path()).write_text(self.cwd + "\n", encoding="utf-8")
        except OSError:
            pass

    def jumps(self) -> list[tuple[str, str]]:
        items = [(":folder", "播放本文件夹")]
        for root in self.tab.roots:
            name = os.path.basename(root.rstrip("/\\")) or root
            items.append((root, name))
        return items

    def is_launchable_dir(self, path: str) -> bool:
        if MODE != "scripts":
            return False
        return (
            os.path.isfile(os.path.join(path, "launch.sh"))
            or os.path.isfile(os.path.join(path, "game", "script.rpy"))
            or os.path.isfile(os.path.join(path, "script.rpy"))
        )

    def refresh(self) -> None:
        items: list[tuple[str, bool, int, str]] = []
        parent = os.path.dirname(self.cwd)
        if parent != self.cwd:
            items.append(("..", True, 0, "dir"))
        try:
            names = os.listdir(self.cwd)
        except OSError as exc:
            names = []
            self.status = str(exc)
        dirs: list[tuple[str, bool, int, str]] = []
        files: list[tuple[str, bool, int, str]] = []
        for name in names:
            if not self.show_all and name.startswith("."):
                continue
            full = os.path.join(self.cwd, name)
            try:
                is_dir = os.path.isdir(full)
                size = 0 if is_dir else os.path.getsize(full)
            except OSError:
                continue
            if is_dir:
                kind = "game" if self.is_launchable_dir(full) else "dir"
                dirs.append((name, True, 0, kind))
                continue
            ext = os.path.splitext(name)[1].lower()
            if self.show_all or self.tab.exts is None or ext in self.tab.exts:
                kind = "script" if ext == ".sh" else "file"
                files.append((name, False, size, kind))
        key = lambda e: (0 if e[3] == "game" else 1, e[0].lower())
        items.extend(sorted(dirs, key=key))
        items.extend(sorted(files, key=lambda e: e[0].lower()))
        self.entries = items or [("..", True, 0, "dir")]
        self.idx = max(0, min(self.idx, len(self.entries) - 1))

    def current(self) -> tuple[str, bool, int, str]:
        return self.entries[self.idx]

    def current_path(self) -> str:
        name, _, _, _ = self.current()
        if name == "..":
            return os.path.dirname(self.cwd)
        return os.path.join(self.cwd, name)

    def write_sel(self, kind: str, payload: str = "") -> None:
        try:
            Path(SEL_PATH).write_text(f"{kind}\n{payload}\n", encoding="utf-8")
        except OSError:
            pass
        self.remember()
        self.running = False

    def play_path(self, path: str) -> None:
        if MODE == "scripts":
            if path.endswith(".sh"):
                self.write_sel("run", path)
                return
            if self.is_launchable_dir(path):
                self.write_sel("renpy", path)
                return
            self.status = "这个目录没有可启动的游戏"
            return
        self.write_sel("file", path)

    def play_folder(self) -> None:
        files = [os.path.join(self.cwd, n) for n, is_dir, _, k in self.entries if not is_dir and k != "script"]
        if MODE == "scripts":
            self.status = "请选一个游戏"
            return
        if not files:
            self.status = "这个文件夹没有可播放文件"
            return
        playlist = os.path.join(tempfile.gettempdir(), "crossmix_hub.m3u")
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
        name, is_dir, _, kind = self.current()
        target = self.current_path()
        if is_dir:
            if kind == "game":
                self.play_path(target)
                return
            if os.path.isdir(target):
                self.cwd = os.path.abspath(target)
                self.idx = 0
                self.scroll = 0
                self.refresh()
                self.status = self.cwd
            return
        self.play_path(target)

    def switch_tab(self, delta: int) -> None:
        if len(self.tabs) < 2:
            return
        self.remember()
        self.tab_i = (self.tab_i + delta) % len(self.tabs)
        self.cwd = self.tab.roots[0]
        self.idx = 0
        self.scroll = 0
        self.load_last()
        self.refresh()
        self.status = self.tab.label

    def go_parent(self) -> None:
        parent = os.path.dirname(self.cwd)
        if parent == self.cwd or not os.path.isdir(parent):
            return
        old = os.path.basename(self.cwd)
        self.cwd = parent
        self.refresh()
        for i, (name, _, _, _) in enumerate(self.entries):
            if name == old:
                self.idx = i
                break

    def jump_to(self, path: str) -> None:
        self.show_jumps = False
        if path == ":folder":
            self.play_folder()
            return
        if os.path.isdir(path):
            self.cwd = os.path.abspath(path)
            self.idx = 0
            self.scroll = 0
            self.refresh()
            self.status = self.cwd

    def move(self, delta: int) -> None:
        if self.show_jumps:
            self.jump_idx = max(0, min(len(self.jumps()) - 1, self.jump_idx + delta))
            return
        if self.entries:
            self.idx = max(0, min(len(self.entries) - 1, self.idx + delta))

    def handle_key(self, key: str) -> None:
        if key in ("CTRL_C", "CTRL_Q"):
            self.running = False
            return
        if key == "ESC":
            if self.show_jumps:
                self.show_jumps = False
                return
            self.running = False
            return
        if self.show_jumps:
            if key == "UP":
                self.move(-1)
            elif key == "DOWN":
                self.move(1)
            elif key in ("ENTER", " "):
                self.jump_to(self.jumps()[self.jump_idx][0])
            elif key in ("BACKSPACE", "LEFT"):
                self.show_jumps = False
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
            self.go_parent()
        elif key in ("RIGHT", "ENTER", " "):
            self.open_selected()
        elif key == "TAB":
            self.switch_tab(1)
        elif key in ("[",):
            self.switch_tab(-1)
        elif key in ("]",):
            self.switch_tab(1)
        elif key in ("x", "X"):
            self.show_all = not self.show_all
            self.refresh()
            self.status = "显示全部文件" if self.show_all else "只显示当前类型"
        elif key in ("y", "Y", "j", "J"):
            self.show_jumps = True
            self.jump_idx = 0
        elif key in ("p", "P"):
            self.play_folder()
        elif key == "F5":
            self.refresh()
            self.status = "已刷新"

    def handle_click(self, x: int, y: int, button: int) -> None:
        now = time.time()
        double = (x, y) == self.last_click[:2] and now - self.last_click[2] < 0.45
        self.last_click = (x, y, now)
        lay = self.layout()
        if button in (64, 65):
            self.move(-3 if button == 64 else 3)
            return
        if lay["tabs"].contains(x, y) and len(self.tabs) > 1:
            slot = max(8, self.w // len(self.tabs))
            i = min(len(self.tabs) - 1, max(0, x // slot))
            self.switch_tab(i - self.tab_i)
            return
        if lay["list"].contains(x, y):
            rel = y - lay["list"].y
            if self.show_jumps:
                if 0 <= rel < len(self.jumps()):
                    self.jump_idx = rel
                    if double:
                        self.jump_to(self.jumps()[self.jump_idx][0])
                return
            idx = self.scroll + rel
            if 0 <= idx < len(self.entries):
                self.idx = idx
                if double:
                    self.open_selected()

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
        tab_h = 1 if len(self.tabs) > 1 else 0
        return {
            "title": Box(0, 0, self.w, 1),
            "tabs": Box(0, 1, self.w, tab_h),
            "list": Box(0, 1 + tab_h, self.w, max(4, self.h - 2 - tab_h)),
            "help": Box(0, self.h - 1, self.w, 1),
        }

    def bar(self, left: str, right: str, width: int, style: str) -> str:
        room = max(0, width - disp_w(right))
        return style + clip(left, room) + clip(right, min(disp_w(right), width)) + RESET

    def draw(self) -> str:
        self.w, self.h = self.size()
        lay = self.layout()
        buf = ["\033[?25l\033[H"]
        title = f"  {TITLE}   {self.tab.label}   {self.cwd}"
        if self.show_jumps:
            title = f"  {TITLE}   快速跳转"
        buf.append(self.bar(title, f"{self.status}  ", self.w, BG_BAR + BOLD + FG_ACCENT))
        if len(self.tabs) > 1:
            parts = []
            slot = max(8, self.w // len(self.tabs))
            for i, tab in enumerate(self.tabs):
                style = (BG_TABSEL + BOLD + FG_TEXT) if i == self.tab_i else (BG_TAB + FG_MUTED)
                parts.append(style + clip(f" {tab.label} ", slot) + RESET)
            buf.append(f"\033[2;1H{''.join(parts)}")
        if self.show_jumps:
            self.draw_jumps(buf, lay["list"])
        else:
            self.draw_files(buf, lay["list"])
        if MODE == "scripts":
            help_l = " A启动  B返回  Y跳转  MENU退出 "
        else:
            help_l = " A播放  B返回  Select分类  Y跳转/播文件夹  X全部  MENU退出 "
        buf.append(f"\033[{self.h};1H")
        buf.append(self.bar(help_l, f" {self.tab.key.upper()} {self.idx + 1}/{len(self.entries)} ", self.w, BG_BAR + FG_MUTED))
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
            name, is_dir, size, kind = self.entries[idx]
            mark = "★ " if kind == "game" else ("▸ " if is_dir else "▶ ")
            extra = " <GAME>" if kind == "game" else (" <DIR>" if is_dir else f" {human_size(size)}")
            line = clip(mark + name, box.w - disp_w(extra)) + extra
            if idx == self.idx:
                style = BG_SEL + BOLD + FG_TEXT
            elif kind == "game":
                style = BG_PANEL + FG_PEACH
            elif is_dir:
                style = BG_PANEL + FG_BLUE
            else:
                style = BG_PANEL + FG_TEXT
            buf.append(style + clip(line, box.w) + RESET)

    def draw_jumps(self, buf: list[str], box: Box) -> None:
        rows = self.jumps()
        for row in range(box.h):
            buf.append(f"\033[{box.y + 1 + row};1H")
            if row >= len(rows):
                buf.append(BG_PANEL + clip("", box.w) + RESET)
                continue
            path, name = rows[row]
            extra = "" if path.startswith(":") else f"   {path}"
            label = f"  {name}{extra}"
            style = BG_SEL + BOLD + FG_TEXT if row == self.jump_idx else (
                BG_PANEL + FG_PEACH if path.startswith(":") else BG_PANEL + FG_GREEN
            )
            buf.append(style + clip(label, box.w) + RESET)

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
    app = Hub()
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
