#!/bin/sh
# DOOM — pick a WAD with the gamepad, then reuse Emus/DOOM.

export PATH="/mnt/SDCARD/System/bin:/mnt/SDCARD/System/usr/trimui/scripts:$PATH"
export LD_LIBRARY_PATH="/mnt/SDCARD/System/lib:/usr/trimui/lib:${LD_LIBRARY_PATH:-}"

INFO="/mnt/SDCARD/System/usr/trimui/scripts/infoscreen.sh"
ROMDIR="/mnt/SDCARD/Roms/DOOM"
LAUNCH="/mnt/SDCARD/Emus/DOOM/launch.sh"

if [ ! -x "$LAUNCH" ] && [ ! -f "$LAUNCH" ]; then
  if [ -x "$INFO" ]; then
    "$INFO" -m "未找到 Emus/DOOM/launch.sh" -k "A" -fs 28
  fi
  exit 1
fi

if [ ! -d "$ROMDIR" ]; then
  mkdir -p "$ROMDIR" 2>/dev/null
fi

# Direct launch when another app passes a file
if [ -n "$1" ] && [ -f "$1" ]; then
  exec sh "$LAUNCH" "$1"
fi

if [ -x "$INFO" ]; then
  "$INFO" -m "把 WAD 放到 Roms/DOOM  然后选一个开打" -t 1.5 -fs 26
fi

if [ -z "$(find "$ROMDIR" -type f \( -iname '*.wad' -o -iname '*.iwad' -o -iname '*.pwad' -o -iname '*.pk3' -o -iname '*.ipk3' -o -iname '*.zip' -o -iname '*.7z' \) 2>/dev/null | head -n 1)" ]; then
  if [ -x "$INFO" ]; then
    "$INFO" -m "Roms/DOOM 里还没有 WAD。拷进去后再开。" -k "A" -fs 28
  fi
  exit 1
fi

out=$(selector -t "选择 DOOM WAD (B 取消)" -d "$ROMDIR") || exit 0
file="${out#*: }"
if [ ! -f "$file" ]; then
  exit 0
fi

exec sh "$LAUNCH" "$file"
