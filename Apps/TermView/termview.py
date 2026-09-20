#!/usr/bin/env python3
# TermView — file sidebar + command terminal + on-screen keyboard
# Designed for TrimUI Smart Pro (CrossMix-OS) via TermSP / SimpleTerminal.

from __future__ import annotations

import os
import sys
import shutil
import struct
import subprocess
import time
from pathlib import Path

IS_WIN = os.name == "nt"

# Catppuccin Mocha-ish (256-color / 16-color friendly ANSI)
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
REV = "\033[7m"
FG_TEXT = "\033[38;5;189m"
FG_MUTED = "\033[38;5;103m"
FG_ACCENT = "\033[38;5;110m"
FG_GREEN = "\033[38;5;114m"
FG_PEACH = "\033[38;5;216m"
FG_RED = "\033[38;5;210m"
FG_YELLOW = "\033[38;5;222m"
FG_BLUE = "\033[38;5;111m"
FG_MAUVE = "\033[38;5;141m"
BG_BAR = "\033[48;5;236m"
BG_SEL = "\033[48;5;24m"
BG_KEY = "\033[48;5;238m"
BG_KEYSEL = "\033[48;5;67m"
BG_PANEL = "\033[48;5;235m"


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
    for cand in ("/mnt/SDCARD", os.path.expanduser("~"), os.getcwd()):
        if cand and os.path.isdir(cand):
            return os.path.abspath(cand)
    return os.path.abspath(".")


class Key:
    __slots__ = ("label", "kind", "value", "wide")

    def __init__(self, label: str, kind: str, value: str = "", wide: int = 1):
        self.label = label
        self.kind = kind  # char / special / run
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
        Key("SPC", "special", "space", 3),
        Key("⌫", "special", "backspace", 2),
        Key("SHFT", "special", "shift", 2),
        Key("SYM", "special", "sym", 2),
        Key("HID", "special", "hide", 2),
        Key("ENT", "special", "enter", 2),
    ]
    quick = [
        Key("ls", "run", "ls -lah", 2),
        Key("pwd", "run", "pwd", 2),
        Key("df", "run", "df -h", 2),
        Key("cd..", "run", "cd ..", 2),
        Key("clr", "special", "clear", 2),
        Key("/SD", "special", "sdcard", 2),
    ]
    return rows + [extras, quick]


class TermView:
    def __init__(self) -> None:
        self.cwd = default_cwd()
        self.focus = "files"  # files | term | keys
        self.entries: list[tuple[str, bool, int]] = []
        self.file_idx = 0
        self.file_scroll = 0
        self.output: list[str] = [
            "TermView  —  左侧文件，右侧终端，底部键盘",
            "Select/Tab 切换栏   方向键移动   Start/Enter 确认   B 退格或返回上级",
            "点文件夹进入，点文件会把路径填进命令行。",
            "",
        ]
        self.out_scroll = 0  # 0 = stick to bottom
        self.cmdline = ""
        self.history: list[str] = []
        self.hist_idx: int | None = None
        self.show_keys = True
        self.show_hidden = False
        self.shift = False
        self.sym = False
        self.key_r = 0
        self.key_c = 0
        self.status = "就绪"
        self.err = ""
        self.last_click = (0, 0, 0.0)
        self.running = True
        self.w = 80
        self.h = 24
        self.refresh_files()

    # ---------- files ----------
    def refresh_files(self) -> None:
        items: list[tuple[str, bool, int]] = []
        parent = os.path.dirname(self.cwd)
        if parent != self.cwd:
            items.append(("..", True, 0))
        try:
            names = os.listdir(self.cwd)
            self.err = ""
        except OSError as exc:
            names = []
            self.err = str(exc)
        dirs: list[tuple[str, bool, int]] = []
        files: list[tuple[str, bool, int]] = []
        for name in names:
            if not self.show_hidden and name.startswith("."):
                continue
            full = os.path.join(self.cwd, name)
            try:
                is_dir = os.path.isdir(full)
                size = 0 if is_dir else os.path.getsize(full)
            except OSError:
                is_dir = False
                size = 0
            (dirs if is_dir else files).append((name, is_dir, size))
        key = lambda e: e[0].lower()
        items.extend(sorted(dirs, key=key))
        items.extend(sorted(files, key=key))
        self.entries = items or [("..", True, 0)]
        self.file_idx = max(0, min(self.file_idx, len(self.entries) - 1))

    def current_entry(self) -> tuple[str, bool, int]:
        return self.entries[self.file_idx]

    def current_path(self) -> str:
        name, _, _ = self.current_entry()
        if name == "..":
            return os.path.dirname(self.cwd)
        return os.path.join(self.cwd, name)

    def open_selected(self, insert_file: bool = True) -> None:
        name, is_dir, _ = self.current_entry()
        target = self.current_path()
        if is_dir:
            if os.path.isdir(target):
                self.cwd = os.path.abspath(target)
                self.file_idx = 0
                self.file_scroll = 0
                self.refresh_files()
                self.status = self.cwd
        elif insert_file:
            q = self.quote(target)
            if self.cmdline and not self.cmdline.endswith(" "):
                self.cmdline += " "
            self.cmdline += q
            self.focus = "term"
            self.status = "已填入文件路径"

    # ---------- terminal ----------
    @staticmethod
    def quote(path: str) -> str:
        if not path:
            return path
        if any(ch in path for ch in ' \t"\'$&|;<>()'):
            return "'" + path.replace("'", "'\"'\"'") + "'"
        return path

    def append_out(self, text: str) -> None:
        if text is None:
            return
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        for line in text.split("\n"):
            self.output.append(line)
        if len(self.output) > 800:
            self.output = self.output[-800:]
        self.out_scroll = 0

    def run_command(self, cmd: str | None = None) -> None:
        raw = (self.cmdline if cmd is None else cmd).strip()
        if cmd is None:
            self.cmdline = ""
            self.hist_idx = None
        if not raw:
            return
        if cmd is None:
            self.history.append(raw)
            if len(self.history) > 80:
                self.history = self.history[-80:]
        self.append_out(f"$ {raw}")
        if raw in ("exit", "quit"):
            self.running = False
            return
        if raw == "clear":
            self.output = []
            self.status = "已清屏"
            return
        if raw == "cd" or raw.startswith("cd ") or raw.startswith("cd\t"):
            dest = raw[2:].strip() or os.environ.get("HOME", default_cwd())
            dest = os.path.expanduser(dest)
            new = dest if os.path.isabs(dest) else os.path.abspath(os.path.join(self.cwd, dest))
            if os.path.isdir(new):
                self.cwd = new
                self.file_idx = 0
                self.file_scroll = 0
                self.refresh_files()
                self.status = f"cd {self.cwd}"
            else:
                self.append_out(f"cd: 目录不存在: {dest}")
                self.status = "cd 失败"
            return

        env = os.environ.copy()
        env.setdefault("TERM", "xterm-256color")
        try:
            proc = subprocess.run(
                raw,
                shell=True,
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                timeout=90,
                env=env,
            )
            out = proc.stdout or ""
            if not out.endswith("\n") and out:
                out += "\n"
            if proc.returncode != 0:
                out += f"[exit {proc.returncode}]\n"
            self.append_out(out)
            self.status = f"exit {proc.returncode}"
        except subprocess.TimeoutExpired:
            self.append_out("[超时 90s]")
            self.status = "命令超时"
        except Exception as exc:
            self.append_out(f"[错误] {exc}")
            self.status = "命令失败"
        self.refresh_files()

    # ---------- keyboard ----------
    def keyboard(self) -> list[list[Key]]:
        return build_keyboard(self.shift, self.sym)

    def press_key(self, key: Key) -> None:
        if key.kind == "char":
            self.cmdline += key.value
            if self.shift:
                self.shift = False
            return
        if key.kind == "run":
            self.run_command(key.value)
            return
        act = key.value
        if act == "space":
            self.cmdline += " "
        elif act == "tab":
            self.cmdline += "    "
        elif act == "backspace":
            self.cmdline = self.cmdline[:-1]
        elif act == "enter":
            self.run_command()
        elif act == "shift":
            self.shift = not self.shift
            self.sym = False
        elif act == "sym":
            self.sym = not self.sym
            self.shift = False
        elif act == "hide":
            self.show_keys = False
            if self.focus == "keys":
                self.focus = "term"
        elif act == "clear":
            self.output = []
        elif act == "sdcard":
            if self.cmdline and not self.cmdline.endswith(" "):
                self.cmdline += " "
            self.cmdline += "/mnt/SDCARD"

    # ---------- input ----------
    def move_file(self, delta: int) -> None:
        if not self.entries:
            return
        self.file_idx = max(0, min(len(self.entries) - 1, self.file_idx + delta))

    def move_key(self, dr: int, dc: int) -> None:
        rows = self.keyboard()
        self.key_r = max(0, min(len(rows) - 1, self.key_r + dr))
        row = rows[self.key_r]
        self.key_c = max(0, min(len(row) - 1, self.key_c + dc))

    def history_move(self, delta: int) -> None:
        if not self.history:
            return
        if self.hist_idx is None:
            self.hist_idx = len(self.history)
        self.hist_idx = max(0, min(len(self.history), self.hist_idx + delta))
        if self.hist_idx == len(self.history):
            self.cmdline = ""
        else:
            self.cmdline = self.history[self.hist_idx]

    def cycle_focus(self, step: int = 1) -> None:
        order = ["files", "term"]
        if self.show_keys:
            order.append("keys")
        i = order.index(self.focus) if self.focus in order else 0
        self.focus = order[(i + step) % len(order)]

    def handle_key(self, key: str) -> None:
        if key in ("ESC", "CTRL_C", "CTRL_Q"):
            self.running = False
            return
        if key == "CTRL_L":
            self.output = []
            return
        if key == "CTRL_K":
            self.show_keys = not self.show_keys
            if not self.show_keys and self.focus == "keys":
                self.focus = "term"
            elif self.show_keys:
                self.focus = "keys"
            return
        if key == "CTRL_H":
            self.show_hidden = not self.show_hidden
            self.refresh_files()
            return
        if key == "TAB":
            self.cycle_focus(1)
            return
        if key == "F5":
            self.refresh_files()
            self.status = "已刷新"
            return

        if self.focus == "files":
            if key == "UP":
                self.move_file(-1)
            elif key == "DOWN":
                self.move_file(1)
            elif key in ("LEFT", "BACKSPACE"):
                parent = os.path.dirname(self.cwd)
                if parent != self.cwd and os.path.isdir(parent):
                    old = os.path.basename(self.cwd)
                    self.cwd = parent
                    self.refresh_files()
                    for i, (name, _, _) in enumerate(self.entries):
                        if name == old:
                            self.file_idx = i
                            break
            elif key in ("RIGHT", "ENTER"):
                self.open_selected()
            elif key == "PGUP":
                self.move_file(-10)
            elif key == "PGDN":
                self.move_file(10)
            elif key == "HOME":
                self.file_idx = 0
            elif key == "END":
                self.file_idx = len(self.entries) - 1
            elif key == " ":
                self.open_selected()
            elif len(key) == 1 and key.isprintable():
                self.cmdline += key
                self.focus = "term"
            return

        if self.focus == "term":
            if key == "UP":
                self.history_move(-1)
            elif key == "DOWN":
                self.history_move(1)
            elif key == "LEFT":
                pass
            elif key == "RIGHT":
                pass
            elif key == "PGUP":
                self.out_scroll = min(len(self.output), self.out_scroll + 5)
            elif key == "PGDN":
                self.out_scroll = max(0, self.out_scroll - 5)
            elif key == "ENTER":
                self.run_command()
            elif key == "BACKSPACE":
                self.cmdline = self.cmdline[:-1]
            elif len(key) == 1 and key.isprintable():
                self.cmdline += key
            return

        # keys
        if key == "UP":
            self.move_key(-1, 0)
        elif key == "DOWN":
            self.move_key(1, 0)
        elif key == "LEFT":
            self.move_key(0, -1)
        elif key == "RIGHT":
            self.move_key(0, 1)
        elif key in ("ENTER", " "):
            rows = self.keyboard()
            self.press_key(rows[self.key_r][self.key_c])
        elif key == "BACKSPACE":
            self.cmdline = self.cmdline[:-1]
        elif len(key) == 1 and key.isprintable():
            self.cmdline += key

    def handle_click(self, x: int, y: int, button: int) -> None:
        layout = self.layout()
        now = time.time()
        double = (x, y) == self.last_click[:2] and now - self.last_click[2] < 0.45
        self.last_click = (x, y, now)

        if button in (64, 65):  # wheel
            delta = -3 if button == 64 else 3
            if layout["files"].contains(x, y) or self.focus == "files":
                self.move_file(delta)
            else:
                self.out_scroll = max(0, self.out_scroll - delta)
            return

        if layout["files"].contains(x, y):
            self.focus = "files"
            rel = y - layout["files"].y
            idx = self.file_scroll + rel
            if 0 <= idx < len(self.entries):
                self.file_idx = idx
                if double:
                    self.open_selected()
            return
        if layout["term"].contains(x, y) or layout["cmd"].contains(x, y):
            self.focus = "term"
            return
        if self.show_keys and layout["keys"].contains(x, y):
            self.focus = "keys"
            hit = self.key_at(x, y, layout["keys"])
            if hit is not None:
                self.key_r, self.key_c = hit
                self.press_key(self.keyboard()[self.key_r][self.key_c])

    def key_at(self, x: int, y: int, box: "Box") -> tuple[int, int] | None:
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

    # ---------- draw ----------
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

    def layout(self) -> dict[str, "Box"]:
        w, h = self.w, self.h
        key_h = 8 if self.show_keys else 0
        top = 1
        bot = 1
        body_h = max(6, h - top - bot - key_h - 1)
        files_w = max(22, min(38, w // 3))
        term_w = w - files_w
        cmd_y = top + body_h - 1
        return {
            "title": Box(0, 0, w, 1),
            "files": Box(0, top, files_w, body_h - 1),
            "term": Box(files_w, top, term_w, body_h - 1),
            "cmd": Box(0, cmd_y, w, 1),
            "keys": Box(0, cmd_y + 1, w, key_h),
            "help": Box(0, h - 1, w, 1),
        }

    def draw(self) -> str:
        self.w, self.h = self.size()
        lay = self.layout()
        buf: list[str] = []
        hide = "\033[?25l"
        buf.append(hide + "\033[H")

        title = f"  TermView   {self.cwd}"
        right = f"{self.status}  "
        buf.append(self.bar(title, right, self.w, BG_BAR + BOLD + FG_ACCENT))

        self.draw_files(buf, lay["files"])
        self.draw_term(buf, lay["term"])
        self.draw_cmd(buf, lay["cmd"])
        if self.show_keys:
            self.draw_keys(buf, lay["keys"])
        help_l = " Select切换  ↑↓移动  Start确认  B退格/返回  Ctrl+K键盘  MENU退出 "
        help_r = f" {self.focus.upper()} "
        buf.append("\033[{};1H".format(self.h))
        buf.append(self.bar(help_l, help_r, self.w, BG_BAR + FG_MUTED))
        return "".join(buf)

    def bar(self, left: str, right: str, width: int, style: str) -> str:
        room = max(0, width - disp_w(right))
        return style + clip(left, room) + clip(right, min(disp_w(right), width)) + RESET

    def draw_files(self, buf: list[str], box: "Box") -> None:
        active = self.focus == "files"
        title = " FILES " if not active else " FILES ● "
        buf.append(f"\033[{box.y + 1};{box.x + 1}H")
        buf.append((BG_SEL + BOLD if active else BG_PANEL + FG_ACCENT) + clip(title, box.w) + RESET)
        view_h = max(1, box.h - 1)
        if self.file_idx < self.file_scroll:
            self.file_scroll = self.file_idx
        if self.file_idx >= self.file_scroll + view_h:
            self.file_scroll = self.file_idx - view_h + 1
        for row in range(view_h):
            y = box.y + 1 + row
            idx = self.file_scroll + row
            buf.append(f"\033[{y + 1};{box.x + 1}H")
            if idx >= len(self.entries):
                buf.append(BG_PANEL + clip("", box.w) + RESET)
                continue
            name, is_dir, size = self.entries[idx]
            mark = "▸ " if is_dir else "  "
            label = f"{mark}{name}"
            extra = " <DIR>" if is_dir else f" {human_size(size)}"
            room = box.w - disp_w(extra)
            line = clip(label, room) + extra
            selected = idx == self.file_idx
            if selected and active:
                style = BG_SEL + BOLD + FG_TEXT
            elif selected:
                style = BG_KEY + FG_TEXT
            elif is_dir:
                style = BG_PANEL + FG_BLUE
            else:
                style = BG_PANEL + FG_TEXT
            buf.append(style + clip(line, box.w) + RESET)

    def draw_term(self, buf: list[str], box: "Box") -> None:
        active = self.focus == "term"
        title = " TERMINAL " if not active else " TERMINAL ● "
        buf.append(f"\033[{box.y + 1};{box.x + 1}H")
        buf.append((BG_SEL + BOLD if active else BG_PANEL + FG_GREEN) + clip(title, box.w) + RESET)
        view_h = max(1, box.h - 1)
        lines = self.output
        end = len(lines) - self.out_scroll
        start = max(0, end - view_h)
        visible = lines[start:end]
        while len(visible) < view_h:
            visible.append("")
        for row, line in enumerate(visible):
            y = box.y + 1 + row
            buf.append(f"\033[{y + 1};{box.x + 1}H")
            style = BG_PANEL + (FG_GREEN if line.startswith("$ ") else FG_TEXT)
            if line.startswith("[") and ("错误" in line or "exit" in line or "超时" in line):
                style = BG_PANEL + FG_RED
            buf.append(style + clip(line.replace("\t", "    "), box.w) + RESET)

    def draw_cmd(self, buf: list[str], box: "Box") -> None:
        active = self.focus == "term"
        prompt = f" {os.path.basename(self.cwd) or '/'} $ "
        caret = "█" if active else " "
        text = prompt + self.cmdline + caret
        style = (BG_SEL + BOLD + FG_YELLOW) if active else (BG_BAR + FG_PEACH)
        buf.append(f"\033[{box.y + 1};{box.x + 1}H")
        buf.append(style + clip(text, box.w) + RESET)

    def draw_keys(self, buf: list[str], box: "Box") -> None:
        rows = self.keyboard()
        self.key_r = max(0, min(len(rows) - 1, self.key_r))
        self.key_c = max(0, min(len(rows[self.key_r]) - 1, self.key_c))
        active = self.focus == "keys"
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
                sel = active and r == self.key_r and c == self.key_c
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


class Box:
    __slots__ = ("x", "y", "w", "h")

    def __init__(self, x: int, y: int, w: int, h: int):
        self.x, self.y, self.w, self.h = x, y, w, h

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x + self.w and self.y <= y < self.y + self.h


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
            return {
                "H": "UP",
                "P": "DOWN",
                "K": "LEFT",
                "M": "RIGHT",
                "I": "PGUP",
                "Q": "PGDN",
                "G": "HOME",
                "O": "END",
            }.get(ch2, "")
        mapping = {
            "\r": "ENTER",
            "\n": "ENTER",
            "\x08": "BACKSPACE",
            "\t": "TAB",
            "\x1b": "ESC",
            "\x03": "CTRL_C",
            "\x0c": "CTRL_L",
            "\x0b": "CTRL_K",
        }
        return mapping.get(ch, ch)

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
        n = len(data)
        while i < n:
            key, used = self._decode_one(data[i:])
            if used <= 0:
                break
            if key:
                keys.append(key)
            i += used
        return keys

    def _decode(self, data: bytes) -> str:
        key, _ = self._decode_one(data)
        return key

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
                b"OP": "F1",
                b"OQ": "F2",
                b"[15~": "F5",
            }
            rest = data[1:]
            for seq, name in table.items():
                if rest.startswith(seq):
                    return name, 1 + len(seq)
            return "ESC", 1
        b0 = data[0]
        mapping = {
            3: "CTRL_C",
            4: "ESC",
            9: "TAB",
            11: "CTRL_K",
            12: "CTRL_L",
            8: "BACKSPACE",
            127: "BACKSPACE",
            13: "ENTER",
            10: "ENTER",
        }
        if b0 in mapping:
            return mapping[b0], 1
        if b0 < 0x80:
            return chr(b0), 1
        if b0 < 0xE0:
            need = 2
        elif b0 < 0xF0:
            need = 3
        else:
            need = 4
        chunk = data[:need]
        try:
            return chunk.decode("utf-8"), len(chunk)
        except UnicodeDecodeError:
            return "?", 1

    def _mouse(self, data: bytes) -> str:
        # SGR: ESC [ < btn ; x ; y M/m
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
    app = TermView()
    sys.stdout.write("\033[?1049h\033[?25l")
    sys.stdout.flush()
    inp = Input()
    try:
        with inp:
            app.enable_mouse()
            while app.running:
                frame = app.draw()
                sys.stdout.write(frame)
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
