#!/bin/sh
# Play a file, playlist, or URL with CrossMix mpv + gptokeyb2.

GHUB="/mnt/SDCARD/System/usr/trimui/scripts/gamepadhub"
TARGET="$1"

export PATH="/mnt/SDCARD/System/bin:/mnt/SDCARD/System/usr/trimui/scripts:${PATH:-}"
export LD_LIBRARY_PATH="/lib:/lib64:/usr/lib:/mnt/SDCARD/System/lib:/mnt/SDCARD/Apps/PortMaster/PortMaster:${LD_LIBRARY_PATH:-}"

if [ -z "$TARGET" ]; then
  exit 1
fi

echo performance >/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null
echo 1608000 >/sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq 2>/dev/null
echo 1 >/tmp/stay_awake

cleanup() {
  rm -f /tmp/stay_awake
  [ -n "$GPTK_PID" ] && kill "$GPTK_PID" 2>/dev/null
  [ -n "$THD_PID" ] && kill "$THD_PID" 2>/dev/null
  echo ondemand >/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null
}
trap cleanup EXIT INT TERM HUP

GPTK="/mnt/SDCARD/Apps/PortMaster/PortMaster/gptokeyb2"
if [ -x "$GPTK" ]; then
  "$GPTK" -1 "mpv" -c "$GHUB/keys.gptk" &
  GPTK_PID=$!
fi
if [ -x /mnt/SDCARD/System/bin/thd ] && [ -f "$GHUB/thd.conf" ]; then
  /mnt/SDCARD/System/bin/thd --triggers "$GHUB/thd.conf" /dev/input/event3 &
  THD_PID=$!
fi

MPV=""
for c in /mnt/SDCARD/System/bin/mpv mpv; do
  if [ -x "$c" ]; then
    MPV="$c"
    break
  fi
  if command -v "$c" >/dev/null 2>&1; then
    MPV="$c"
    break
  fi
done

if [ -z "$MPV" ]; then
  if [ -x /mnt/SDCARD/System/usr/trimui/scripts/infoscreen.sh ]; then
    /mnt/SDCARD/System/usr/trimui/scripts/infoscreen.sh -m "未找到 mpv。请确认 CrossMix 已完整安装。" -k "A" -fs 28
  fi
  exit 1
fi

HOME="${HUB_APPDIR:-$GHUB}"
export HOME

EXTRA="--fullscreen --audio-buffer=1 --terminal=no"
case "$TARGET" in
  http://*|https://*|rtsp://*|rtmp://*|rtsps://*)
    EXTRA="$EXTRA --cache=yes --network-timeout=20"
    ;;
esac
case "$TARGET" in
  *.m3u|*.m3u8|*.M3U|*.M3U8)
    EXTRA="$EXTRA --cache=yes"
    ;;
esac

# shellcheck disable=SC2086
"$MPV" $EXTRA -- "$TARGET"
exit $?
