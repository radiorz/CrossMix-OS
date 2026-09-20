#!/bin/sh
# WebDesk — LAN web terminal + file manager. HTTP lives only while this app is open.

echo performance >/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null
echo 1416000 >/sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq 2>/dev/null

touch /var/trimui_inputd/sticks_disabled 2>/dev/null

export PATH="/mnt/SDCARD/System/bin:/mnt/SDCARD/System/usr/trimui/scripts:$PATH"
export LD_LIBRARY_PATH="/mnt/SDCARD/System/lib:/usr/trimui/lib:${LD_LIBRARY_PATH:-}"

APPDIR=$(cd "$(dirname "$0")" && pwd)
cd "$APPDIR" || exit 1

cleanup() {
  if [ -f /tmp/webdesk.pid ]; then
    pid=$(cat /tmp/webdesk.pid)
    if [ -n "$pid" ] && [ -d "/proc/$pid" ]; then
      kill "$pid" 2>/dev/null
      sleep 0.2
      kill -9 "$pid" 2>/dev/null
    fi
    rm -f /tmp/webdesk.pid
  fi
  rm -f /var/trimui_inputd/sticks_disabled
}
trap cleanup EXIT INT TERM

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
  if [ -x /mnt/SDCARD/System/usr/trimui/scripts/infoscreen.sh ]; then
    /mnt/SDCARD/System/usr/trimui/scripts/infoscreen.sh -m "WebDesk needs Python 3.11. Run a CrossMix update first." -k "A"
  fi
  exit 1
fi

export WEBDESK_PYTHON="$PY"
chmod +x "$APPDIR/run.sh" "$APPDIR/launch.sh" 2>/dev/null

if [ -n "${SSH_TTY}${SSH_CONNECTION}" ] && [ -t 1 ]; then
  "$PY" "$APPDIR/webdesk.py"
  exit $?
fi

TERMDIR="/mnt/SDCARD/Apps/Terminal"

if [ -x "$TERMDIR/TermSP" ]; then
  export LD_LIBRARY_PATH="$TERMDIR/lib:${LD_LIBRARY_PATH:-}"
  "$TERMDIR/TermSP" -s 16 -e "$APPDIR/run.sh"
elif [ -x "$TERMDIR/SimpleTerminal" ]; then
  "$TERMDIR/SimpleTerminal" -r "$APPDIR/run.sh"
else
  if [ -x /mnt/SDCARD/System/usr/trimui/scripts/infoscreen.sh ]; then
    /mnt/SDCARD/System/usr/trimui/scripts/infoscreen.sh -m "Apps/Terminal not found." -k "A"
  fi
  exit 1
fi

exit 0
