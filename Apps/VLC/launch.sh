#!/bin/sh
# VLC — Apps-menu video player for TrimUI Smart Pro / CrossMix-OS
# Uses CrossMix mpv (and the stock hardware player). Official VideoLAN
# is not available for this device; drop a binary in Apps/VLC/bin/vlc to use it.

echo performance >/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null
echo 1608000 >/sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq 2>/dev/null

export PATH="/mnt/SDCARD/System/bin:/mnt/SDCARD/System/usr/trimui/scripts:$PATH"
export LD_LIBRARY_PATH="/mnt/SDCARD/System/lib:/usr/trimui/lib:${LD_LIBRARY_PATH:-}"

APPDIR=$(cd "$(dirname "$0")" && pwd)
cd "$APPDIR" || exit 1
chmod +x "$APPDIR/launch.sh" "$APPDIR/run.sh" "$APPDIR/play.sh" 2>/dev/null

SEL="/tmp/crossmix_vlc.sel"
INFO="/mnt/SDCARD/System/usr/trimui/scripts/infoscreen.sh"

play_target() {
  "$APPDIR/play.sh" "$1"
}

open_stock() {
  for p in /usr/trimui/apps/player/launch.sh /usr/trimui/apps/videoplayer/launch.sh; do
    if [ -x "$p" ]; then
      echo 1 >/tmp/stay_awake
      "$p"
      rm -f /tmp/stay_awake
      return 0
    fi
  done
  if [ -x "$INFO" ]; then
    "$INFO" -m "未找到系统播放器 (/usr/trimui/apps/player)。" -k "A" -fs 28
  fi
  return 1
}

run_picker() {
  export VLC_MODE="${1:-browse}"
  export VLC_SEL="$SEL"
  rm -f "$SEL"

  PY=""
  for c in /mnt/SDCARD/System/bin/python3.11 /mnt/SDCARD/System/bin/python3 python3.11 python3; do
    if [ -x "$c" ]; then
      PY="$c"
      break
    fi
    if command -v "$c" >/dev/null 2>&1; then
      PY="$c"
      break
    fi
  done

  if [ -z "$PY" ]; then
    if [ -x "$INFO" ]; then
      "$INFO" -m "VLC 需要 Python 3.11，请先做一次 CrossMix 更新。" -k "A" -fs 28
    fi
    return 1
  fi
  export VLC_PYTHON="$PY"

  touch /var/trimui_inputd/sticks_disabled 2>/dev/null

  if [ -n "${SSH_TTY}${SSH_CONNECTION}" ] && [ -t 1 ]; then
    "$PY" "$APPDIR/vlc.py"
  else
    TERMDIR="/mnt/SDCARD/Apps/Terminal"
    if [ -x "$TERMDIR/TermSP" ]; then
      export LD_LIBRARY_PATH="$TERMDIR/lib:${LD_LIBRARY_PATH:-}"
      "$TERMDIR/TermSP" -s 16 -e "$APPDIR/run.sh"
    elif [ -x "$TERMDIR/SimpleTerminal" ]; then
      "$TERMDIR/SimpleTerminal" -r "$APPDIR/run.sh"
    else
      if [ -x "$INFO" ]; then
        "$INFO" -m "需要 Apps/Terminal 才能浏览文件。可按 Y 使用系统播放器。" -k "A" -fs 28
      fi
      rm -f /var/trimui_inputd/sticks_disabled
      return 1
    fi
  fi

  rm -f /var/trimui_inputd/sticks_disabled
  return 0
}

handle_sel() {
  [ -f "$SEL" ] || return 1
  kind=$(sed -n '1p' "$SEL")
  payload=$(sed -n '2p' "$SEL")
  rm -f "$SEL"
  case "$kind" in
    stock)
      open_stock
      ;;
    file|url|playlist)
      [ -n "$payload" ] && play_target "$payload"
      ;;
    *)
      return 1
      ;;
  esac
  return 0
}

# Direct play when another app passes a file or URL
if [ -n "$1" ]; then
  case "$1" in
    --stock) open_stock ;;
    *) play_target "$1" ;;
  esac
  exit $?
fi

# Main menu. Hold L at launch to skip and go straight to the file list.
skip_menu=0
if [ -x /mnt/SDCARD/System/usr/trimui/scripts/button_state.sh ]; then
  /mnt/SDCARD/System/usr/trimui/scripts/button_state.sh L
  [ $? -eq 10 ] && skip_menu=1
fi

if [ "$skip_menu" -eq 0 ]; then
  if [ -x "$INFO" ]; then
    button=$("$INFO" -m "VLC  A浏览(mpv)  Y系统硬解  X网络串流  B退出" -k "A Y X B MENU" -fs 28 -c orange)
  else
    button="A"
  fi

  case "$button" in
    Y)
      open_stock
      exit $?
      ;;
    X)
      run_picker stream
      handle_sel
      exit $?
      ;;
    B|MENU|"")
      exit 0
      ;;
  esac
fi

while true; do
  run_picker browse || exit 1
  if [ ! -f "$SEL" ]; then
    exit 0
  fi
  handle_sel || exit 0
done
