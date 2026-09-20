#!/bin/sh
# Kodi — drop-in wrapper. Official Kodi is heavy on A133P; use XMPlayer if unsure.
# MainUI execs this file. It MUST be Unix LF (CRLF shebang = 架构错误).

export PATH="/mnt/SDCARD/System/bin:/mnt/SDCARD/System/usr/trimui/scripts:$PATH"
export LD_LIBRARY_PATH="/mnt/SDCARD/System/lib:/usr/trimui/lib:${LD_LIBRARY_PATH:-}"

APPDIR=$(cd "$(dirname "$0")" && pwd)
INFO="/mnt/SDCARD/System/usr/trimui/scripts/infoscreen.sh"

say() {
  if [ -x "$INFO" ]; then
    "$INFO" -m "$1" -k "A" -fs 24
  fi
}

head4() {
  dd if="$1" bs=1 count=4 2>/dev/null
}

is_script() {
  [ -f "$1" ] || return 1
  [ "$(dd if="$1" bs=1 count=2 2>/dev/null)" = "#!" ]
}

is_elf() {
  [ -f "$1" ] || return 1
  [ "$(head4 "$1")" = "$(printf '\177ELF')" ]
}

# Reject Windows PE and common non-ARM64 ELF machines. Unknown ELF still runs.
wrong_arch() {
  [ -f "$1" ] || return 1
  [ "$(dd if="$1" bs=1 count=2 2>/dev/null)" = "MZ" ] && return 0
  is_elf "$1" || return 1
  set -- $(od -An -t x1 -N 20 "$1" 2>/dev/null | tr 'A-F' 'a-f')
  [ "$#" -ge 20 ] || return 1
  mach="$19$20"
  class="$5"
  [ "$class" != "02" ] && return 0
  case "$mach" in
    b700) return 1 ;;
    3e00|0300|2800|0800) return 0 ;;
  esac
  return 1
}

BIN=""
for p in \
  "$APPDIR/bin/kodi-standalone" \
  "$APPDIR/bin/kodi.bin" \
  "$APPDIR/bin/kodi-gbm" \
  "$APPDIR/bin/kodi" \
  "$APPDIR/kodi-standalone" \
  "$APPDIR/kodi.bin" \
  "$APPDIR/kodi.sh" \
  "$APPDIR/kodi"
do
  [ -f "$p" ] || continue
  BIN="$p"
  break
done

if [ -z "$BIN" ]; then
  say "Kodi 需要自备 Linux aarch64 二进制。放到 Apps/Kodi/bin/kodi 。不要用 Windows/Android 包。日常请用 XMPlayer。"
  exit 1
fi

if is_script "$BIN"; then
  RUN=script
elif wrong_arch "$BIN"; then
  say "架构错误：$(basename "$BIN") 不是 Linux aarch64 程序。请换成 kodi / kodi.bin（不要 Windows、Android、x86）。"
  exit 1
elif is_elf "$BIN"; then
  RUN=elf
else
  say "架构错误：$(basename "$BIN") 不是可执行的 Linux 程序。请换成 aarch64 的 kodi / kodi.bin。"
  exit 1
fi

echo performance >/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null
echo 1608000 >/sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq 2>/dev/null
echo 1 >/tmp/stay_awake

export HOME="${KODI_HOME:-$APPDIR}"
export LD_LIBRARY_PATH="$APPDIR/bin/lib:${LD_LIBRARY_PATH:-}"
cd "$(dirname "$BIN")" || exit 1
chmod +x "$BIN" 2>/dev/null

name=$(basename "$BIN")
if [ "$RUN" = "script" ]; then
  sh "$BIN" --standalone
  rc=$?
elif [ "$name" = "kodi.bin" ] || [ "$name" = "kodi-gbm" ]; then
  "$BIN"
  rc=$?
else
  "$BIN" --standalone
  rc=$?
fi

rm -f /tmp/stay_awake
echo ondemand >/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null
exit $rc
