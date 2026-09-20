#!/bin/sh
# Azahar / Lime3DS — drop-in wrapper. TSP can only do very light 3DS titles.

export PATH="/mnt/SDCARD/System/bin:/mnt/SDCARD/System/usr/trimui/scripts:$PATH"
export LD_LIBRARY_PATH="/usr/trimui/lib:/mnt/SDCARD/System/lib:${LD_LIBRARY_PATH:-}"

if [ -n "$1" ] && [ -f "$1" ]; then
  source /mnt/SDCARD/System/usr/trimui/scripts/common_launcher.sh
fi

EMU_DIR="${EMU_DIR:-$(cd "$(dirname "$0")" && pwd)}"
INFO="/mnt/SDCARD/System/usr/trimui/scripts/infoscreen.sh"

BIN=""
for p in "$EMU_DIR/bin/azahar" "$EMU_DIR/bin/lime3ds" "$EMU_DIR/azahar" "$EMU_DIR/lime3ds"; do
  if [ -x "$p" ]; then
    BIN="$p"
    break
  fi
done

if [ -z "$BIN" ]; then
  if [ -x "$INFO" ]; then
    "$INFO" -m "Azahar 需要自备 aarch64 二进制。放到 Emus/3DS/bin/azahar 。TSP 只能碰很轻的 3DS。" -k "A" -fs 24
  fi
  exit 1
fi

ROM=""
if [ -n "$1" ] && [ -f "$1" ]; then
  ROM="$1"
fi

if [ -x /mnt/SDCARD/System/usr/trimui/scripts/cpufreq.sh ]; then
  cpufreq.sh performance 7 7
else
  echo performance >/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null
  echo 1608000 >/sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq 2>/dev/null
fi
echo 1 >/tmp/stay_awake

export HOME="${AZAHAR_HOME:-$EMU_DIR}"
export LD_LIBRARY_PATH="$EMU_DIR/bin/lib:${LD_LIBRARY_PATH:-}"
cd "$(dirname "$BIN")" || exit 1
if [ -n "$ROM" ]; then
  "$BIN" "$ROM"
  rc=$?
else
  "$BIN"
  rc=$?
fi

rm -f /tmp/stay_awake
exit $rc
