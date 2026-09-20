#!/bin/sh
# Ren'Py — pick a visual novel (script or folder) with the gamepad.

export PATH="/mnt/SDCARD/System/bin:/mnt/SDCARD/System/usr/trimui/scripts:$PATH"
export LD_LIBRARY_PATH="/mnt/SDCARD/System/lib:/usr/trimui/lib:${LD_LIBRARY_PATH:-}"

. /mnt/SDCARD/System/usr/trimui/scripts/gamepadhub/common.sh
ghub_path

APPDIR=$(cd "$(dirname "$0")" && pwd)
cd "$APPDIR" || exit 1
mkdir -p "$APPDIR/games" 2>/dev/null
chmod +x "$APPDIR/launch.sh" "$GHUB/run.sh" 2>/dev/null

run_game() {
  target="$1"
  if [ -z "$target" ]; then
    return 1
  fi
  if [ -f "$target" ]; then
    chmod +x "$target" 2>/dev/null
    cd "$(dirname "$target")" || return 1
    sh "$target"
    return $?
  fi
  if [ -d "$target" ]; then
    if [ -f "$target/launch.sh" ]; then
      chmod +x "$target/launch.sh" 2>/dev/null
      cd "$target" || return 1
      sh "./launch.sh"
      return $?
    fi
    for b in "$APPDIR/bin/renpy" "$APPDIR/renpy" "$target/renpy.sh"; do
      if [ -x "$b" ]; then
        export LD_LIBRARY_PATH="$APPDIR/bin/lib:${LD_LIBRARY_PATH:-}"
        "$b" "$target"
        return $?
      fi
    done
    ghub_info -m "这个目录没有 launch.sh。把游戏自带启动脚本放进去，或把 renpy 放到 Apps/RenPy/bin/renpy。" -k "A" -fs 24
    return 1
  fi
  return 1
}

if [ -n "$1" ]; then
  run_game "$1"
  exit $?
fi

export HUB_MODE="scripts"
export HUB_TITLE="Ren'Py"
export HUB_SEL="/tmp/crossmix_renpy.sel"
export HUB_APPDIR="$APPDIR"
export HUB_ROOTS="$APPDIR/games|/mnt/SDCARD/Roms/RENPY|/mnt/SDCARD/Roms/PORTS"

while true; do
  rm -f "$HUB_SEL"
  ghub_run_term "$GHUB/run.sh" || exit 1
  if [ ! -f "$HUB_SEL" ]; then
    exit 0
  fi
  kind=$(sed -n '1p' "$HUB_SEL")
  payload=$(sed -n '2p' "$HUB_SEL")
  rm -f "$HUB_SEL"
  case "$kind" in
    run|renpy)
      run_game "$payload"
      ;;
    *)
      exit 0
      ;;
  esac
done
