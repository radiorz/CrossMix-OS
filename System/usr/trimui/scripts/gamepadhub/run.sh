#!/bin/sh
# Inner launcher: runs hub.py inside TermSP / SimpleTerminal.

export PATH="/mnt/SDCARD/System/bin:/mnt/SDCARD/System/usr/trimui/scripts:${PATH:-}"
export LD_LIBRARY_PATH="/mnt/SDCARD/System/lib:/usr/trimui/lib:${LD_LIBRARY_PATH:-}"
export TERM="${TERM:-xterm-256color}"
export LANG="${LANG:-en_US.UTF-8}"
export LC_ALL="${LC_ALL:-en_US.UTF-8}"
export PYTHONIOENCODING="utf-8"
export PYTHONUNBUFFERED="1"
export HOME="${HOME:-/mnt/SDCARD}"

GHUB="/mnt/SDCARD/System/usr/trimui/scripts/gamepadhub"
cd "$GHUB" || exit 1

PY="${HUB_PYTHON:-}"
if [ -z "$PY" ]; then
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
fi

if [ -z "$PY" ]; then
  echo "gamepadhub: python3.11 not found"
  echo
  echo "Press any key..."
  read -r _
  exit 1
fi

exec "$PY" "$GHUB/hub.py"
