#!/bin/sh
# Moonlight — wrap the stock TrimUI streaming client (native gamepad).

export PATH="/mnt/SDCARD/System/bin:/mnt/SDCARD/System/usr/trimui/scripts:$PATH"
export LD_LIBRARY_PATH="/mnt/SDCARD/System/lib:/usr/trimui/lib:${LD_LIBRARY_PATH:-}"

INFO="/mnt/SDCARD/System/usr/trimui/scripts/infoscreen.sh"

TARGET=""
for p in /usr/trimui/apps/moonlight/launch.sh /usr/trimui/apps/Moonlight/launch.sh; do
  if [ -x "$p" ] || [ -f "$p" ]; then
    TARGET="$p"
    break
  fi
done

if [ -z "$TARGET" ]; then
  if [ -x "$INFO" ]; then
    "$INFO" -m "未找到系统 Moonlight (/usr/trimui/apps/moonlight)。需要官方固件自带的串流 App。" -k "A" -fs 26
  fi
  exit 1
fi

if [ -x "$INFO" ]; then
  "$INFO" -m "Moonlight  Select+Start退出  请先关蓝牙" -t 2 -fs 28
fi

echo performance >/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null
echo 1608000 >/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq 2>/dev/null
echo 1 >/tmp/stay_awake

cd "$(dirname "$TARGET")" || exit 1
sh "$TARGET"
rc=$?

rm -f /tmp/stay_awake
echo ondemand >/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null
exit $rc
