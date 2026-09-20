#!/bin/sh
# Run a drop-in musikcube binary inside TermSP.

export PATH="/mnt/SDCARD/System/bin:/mnt/SDCARD/System/usr/trimui/scripts:${PATH:-}"
export LD_LIBRARY_PATH="/mnt/SDCARD/System/lib:/usr/trimui/lib:${LD_LIBRARY_PATH:-}"
export TERM="${TERM:-xterm-256color}"
export HOME="${HOME:-/mnt/SDCARD}"

APPDIR=$(cd "$(dirname "$0")" && pwd)
BIN="${MUSIKCUBE_BIN:-$APPDIR/bin/musikcube}"
if [ ! -x "$BIN" ]; then
  echo "musikcube binary not found"
  echo
  echo "Press any key..."
  read -r _
  exit 1
fi

export LD_LIBRARY_PATH="$APPDIR/bin/lib:${LD_LIBRARY_PATH:-}"
exec "$BIN"
