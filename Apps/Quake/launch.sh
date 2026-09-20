#!/bin/sh
# Quake — pick a PAK / game folder, then reuse Emus/TYRQUAKE.

export PATH="/mnt/SDCARD/System/bin:/mnt/SDCARD/System/usr/trimui/scripts:$PATH"
export LD_LIBRARY_PATH="/mnt/SDCARD/System/lib:/usr/trimui/lib:${LD_LIBRARY_PATH:-}"

INFO="/mnt/SDCARD/System/usr/trimui/scripts/infoscreen.sh"
ROMDIR="/mnt/SDCARD/Roms/TYRQUAKE"
LAUNCH="/mnt/SDCARD/Emus/TYRQUAKE/launch.sh"

if [ ! -f "$LAUNCH" ]; then
  if [ -x "$INFO" ]; then
    "$INFO" -m "未找到 Emus/TYRQUAKE/launch.sh" -k "A" -fs 28
  fi
  exit 1
fi

if [ ! -d "$ROMDIR" ]; then
  mkdir -p "$ROMDIR" 2>/dev/null
fi

if [ -n "$1" ] && [ -f "$1" ]; then
  exec sh "$LAUNCH" "$1"
fi

if [ -x "$INFO" ]; then
  "$INFO" -m "把 pak0.pak 放到 Roms/TYRQUAKE" -t 1.5 -fs 26
fi

if [ -z "$(find "$ROMDIR" -type f \( -iname '*.pak' -o -iname '*.zip' -o -iname '*.7z' \) 2>/dev/null | head -n 1)" ]; then
  if [ -x "$INFO" ]; then
    "$INFO" -m "Roms/TYRQUAKE 里还没有 pak0.pak。" -k "A" -fs 28
  fi
  exit 1
fi

out=$(selector -t "选择 Quake 游戏 (B 取消)" -d "$ROMDIR") || exit 0
file="${out#*: }"
if [ ! -f "$file" ]; then
  exit 0
fi

exec sh "$LAUNCH" "$file"
