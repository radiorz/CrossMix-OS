#!/usr/bin/env python3
# WebDesk HTTP + WebSocket service. Stdlib only.

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import secrets
import socket
import struct
import subprocess
import sys
import threading
import time
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

IS_WIN = os.name == "nt"
WWW = Path(__file__).resolve().parent / "www"
WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_TERMS = 4
READ_LIMIT = 512 * 1024


def default_root() -> str:
    for cand in ("/mnt/SDCARD", os.path.expanduser("~"), os.getcwd()):
        if cand and os.path.isdir(cand):
            return os.path.abspath(cand)
    return os.path.abspath(".")


def lan_ips() -> list[str]:
    found: list[str] = []

    def add(ip: str) -> None:
        ip = (ip or "").strip()
        if not ip or ip.startswith("127.") or ip.startswith("169.254."):
            return
        if ip not in found:
            found.append(ip)

    try:
        out = subprocess.check_output(
            ["ip", "-4", "-o", "addr", "show"],
            text=True,
            errors="replace",
            timeout=2,
        )
        for line in out.splitlines():
            parts = line.split()
            if "inet" in parts:
                i = parts.index("inet")
                add(parts[i + 1].split("/")[0])
    except Exception:
        pass

    try:
        out = subprocess.check_output(
            ["ip", "route", "get", "1"],
            text=True,
            errors="replace",
            timeout=2,
        )
        toks = out.split()
        if "src" in toks:
            add(toks[toks.index("src") + 1])
        elif toks:
            add(toks[-1])
    except Exception:
        pass

    if not IS_WIN:
        try:
            out = subprocess.check_output(["hostname", "-I"], text=True, errors="replace", timeout=2)
            for part in out.split():
                add(part)
        except Exception:
            pass

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.3)
        s.connect(("1.1.1.1", 80))
        add(s.getsockname()[0])
        s.close()
    except Exception:
        pass

    return found


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "K", "M", "G", "T"):
        if size < 1024 or unit == "T":
            return f"{int(size)}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{n}B"


def read_first(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def sys_info() -> dict:
    mem_total = mem_free = 0
    try:
        for line in open("/proc/meminfo", encoding="utf-8", errors="replace"):
            if line.startswith("MemTotal:"):
                mem_total = int(line.split()[1]) * 1024
            elif line.startswith("MemAvailable:"):
                mem_free = int(line.split()[1]) * 1024
    except OSError:
        pass

    load = read_first("/proc/loadavg").split()[:3]
    uptime_s = 0.0
    try:
        uptime_s = float(read_first("/proc/uptime").split()[0])
    except (IndexError, ValueError):
        pass

    disks = []
    try:
        out = subprocess.check_output(["df", "-k"], text=True, errors="replace", timeout=3)
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 6:
                continue
            mp = parts[-1]
            if mp in ("/mnt/SDCARD", "/", "/tmp") or mp.startswith("/mnt/"):
                try:
                    disks.append(
                        {
                            "mount": mp,
                            "size": int(parts[1]) * 1024,
                            "used": int(parts[2]) * 1024,
                            "avail": int(parts[3]) * 1024,
                            "pct": parts[4],
                        }
                    )
                except ValueError:
                    pass
    except Exception:
        pass

    gov = read_first("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    return {
        "host": socket.gethostname(),
        "ips": lan_ips(),
        "root": default_root(),
        "cwd": os.getcwd(),
        "uptime": uptime_s,
        "load": load,
        "mem_total": mem_total,
        "mem_avail": mem_free,
        "disks": disks,
        "governor": gov,
        "python": sys.version.split()[0],
        "time": int(time.time()),
    }


def abs_path(raw: str | None) -> str:
    path = unquote(raw or "") or default_root()
    path = os.path.expanduser(path)
    if IS_WIN and path.startswith("/") and not path.startswith("//"):
        # browser may send POSIX paths while testing on Windows
        if not os.path.exists(path):
            path = default_root()
    return os.path.abspath(path)


class Service:
    def __init__(self, host: str, port: int, pin: str) -> None:
        self.host = host
        self.port = port
        self.pin = pin
        self.token = secrets.token_hex(16)
        self.started = time.time()
        self.lock = threading.Lock()
        self.sessions: list[TermSession] = []
        self.http_clients = 0
        self.last_event = "等待浏览器连接"
        self.fail_n = 0
        self.lockout = 0.0
        self.httpd: ReuseHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.bound_port = port
        self.error = ""

    def note(self, who: str, msg: str) -> None:
        self.last_event = f"{who}  {msg}"[:120]

    def snapshot(self) -> dict:
        with self.lock:
            terms = len(self.sessions)
        return {
            "port": self.bound_port,
            "ips": lan_ips(),
            "clients": self.http_clients,
            "terms": terms,
            "last": self.last_event,
            "error": self.error,
            "uptime": time.time() - self.started,
            "pin": self.pin,
        }

    def start(self) -> None:
        last_err = None
        ports = [self.port]
        if self.port == 80:
            ports.append(8088)
        for port in ports:
            try:
                httpd = ReuseHTTPServer((self.host, port), Handler)
                httpd.svc = self
                self.httpd = httpd
                self.bound_port = port
                self.error = ""
                break
            except OSError as exc:
                last_err = exc
                httpd = None
        if self.httpd is None:
            self.error = f"无法绑定 {self.host}:{self.port} ({last_err})"
            raise RuntimeError(self.error)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        with self.lock:
            sessions = list(self.sessions)
        for sess in sessions:
            sess.close()
        if self.httpd is not None:
            try:
                self.httpd.shutdown()
            except Exception:
                pass
            try:
                self.httpd.server_close()
            except Exception:
                pass
            self.httpd = None
        if self.thread is not None:
            self.thread.join(timeout=2)
            self.thread = None

    def check_pin(self, pin: str) -> bool:
        now = time.time()
        if now < self.lockout:
            return False
        if secrets.compare_digest(str(pin or ""), self.pin):
            self.fail_n = 0
            return True
        self.fail_n += 1
        if self.fail_n >= 8:
            self.lockout = now + 20
            self.fail_n = 0
        time.sleep(0.35)
        return False

    def add_term(self, sess: TermSession) -> bool:
        with self.lock:
            self.sessions = [s for s in self.sessions if s.alive]
            if len(self.sessions) >= MAX_TERMS:
                return False
            self.sessions.append(sess)
            return True

    def drop_term(self, sess: TermSession) -> None:
        with self.lock:
            self.sessions = [s for s in self.sessions if s is not sess and s.alive]


class ReuseHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 16

    def server_bind(self) -> None:
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        super().server_bind()


class Handler(BaseHTTPRequestHandler):
    server_version = "WebDesk/1.0"
    protocol_version = "HTTP/1.1"
    timeout = 30

    @property
    def svc(self) -> Service:
        return self.server.svc  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args) -> None:
        try:
            self.svc.note(self.client_address[0], fmt % args)
        except Exception:
            pass

    def handle_one_request(self) -> None:
        self.svc.http_clients += 1
        try:
            super().handle_one_request()
        finally:
            self.svc.http_clients = max(0, self.svc.http_clients - 1)

    def cookie_ok(self) -> bool:
        raw = self.headers.get("Cookie", "")
        jar = cookies.SimpleCookie()
        try:
            jar.load(raw)
        except Exception:
            return False
        morsel = jar.get("webdesk")
        if not morsel:
            return False
        return secrets.compare_digest(morsel.value, self.svc.token)

    def send_cors(self) -> None:
        self.send_header("Cache-Control", "no-store")

    def write_bytes(self, status: int, body: bytes, ctype: str, extra: list[tuple[str, str]] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_cors()
        if extra:
            for k, v in extra:
                self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def write_json(self, status: int, payload: dict, extra: list[tuple[str, str]] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.write_bytes(status, body, "application/json; charset=utf-8", extra)

    def read_json(self) -> dict:
        n = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(n) if n > 0 else b"{}"
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def qs(self) -> dict[str, str]:
        parsed = urlparse(self.path)
        q = parse_qs(parsed.query)
        return {k: (v[0] if v else "") for k, v in q.items()}

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path == "/ws/term":
            self.handle_ws()
            return
        if path in ("/api/ping",):
            self.write_json(200, {"ok": True})
            return
        if path == "/api/login":
            self.write_json(405, {"ok": False, "error": "POST only"})
            return
        if path == "/api/status":
            snap = self.svc.snapshot()
            self.write_json(
                200,
                {
                    "ok": True,
                    "auth": self.cookie_ok(),
                    "port": snap["port"],
                    "ips": snap["ips"],
                    "host": socket.gethostname(),
                },
            )
            return
        if path.startswith("/api/") and not self.cookie_ok():
            self.write_json(401, {"ok": False, "error": "需要访问码"})
            return
        if path == "/api/sys":
            info = sys_info()
            info.update({"ok": True, **self.svc.snapshot()})
            info.pop("pin", None)
            self.write_json(200, info)
            return
        if path == "/api/fs":
            self.api_list()
            return
        if path == "/api/fs/download":
            self.api_download()
            return
        if path == "/api/fs/read":
            self.api_read()
            return
        if path.startswith("/static/"):
            self.serve_static(path[len("/static/") :])
            return
        if path in ("/", "/index.html"):
            self.serve_static("index.html", public=True)
            return
        self.serve_static("index.html", public=True)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/api/login":
            self.api_login()
            return
        if not self.cookie_ok():
            self.write_json(401, {"ok": False, "error": "需要访问码"})
            return
        if path == "/api/fs/mkdir":
            self.api_mkdir()
            return
        if path == "/api/fs/rename":
            self.api_rename()
            return
        if path == "/api/fs/delete":
            self.api_delete()
            return
        if path == "/api/fs/write":
            self.api_write()
            return
        self.write_json(404, {"ok": False, "error": "not found"})

    def do_PUT(self) -> None:
        path = unquote(urlparse(self.path).path)
        if not self.cookie_ok():
            self.write_json(401, {"ok": False, "error": "需要访问码"})
            return
        if path == "/api/fs/upload":
            self.api_upload()
            return
        self.write_json(404, {"ok": False, "error": "not found"})

    def api_login(self) -> None:
        data = self.read_json()
        pin = str(data.get("pin") or data.get("code") or "").strip()
        if not self.svc.check_pin(pin):
            self.write_json(403, {"ok": False, "error": "访问码不对，看掌机屏幕"})
            return
        extra = [("Set-Cookie", f"webdesk={self.svc.token}; Path=/; SameSite=Lax; HttpOnly")]
        self.write_json(200, {"ok": True}, extra)

    def api_list(self) -> None:
        target = abs_path(self.qs().get("path"))
        hidden = self.qs().get("hidden") in ("1", "true", "yes")
        if not os.path.isdir(target):
            self.write_json(404, {"ok": False, "error": f"不是目录: {target}"})
            return
        entries = []
        try:
            with os.scandir(target) as it:
                for item in it:
                    name = item.name
                    if not hidden and name.startswith("."):
                        continue
                    try:
                        st = item.stat(follow_symlinks=False)
                        is_dir = item.is_dir(follow_symlinks=False)
                        size = 0 if is_dir else int(st.st_size)
                        mtime = int(st.st_mtime)
                    except OSError:
                        is_dir = False
                        size = 0
                        mtime = 0
                    entries.append(
                        {
                            "name": name,
                            "dir": is_dir,
                            "size": size,
                            "mtime": mtime,
                            "link": item.is_symlink(),
                        }
                    )
        except OSError as exc:
            self.write_json(403, {"ok": False, "error": str(exc)})
            return
        entries.sort(key=lambda e: (not e["dir"], e["name"].lower()))
        parent = os.path.dirname(target)
        self.write_json(
            200,
            {
                "ok": True,
                "path": target,
                "parent": parent if parent != target else "",
                "entries": entries,
            },
        )

    def api_download(self) -> None:
        target = abs_path(self.qs().get("path"))
        if not os.path.isfile(target):
            self.write_json(404, {"ok": False, "error": "文件不存在"})
            return
        ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
        try:
            size = os.path.getsize(target)
            name = os.path.basename(target)
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(size))
            self.send_header("Content-Disposition", f'attachment; filename="{name}"')
            self.send_cors()
            self.end_headers()
            if self.command == "HEAD":
                return
            with open(target, "rb") as fh:
                while True:
                    chunk = fh.read(64 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except OSError as exc:
            self.write_json(403, {"ok": False, "error": str(exc)})

    def api_read(self) -> None:
        target = abs_path(self.qs().get("path"))
        if not os.path.isfile(target):
            self.write_json(404, {"ok": False, "error": "文件不存在"})
            return
        try:
            size = os.path.getsize(target)
            if size > READ_LIMIT:
                self.write_json(413, {"ok": False, "error": f"超过 {human_size(READ_LIMIT)}，请下载后改"})
                return
            data = open(target, "rb").read()
        except OSError as exc:
            self.write_json(403, {"ok": False, "error": str(exc)})
            return
        if b"\x00" in data[:4096]:
            self.write_json(415, {"ok": False, "error": "二进制文件，不能在线编辑"})
            return
        text = data.decode("utf-8", errors="replace")
        self.write_json(200, {"ok": True, "path": target, "content": text, "size": size})

    def api_write(self) -> None:
        data = self.read_json()
        target = abs_path(str(data.get("path") or ""))
        if os.path.isdir(target):
            self.write_json(400, {"ok": False, "error": "不能把目录当文件写"})
            return
        text = data.get("content")
        if not isinstance(text, str):
            self.write_json(400, {"ok": False, "error": "缺少 content"})
            return
        try:
            os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
            with open(target, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        except OSError as exc:
            self.write_json(403, {"ok": False, "error": str(exc)})
            return
        self.write_json(200, {"ok": True, "path": target})

    def api_mkdir(self) -> None:
        data = self.read_json()
        parent = abs_path(str(data.get("path") or default_root()))
        name = str(data.get("name") or "").strip()
        if not name or "/" in name or "\\" in name or name in (".", ".."):
            self.write_json(400, {"ok": False, "error": "目录名不合法"})
            return
        dest = os.path.join(parent, name)
        try:
            os.makedirs(dest, exist_ok=False)
        except FileExistsError:
            self.write_json(409, {"ok": False, "error": "已存在"})
            return
        except OSError as exc:
            self.write_json(403, {"ok": False, "error": str(exc)})
            return
        self.write_json(200, {"ok": True, "path": dest})

    def api_rename(self) -> None:
        data = self.read_json()
        src = abs_path(str(data.get("path") or ""))
        dest_name = str(data.get("name") or "").strip()
        dest = str(data.get("dest") or "").strip()
        if dest:
            target = abs_path(dest)
        else:
            if not dest_name or "/" in dest_name or "\\" in dest_name:
                self.write_json(400, {"ok": False, "error": "新名字不合法"})
                return
            target = os.path.join(os.path.dirname(src), dest_name)
        if not os.path.exists(src):
            self.write_json(404, {"ok": False, "error": "源路径不存在"})
            return
        try:
            os.rename(src, target)
        except OSError as exc:
            self.write_json(403, {"ok": False, "error": str(exc)})
            return
        self.write_json(200, {"ok": True, "path": target})

    def api_delete(self) -> None:
        import shutil

        data = self.read_json()
        target = abs_path(str(data.get("path") or ""))
        if target in ("/", "\\") or len(target) < 2:
            self.write_json(400, {"ok": False, "error": "拒绝删除这个路径"})
            return
        if not os.path.exists(target):
            self.write_json(404, {"ok": False, "error": "不存在"})
            return
        try:
            if os.path.isdir(target) and not os.path.islink(target):
                shutil.rmtree(target)
            else:
                os.remove(target)
        except OSError as exc:
            self.write_json(403, {"ok": False, "error": str(exc)})
            return
        self.write_json(200, {"ok": True})

    def api_upload(self) -> None:
        q = self.qs()
        folder = abs_path(q.get("dir") or q.get("path") or default_root())
        name = os.path.basename(unquote(q.get("name") or "upload.bin"))
        if not name or name in (".", ".."):
            self.write_json(400, {"ok": False, "error": "文件名不合法"})
            return
        if not os.path.isdir(folder):
            self.write_json(404, {"ok": False, "error": "目录不存在"})
            return
        dest = os.path.join(folder, name)
        n = int(self.headers.get("Content-Length") or "0")
        left = n
        try:
            with open(dest, "wb") as fh:
                while left > 0:
                    chunk = self.rfile.read(min(64 * 1024, left))
                    if not chunk:
                        break
                    fh.write(chunk)
                    left -= len(chunk)
        except OSError as exc:
            self.write_json(403, {"ok": False, "error": str(exc)})
            return
        self.write_json(200, {"ok": True, "path": dest, "size": n - left})

    def serve_static(self, rel: str, public: bool = False) -> None:
        rel = rel.replace("\\", "/").lstrip("/")
        if ".." in rel.split("/"):
            self.write_json(403, {"ok": False, "error": "bad path"})
            return
        target = (WWW / rel).resolve()
        try:
            target.relative_to(WWW.resolve())
        except ValueError:
            self.write_json(403, {"ok": False, "error": "bad path"})
            return
        if not target.is_file():
            self.write_bytes(404, b"not found", "text/plain; charset=utf-8")
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if target.suffix == ".js":
            ctype = "application/javascript; charset=utf-8"
        elif target.suffix == ".css":
            ctype = "text/css; charset=utf-8"
        elif target.suffix == ".html":
            ctype = "text/html; charset=utf-8"
        data = target.read_bytes()
        cache = [] if target.suffix == ".html" else [("Cache-Control", "public, max-age=86400")]
        self.write_bytes(200, data, ctype, cache)

    def handle_ws(self) -> None:
        if not self.cookie_ok():
            self.write_json(401, {"ok": False, "error": "需要访问码"})
            return
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            self.write_bytes(400, b"missing key", "text/plain")
            return
        accept = base64.b64encode(hashlib.sha1((key + WS_MAGIC).encode("ascii")).digest()).decode("ascii")
        sess = TermSession(self.connection, self.svc)
        if not self.svc.add_term(sess):
            self.write_json(429, {"ok": False, "error": f"终端最多 {MAX_TERMS} 路"})
            return
        try:
            self.send_response(101, "Switching Protocols")
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", accept)
            self.end_headers()
            try:
                self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass
            self.close_connection = True
            self.timeout = None
            try:
                self.connection.settimeout(None)
            except OSError:
                pass
            sess.run()
        finally:
            self.svc.drop_term(sess)
            sess.close()


class TermSession:
    def __init__(self, sock: socket.socket, svc: Service) -> None:
        self.sock = sock
        self.svc = svc
        self.alive = True
        self.proc: subprocess.Popen | None = None
        self.master: int | None = None
        self.lock = threading.Lock()

    def close(self) -> None:
        self.alive = False
        proc = self.proc
        master = self.master
        self.proc = None
        self.master = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.kill()
            except Exception:
                pass
        if master is not None:
            try:
                os.close(master)
            except OSError:
                pass
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass

    def run(self) -> None:
        env = os.environ.copy()
        env.setdefault("TERM", "xterm-256color")
        env.setdefault("LANG", "en_US.UTF-8")
        env.setdefault("LC_ALL", "en_US.UTF-8")
        env.setdefault("HOME", default_root())
        extra = "/mnt/SDCARD/System/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        env["PATH"] = extra + os.pathsep + env.get("PATH", "")
        if os.path.isdir("/mnt/SDCARD/System/lib"):
            env["LD_LIBRARY_PATH"] = "/mnt/SDCARD/System/lib:/usr/trimui/lib:" + env.get(
                "LD_LIBRARY_PATH", ""
            )
        cwd = default_root()
        try:
            if IS_WIN:
                self._run_win(env, cwd)
            else:
                self._run_pty(env, cwd)
        except Exception:
            self.alive = False

    def _run_win(self, env: dict, cwd: str) -> None:
        shell = os.environ.get("COMSPEC", "cmd.exe")
        self.proc = subprocess.Popen(
            [shell],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=cwd,
            env=env,
            bufsize=0,
        )
        assert self.proc.stdout and self.proc.stdin
        out_th = threading.Thread(target=self._pump_pipe, daemon=True)
        out_th.start()
        self._ws_loop(win=True)
        if self.proc and self.proc.poll() is None:
            self.proc.kill()

    def _pump_pipe(self) -> None:
        assert self.proc and self.proc.stdout
        while self.alive:
            data = self.proc.stdout.read(4096)
            if not data:
                break
            if not self._ws_send(0x2, data):
                break
        self.alive = False

    def _run_pty(self, env: dict, cwd: str) -> None:
        import fcntl
        import pty
        import select
        import termios

        master, slave = pty.openpty()
        self.master = master
        shell = "/bin/sh" if os.path.isfile("/bin/sh") else "/bin/bash"
        try:
            self.proc = subprocess.Popen(
                [shell, "-i"],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                cwd=cwd,
                env=env,
                close_fds=True,
                preexec_fn=os.setsid,
            )
        finally:
            try:
                os.close(slave)
            except OSError:
                pass
        flags = fcntl.fcntl(master, fcntl.F_GETFL)
        fcntl.fcntl(master, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        self._set_winsize(80, 24)
        while self.alive:
            fds = [self.sock, master]
            try:
                ready, _, _ = select.select(fds, [], [], 0.25)
            except (OSError, ValueError):
                break
            if master in ready:
                try:
                    data = os.read(master, 8192)
                except OSError:
                    data = b""
                if not data:
                    break
                if not self._ws_send(0x2, data):
                    break
            if self.sock in ready:
                if not self._ws_once(win=False):
                    break
            if self.proc and self.proc.poll() is not None:
                try:
                    leftover = os.read(master, 8192)
                    if leftover:
                        self._ws_send(0x2, leftover)
                except OSError:
                    pass
                break
        self.alive = False

    def _set_winsize(self, cols: int, rows: int) -> None:
        if self.master is None or IS_WIN:
            return
        try:
            import fcntl
            import termios

            cols = max(20, min(int(cols), 400))
            rows = max(8, min(int(rows), 120))
            fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        except Exception:
            pass

    def _ws_loop(self, win: bool) -> None:
        while self.alive:
            if not self._ws_once(win=win):
                break

    def _ws_once(self, win: bool) -> bool:
        try:
            opcode, payload = ws_recv(self.sock)
        except (OSError, ConnectionError, struct.error, TimeoutError, ValueError):
            return False
        if opcode in (0x8, -1):
            return False
        if opcode == 0x9:
            self._ws_send(0xA, payload)
            return True
        if opcode == 0xA:
            return True
        if opcode not in (0x1, 0x2):
            return True
        if opcode == 0x1:
            try:
                msg = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._write_child(payload)
                return True
            if isinstance(msg, dict) and msg.get("type") == "resize":
                self._set_winsize(int(msg.get("cols") or 80), int(msg.get("rows") or 24))
                return True
            if isinstance(msg, dict) and msg.get("type") == "data":
                self._write_child(str(msg.get("data") or "").encode("utf-8", errors="replace"))
                return True
            return True
        self._write_child(payload)
        return True

    def _write_child(self, data: bytes) -> None:
        if not data or not self.alive:
            return
        if self.master is not None:
            try:
                os.write(self.master, data)
            except OSError:
                self.alive = False
            return
        if self.proc and self.proc.stdin:
            try:
                self.proc.stdin.write(data)
                self.proc.stdin.flush()
            except OSError:
                self.alive = False

    def _ws_send(self, opcode: int, data: bytes) -> bool:
        try:
            with self.lock:
                self.sock.sendall(ws_frame(opcode, data))
            return True
        except OSError:
            self.alive = False
            return False


def recvall(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("closed")
        buf.extend(chunk)
    return bytes(buf)


def ws_recv(sock: socket.socket) -> tuple[int, bytes]:
    hdr = recvall(sock, 2)
    opcode = hdr[0] & 0x0F
    masked = hdr[1] & 0x80
    length = hdr[1] & 0x7F
    if length == 126:
        length = struct.unpack(">H", recvall(sock, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", recvall(sock, 8))[0]
    mask = recvall(sock, 4) if masked else b"\x00\x00\x00\x00"
    data = recvall(sock, length) if length else b""
    if masked:
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    return opcode, data


def ws_frame(opcode: int, data: bytes) -> bytes:
    header = bytes([0x80 | (opcode & 0x0F)])
    n = len(data)
    if n < 126:
        header += bytes([n])
    elif n < 65536:
        header += struct.pack(">BH", 126, n)
    else:
        header += struct.pack(">BQ", 127, n)
    return header + data


def make_pin() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def pick_port() -> int:
    env = os.environ.get("WEBDESK_PORT", "").strip()
    if env.isdigit():
        return int(env)
    return 80 if not IS_WIN else 8088
