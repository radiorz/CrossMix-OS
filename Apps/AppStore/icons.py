#!/usr/bin/env python3
"""Read local CrossMix icons and turn them into small ANSI thumbnails."""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

from sync import APPDIR, sdcard_root

THUMB_W = 8
THUMB_H = 4  # half-block rows → 8 pixels tall
CARD_H = 5

ROOT_LABELS = {
    "Apps": ("Apps", "应用", "同步整个应用目录"),
    "Emus": ("Emus", "模拟器", "同步整个模拟器目录"),
}


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def load_png_rgba(path: Path) -> tuple[int, int, list[tuple[int, int, int, int]]] | None:
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos = 8
    width = height = 0
    bit_depth = 8
    color_type = 6
    palette: list[tuple[int, int, int]] = []
    raw = bytearray()
    n = len(data)
    while pos + 8 <= n:
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        ctype = data[pos + 4 : pos + 8]
        start = pos + 8
        end = start + length
        if end + 4 > n:
            break
        chunk = data[start:end]
        pos = end + 4
        if ctype == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", chunk[:10])
            if chunk[12]:  # interlaced
                return None
        elif ctype == b"PLTE":
            palette = [tuple(chunk[i : i + 3]) for i in range(0, len(chunk), 3)]  # type: ignore[misc]
        elif ctype == b"IDAT":
            raw.extend(chunk)
        elif ctype == b"IEND":
            break
    if width <= 0 or height <= 0 or bit_depth != 8:
        return None
    try:
        decoded = zlib.decompress(bytes(raw))
    except zlib.error:
        return None
    bpp = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    if not bpp:
        return None
    stride = width * bpp
    out: list[tuple[int, int, int, int]] = []
    prev = bytearray(stride)
    i = 0
    for _y in range(height):
        if i + 1 + stride > len(decoded):
            return None
        ftype = decoded[i]
        scan = bytearray(decoded[i + 1 : i + 1 + stride])
        i += 1 + stride
        if ftype == 1:
            for x in range(stride):
                left = scan[x - bpp] if x >= bpp else 0
                scan[x] = (scan[x] + left) & 255
        elif ftype == 2:
            for x in range(stride):
                scan[x] = (scan[x] + prev[x]) & 255
        elif ftype == 3:
            for x in range(stride):
                left = scan[x - bpp] if x >= bpp else 0
                scan[x] = (scan[x] + ((left + prev[x]) // 2)) & 255
        elif ftype == 4:
            for x in range(stride):
                left = scan[x - bpp] if x >= bpp else 0
                up = prev[x]
                ul = prev[x - bpp] if x >= bpp else 0
                scan[x] = (scan[x] + _paeth(left, up, ul)) & 255
        elif ftype != 0:
            return None
        prev = scan
        x = 0
        while x < stride:
            if color_type == 6:
                out.append((scan[x], scan[x + 1], scan[x + 2], scan[x + 3]))
            elif color_type == 2:
                out.append((scan[x], scan[x + 1], scan[x + 2], 255))
            elif color_type == 3:
                pal = palette[scan[x]] if scan[x] < len(palette) else (0, 0, 0)
                out.append((pal[0], pal[1], pal[2], 255))
            elif color_type == 0:
                g = scan[x]
                out.append((g, g, g, 255))
            else:
                g, a = scan[x], scan[x + 1]
                out.append((g, g, g, a))
            x += bpp
    return width, height, out


def _sample(pixels, sw: int, sh: int, x: int, y: int) -> tuple[int, int, int]:
    sx = min(sw - 1, max(0, int(x * sw / THUMB_W)))
    sy = min(sh - 1, max(0, int(y * sh / (THUMB_H * 2))))
    r, g, b, a = pixels[sy * sw + sx]
    if a < 16:
        return 17, 24, 39
    if a < 255:
        return (
            (r * a + 17 * (255 - a)) // 255,
            (g * a + 24 * (255 - a)) // 255,
            (b * a + 39 * (255 - a)) // 255,
        )
    return r, g, b


def rgb256(r: int, g: int, b: int) -> int:
    if abs(r - g) < 8 and abs(g - b) < 8:
        gray = (r + g + b) // 3
        if gray < 8:
            return 16
        if gray > 247:
            return 231
        return 232 + min(23, gray * 24 // 256)
    return 16 + 36 * (r * 5 // 256) + 6 * (g * 5 // 256) + (b * 5 // 256)


def thumb_lines(path: Path | None, fallback: str = "app") -> list[str]:
    rgba = load_png_rgba(path) if path else None
    if rgba:
        sw, sh, pixels = rgba
        lines = []
        for row in range(THUMB_H):
            parts = []
            for col in range(THUMB_W):
                tr, tg, tb = _sample(pixels, sw, sh, col, row * 2)
                br, bg, bb = _sample(pixels, sw, sh, col, row * 2 + 1)
                parts.append(f"\033[38;5;{rgb256(tr, tg, tb)}m\033[48;5;{rgb256(br, bg, bb)}m▀")
            lines.append("".join(parts) + "\033[0m")
        return lines
    return _fallback_thumb(fallback)


def _fallback_thumb(kind: str) -> list[str]:
    if kind == "emu":
        colors = [
            [(23, 23, 23), (45, 212, 191), (45, 212, 191), (23, 23, 23)],
            [(30, 41, 59), (15, 23, 42), (15, 23, 42), (30, 41, 59)],
        ]
    else:
        colors = [
            [(45, 212, 191), (20, 83, 80), (20, 83, 80), (45, 212, 191)],
            [(20, 83, 80), (45, 212, 191), (45, 212, 191), (20, 83, 80)],
        ]
    lines = []
    for row in range(THUMB_H):
        band = colors[0 if row < 2 else 1]
        parts = []
        for col in range(THUMB_W):
            r, g, b = band[col * len(band) // THUMB_W]
            parts.append(f"\033[38;5;{rgb256(r, g, b)}m\033[48;5;{rgb256(max(0, r - 30), max(0, g - 30), max(0, b - 30))}m▀")
        lines.append("".join(parts) + "\033[0m")
    return lines


def resolve_sd_path(raw: str, base: Path) -> Path:
    text = (raw or "").replace("\\", "/").strip()
    if not text:
        return base / "icon.png"
    if text.startswith("/mnt/SDCARD/"):
        return sdcard_root() / text[len("/mnt/SDCARD/") :]
    if text.startswith("/"):
        p = Path(text)
        if p.is_file():
            return p
    return (base / text).resolve() if not Path(text).is_absolute() else Path(text)


def category_icon(root: str) -> Path:
    name = "Emus.png" if root == "Emus" else "Apps.png"
    return APPDIR / "icons" / name


def package_info(dest: Path, rel: str) -> dict:
    rel = (rel or "").replace("\\", "/").strip("/")
    name = Path(rel).name or rel
    root = rel.split("/", 1)[0] if rel else ""
    label = name
    desc = ""
    icon: Path | None = None
    cfg = dest / "config.json"
    if cfg.is_file():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict):
            label = str(data.get("label.ch.lang") or data.get("label") or label)
            desc = str(data.get("description") or "")
            icon_raw = str(data.get("icon") or data.get("iconsel") or "icon.png")
            cand = resolve_sd_path(icon_raw, dest)
            if cand.is_file():
                icon = cand
    if icon is None:
        for cand in (dest / "icon.png", dest / f"{name}.png", dest / "icon.jpg"):
            if cand.is_file():
                icon = cand
                break
    if icon is None and root == "Emus":
        emu = sdcard_root() / "Icons" / "Default" / "Emus" / f"{name}.png"
        if emu.is_file():
            icon = emu
    if icon is None and rel in ROOT_LABELS:
        cat = category_icon(rel)
        if cat.is_file():
            icon = cat
        names = ROOT_LABELS[rel]
        label = f"{names[1]}  {names[0]}"
        desc = names[2]
    kind = "emu" if root == "Emus" or rel == "Emus" else "app"
    return {"label": label, "desc": desc, "icon": icon, "kind": kind, "name": name}
