#!/bin/sh
# Musikcube — official binary in TermSP if present, otherwise music hub + mpv.

export PATH="/mnt/SDCARD/System/bin:/mnt/SDCARD/System/usr/trimui/scripts:$PATH"
export LD_LIBRARY_PATH="/mnt/SDCARD/System/lib:/usr/trimui/lib:${LD_LIBRARY_PATH:-}"

. /mnt/SDCARD/System/usr/trimui/scripts/gamepadhub/common.sh
ghub_path

APPDIR=$(cd "$(dirname "$0")" && pwd)
cd "$APPDIR" || exit 1
chmod +x "$APPDIR/launch.sh" "$APPDIR/run_bin.sh" "$GHUB/run.sh" "$GHUB/play.sh" 2>/dev/null

run_official() {
  BIN=""
  for p in "$APPDIR/bin/musikcube" "$APPDIR/musikcube"; do
    if [ -x "$p" ]; then
      BIN="$p"
      break
    fi
  done
  [ -n "$BIN" ] || return 1

  export MUSIKCUBE_BIN="$BIN"
  GPTK="/mnt/SDCARD/Apps/PortMaster/PortMaster/gptokeyb2"
  if [ -x "$GPTK" ]; then
    "$GPTK" -1 "musikcube" -c "$GHUB/musikcube.gptk" &
    GPTK_PID=$!
  fi
  touch /var/trimui_inputd/sticks_disabled 2>/dev/null
  TERMDIR="/mnt/SDCARD/Apps/Terminal"
  if [ -x "$TERMDIR/TermSP" ]; then
    export LD_LIBRARY_PATH="$TERMDIR/lib:${LD_LIBRARY_PATH:-}"
    "$TERMDIR/TermSP" -s 16 -e "$APPDIR/run_bin.sh"
  elif [ -x "$TERMDIR/SimpleTerminal" ]; then
    "$TERMDIR/SimpleTerminal" -r "$APPDIR/run_bin.sh"
  else
    "$BIN"
  fi
  rm -f /var/trimui_inputd/sticks_disabled
  [ -n "$GPTK_PID" ] && kill "$GPTK_PID" 2>/dev/null
  return 0
}

if run_official; then
  exit $?
fi

export HUB_MODE="music"
export HUB_TITLE="Musikcube"
export HUB_SEL="/tmp/crossmix_musikcube.sel"
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
