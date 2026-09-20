# Shared helpers for gamepad-friendly CrossMix apps.
# Source from launch.sh:  . /mnt/SDCARD/System/usr/trimui/scripts/gamepadhub/common.sh

GHUB="${GHUB:-/mnt/SDCARD/System/usr/trimui/scripts/gamepadhub}"
INFO="${INFO:-/mnt/SDCARD/System/usr/trimui/scripts/infoscreen.sh}"

ghub_path() {
  export PATH="/mnt/SDCARD/System/bin:/mnt/SDCARD/System/usr/trimui/scripts:${PATH:-}"
  export LD_LIBRARY_PATH="/mnt/SDCARD/System/lib:/usr/trimui/lib:/mnt/SDCARD/Apps/PortMaster/PortMaster:${LD_LIBRARY_PATH:-}"
}

ghub_info() {
  if [ -x "$INFO" ]; then
    "$INFO" "$@"
  fi
}

ghub_python() {
  _py=""
  for _c in /mnt/SDCARD/System/bin/python3.11 /mnt/SDCARD/System/bin/python3 python3.11 python3; do
    if [ -x "$_c" ]; then
      _py="$_c"
      break
    fi
    if command -v "$_c" >/dev/null 2>&1; then
      _py="$_c"
      break
    fi
  done
  echo "$_py"
}

ghub_run_term() {
  _inner="$1"
  _py=$(ghub_python)
  if [ -z "$_py" ]; then
    ghub_info -m "需要 Python 3.11，请先做一次 CrossMix 更新。" -k "A" -fs 28
    return 1
  fi
  export HUB_PYTHON="$_py"
  touch /var/trimui_inputd/sticks_disabled 2>/dev/null

  if [ -n "${SSH_TTY}${SSH_CONNECTION}" ] && [ -t 1 ]; then
    "$_py" "$GHUB/hub.py"
    _rc=$?
    rm -f /var/trimui_inputd/sticks_disabled
    return $_rc
  fi

  TERMDIR="/mnt/SDCARD/Apps/Terminal"
  if [ -x "$TERMDIR/TermSP" ]; then
    export LD_LIBRARY_PATH="$TERMDIR/lib:${LD_LIBRARY_PATH:-}"
    "$TERMDIR/TermSP" -s 16 -e "${_inner:-$GHUB/run.sh}"
  elif [ -x "$TERMDIR/SimpleTerminal" ]; then
    "$TERMDIR/SimpleTerminal" -r "${_inner:-$GHUB/run.sh}"
  else
    ghub_info -m "需要 Apps/Terminal 才能打开这个界面。" -k "A" -fs 28
    rm -f /var/trimui_inputd/sticks_disabled
    return 1
  fi
  rm -f /var/trimui_inputd/sticks_disabled
  return 0
}

ghub_play() {
  "$GHUB/play.sh" "$1"
}

ghub_selector_file() {
  _title="$1"
  _dir="$2"
  if [ ! -d "$_dir" ]; then
    return 1
  fi
  _out=$(selector -t "$_title" -d "$_dir") || return 1
  _file="${_out#*: }"
  [ -f "$_file" ] || return 1
  echo "$_file"
}
