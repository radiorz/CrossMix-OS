#!/bin/sh
# PSPMAN — official PocketJS music player, launched through CrossMix PPSSPP.
# Game files: /mnt/SDCARD/Roms/PSP/PSPMAN/
# Music:      PPSSPP memstick MUSIC/ or PSP/MUSIC/

echo performance >/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null
echo 1608000 >/sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq 2>/dev/null

export PATH="/mnt/SDCARD/System/bin:/mnt/SDCARD/System/usr/trimui/scripts:$PATH"
export LD_LIBRARY_PATH="/mnt/SDCARD/System/lib:/usr/trimui/lib:${LD_LIBRARY_PATH:-}"

ROM="/mnt/SDCARD/Roms/PSP/PSPMAN/EBOOT.PBP"
EMU="/mnt/SDCARD/Emus/PSP"
LAUNCH="$EMU/ppsspp_1.17.1_vulkan.sh"
INFO="/mnt/SDCARD/System/usr/trimui/scripts/infoscreen.sh"

if [ ! -f "$ROM" ]; then
  if [ -x "$INFO" ]; then
    "$INFO" -m "缺少 Roms/PSP/PSPMAN/EBOOT.PBP" -k "A" -fs 28
  fi
  exit 1
fi

if [ ! -x "$LAUNCH" ]; then
  if [ -x "$INFO" ]; then
    "$INFO" -m "缺少 Emus/PSP/ppsspp_1.17.1_vulkan.sh" -k "A" -fs 28
  fi
  exit 1
fi

# Expose CrossMix Roms/MUSIC when the PPSSPP memstick library is still empty.
MS_ROOT="/mnt/SDCARD/Emus/PSP/PPSSPP_1.17.1/.config/ppsspp"
mkdir -p "$MS_ROOT/MUSIC" "$MS_ROOT/PSP/MUSIC"
if [ -d /mnt/SDCARD/Roms/MUSIC ]; then
  has_tracks=$(find "$MS_ROOT/MUSIC" "$MS_ROOT/PSP/MUSIC" -type f \( -iname '*.mp3' -o -iname '*.flac' \) 2>/dev/null | head -n 1)
  if [ -z "$has_tracks" ]; then
    mount --bind /mnt/SDCARD/Roms/MUSIC "$MS_ROOT/MUSIC" 2>/dev/null || true
  fi
fi

# Same launcher MainUI uses for PSP → keeps saves, backend, CPU profile.
exec "$LAUNCH" "$ROM"
