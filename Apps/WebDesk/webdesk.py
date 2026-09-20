#!/usr/bin/env python3
# WebDesk — LAN web terminal + file manager for TrimUI Smart Pro / CrossMix-OS.
# HTTP is up only while this process is running.

from __future__ import annotations

import os
import shutil
import signal
import struct
import sys
import time

from httpsvc import IS_WIN, Service, lan_ips, make_pin, pick_port

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
FG_TEXT = "\033[38;5;189m"
FG_MUTED = "\033[38;5;103m"
FG_ACCENT = "\033[38;5;80m"
FG_GREEN = "\033[38;5;114m"
FG_PEACH = "\033[38;5;216m"
FG_RED = "\033[38;5;210m"
FG_YELLOW = "\033[38;5;222m"
BG_BAR = "\033[48;5;236m"
BG_PANEL = "\033[48;5;235m"
BG_PIN = "\033[48;5;24m"

PIDFILE = "/tmp/webdesk.pid" if not IS_WIN else os.path.join(os.environ.get("TEMP", "."), "webdesk.pid")


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


def write_pid() -> None:
    try:
        with open(PIDFILE, "w", encoding="utf-8") as fh:
            fh.write(str(os.getpid()))
    except OSError:
        pass


def clear_pid() -> None:
    try:
        os.remove(PIDFILE)
    except OSError:
        pass


class WebDeskUI:
    def __init__(self, svc: Service) -> None:
        self.svc = svc
        self.running = True
        self.w = 80
        self.h = 24
        self.help = False

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
                    return max(56, w), max(16, h)
        except Exception:
            pass
        sz = shutil.get_terminal_size((100, 28))
        return max(56, sz.columns), max(16, sz.lines)

    def urls(self) -> list[str]:
        port = self.svc.bound_port
        suffix = "" if port == 80 else f":{port}"
        urls = []
        for ip in lan_ips():
            urls.append(f"http://{ip}{suffix}/")
        if not urls:
            urls.append(f"http://127.0.0.1{suffix}/")
        host = "TSP"
        extra = f"http://{host}{suffix}/"
        if extra not in urls:
            urls.append(extra)
        return urls

    def handle_key(self, key: str) -> None:
        if key in ("ESC", "CTRL_C", "CTRL_Q", "BACKSPACE", "q", "Q"):
            self.running = False
            return
        if key in ("ENTER", " ", "r", "R"):
            return
        if key in ("h", "H", "TAB"):
            self.help = not self.help

    def draw(self) -> str:
        self.w, self.h = self.size()
        w, h = self.w, self.h
        snap = self.svc.snapshot()
        buf = [f"\033[H\033[J{RESET}"]
        title = clip(" WebDesk  远程网页   打开才提供服务 · 退出即关闭 ", w)
        buf.append(f"{BG_BAR}{BOLD}{FG_TEXT}{title}{RESET}\n")

        if self.help:
            lines = [
                "电脑或手机连和掌机同一 WiFi，浏览器打开下面的地址。",
                "访问码只显示在这台机子上，关掉 App 后网页立刻失效。",
                "网页里可以：看系统信息、管文件、开终端。",
                "终端是 root shell，只在自己信任的局域网里开。",
                "80 端口被占用时会自动改用 8088。",
                "B / MENU / ESC 退出并关闭 HTTP。",
            ]
            for i, line in enumerate(lines):
                if i + 3 >= h:
                    break
                buf.append(f" {FG_TEXT}{clip(line, w - 2)}{RESET}\n")
            for _ in range(h - 2 - len(lines)):
                buf.append("\n")
            buf.append(f"{BG_BAR}{FG_MUTED}{clip(' A/Tab 返回   B 退出 ', w)}{RESET}")
            return "".join(buf)

        rows: list[str] = []
        if snap["error"]:
            rows.append(f"{FG_RED}{BOLD}服务没起来{RESET}  {FG_RED}{snap['error']}{RESET}")
        else:
            rows.append(f"{FG_GREEN}{BOLD}HTTP 已打开{RESET}  {FG_MUTED}0.0.0.0:{snap['port']}{RESET}")

        rows.append("")
        rows.append(f"{FG_MUTED}浏览器打开{RESET}")
        ips = lan_ips()
        if not ips:
            rows.append(f"{FG_YELLOW}还没有局域网地址，先开 WiFi，连和电脑同一网络{RESET}")
        for url in self.urls()[:4]:
            rows.append(f"  {FG_ACCENT}{BOLD}{url}{RESET}")

        rows.append("")
        pin = "  ".join(self.svc.pin)
        rows.append(f"{FG_MUTED}访问码（只给这台电脑/手机）{RESET}")
        rows.append(f"  {BG_PIN}{BOLD}{FG_TEXT}  {pin}  {RESET}")

        rows.append("")
        rows.append(
            f"{FG_MUTED}浏览器 {RESET}{FG_TEXT}{snap['clients']}{RESET}"
            f"{FG_MUTED}  终端 {RESET}{FG_TEXT}{snap['terms']}{RESET}"
            f"{FG_MUTED}  已开 {RESET}{FG_TEXT}{int(snap['uptime'])}s{RESET}"
        )
        rows.append(f"{FG_MUTED}{clip(snap['last'], w - 2)}{RESET}")

        for i, line in enumerate(rows):
            if i + 3 >= h:
                break
            buf.append(f" {line}{RESET}\n")
        pad = h - 2 - min(len(rows), h - 3)
        buf.extend(["\n"] * max(0, pad))
        foot = " A 刷新   Select 说明   B / MENU 退出并关掉网页 "
        buf.append(f"{BG_BAR}{FG_MUTED}{clip(foot, w)}{RESET}")
        return "".join(buf)


class Input:
    def __init__(self) -> None:
        self.fd = None if IS_WIN else sys.stdin.fileno()
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
        return self._read_win() if IS_WIN else self._read_unix()

    def _read_win(self) -> str | None:
        import msvcrt

        if not msvcrt.kbhit():
            time.sleep(0.05)
            return None
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            return {"H": "UP", "P": "DOWN", "K": "LEFT", "M": "RIGHT"}.get(msvcrt.getwch(), "")
        return {
            "\r": "ENTER",
            "\n": "ENTER",
            "\x08": "BACKSPACE",
            "\t": "TAB",
            "\x1b": "ESC",
            "\x03": "CTRL_C",
        }.get(ch, ch)

    def _read_unix(self) -> str | None:
        import select

        ready, _, _ = select.select([self.fd], [], [], 0.35)
        if not ready:
            return None
        data = os.read(self.fd, 32)
        if not data:
            return None
        if data[0] == 0x1B:
            return "ESC" if len(data) == 1 else None
        b0 = data[0]
        return {
            3: "CTRL_C",
            9: "TAB",
            8: "BACKSPACE",
            127: "BACKSPACE",
            13: "ENTER",
            10: "ENTER",
        }.get(b0, chr(b0) if b0 < 128 else "ESC")


def main() -> int:
    os.environ.setdefault("TERM", "xterm-256color")
    pin = os.environ.get("WEBDESK_PIN", "").strip()
    if not (pin.isdigit() and 4 <= len(pin) <= 8):
        pin = make_pin()
    host = os.environ.get("WEBDESK_HOST", "0.0.0.0")
    port = pick_port()
    svc = Service(host, port, pin)
    ui = WebDeskUI(svc)
    write_pid()

    def stop(*_args) -> None:
        ui.running = False

    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    try:
        svc.start()
    except Exception:
        pass

    sys.stdout.write("\033[?1049h\033[?25l")
    sys.stdout.flush()
    inp = Input()
    try:
        with inp:
            while ui.running:
                sys.stdout.write(ui.draw())
                sys.stdout.flush()
                key = inp.read()
                if key:
                    ui.handle_key(key)
    except KeyboardInterrupt:
        pass
    finally:
        svc.stop()
        clear_pid()
        sys.stdout.write("\033[?25h\033[?1049l" + RESET)
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
