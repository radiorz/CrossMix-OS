#!/bin/sh
# XMPlayer — official drop-in if present, otherwise CrossMix media hub + mpv.

export PATH="/mnt/SDCARD/System/bin:/mnt/SDCARD/System/usr/trimui/scripts:$PATH"
export LD_LIBRARY_PATH="/mnt/SDCARD/System/lib:/usr/trimui/lib:${LD_LIBRARY_PATH:-}"

. /mnt/SDCARD/System/usr/trimui/scripts/gamepadhub/common.sh
ghub_path

APPDIR=$(cd "$(dirname "$0")" && pwd)
cd "$APPDIR" || exit 1
chmod +x "$APPDIR/launch.sh" "$GHUB/run.sh" "$GHUB/play.sh" 2>/dev/null

run_official() {
  for p in \
    "$APPDIR/XMPlayer.sh" \
    "$APPDIR/xmplayer/XMPlayer.sh" \
    /mnt/SDCARD/Roms/PORTS/XMPlayer.sh \
    /mnt/SDCARD/Roms/PORTS/xmplayer.sh
  do
    if [ -f "$p" ]; then
      controlfolder="/mnt/SDCARD/Apps/PortMaster/PortMaster"
      if [ -f "$controlfolder/control.txt" ]; then
        # shellcheck disable=SC1091
        . "$controlfolder/control.txt"
      fi
      cd "$(dirname "$p")" || return 1
      chmod +x "$p" 2>/dev/null
      sh "$p"
      return 0
    fi
  done
  return 1
}

if run_official; then
  exit $?
fi

export HUB_MODE="xmb"
export HUB_TITLE="XMPlayer"
export HUB_SEL="/tmp/crossmix_xmplayer.sel"
export HUB_APPDIR="$APPDIR"

if [ -n "$1" ]; then
  ghub_play "$1"
  exit $?
fi

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
    file|playlist|url)
      [ -n "$payload" ] && ghub_play "$payload"
      ;;
    *)
      exit 0
      ;;
  esac
done
