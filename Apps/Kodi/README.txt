Kodi for CrossMix-OS

这里只有启动器，没有官方 Kodi 本体（体积大，A133P 会很卡）。
如果有 Linux aarch64 的 kodi / kodi-standalone / kodi.bin：
  放到 Apps/Kodi/bin/kodi
  库放到 Apps/Kodi/bin/lib/

不要用 Windows、Android APK、x86 包，MainUI 会报「架构错误」。
launch.sh 必须是 Unix LF 换行（Windows CRLF 的 #!/bin/sh 也会报架构错误）。

Kodi 自己认手柄（peripheral.joystick），不要再挂 gptokeyb。

日常看电影请用 Apps/XMPlayer 或 Apps/VLC。
