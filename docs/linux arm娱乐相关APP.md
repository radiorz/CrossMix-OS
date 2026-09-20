# Linux ARM64（树莓派、RK3588、香橙派、国产 ARM 桌面）娱乐软件清单

>
> 优先**原生 ARM64**；x86 程序需要 Box64/FEX 转译，性能取决于 SOC 显卡（RK3588 最好，老 RK3326 弱很多）
>
> 手柄一句话：游戏类软件大多**原生读手柄**；影音 / 桌面软件多数只认键盘鼠标，掌机上要用 **gptokeyb** 把按键翻译成键盘。

图例：

| 标记 | 含义 |
|---|---|
| 原生手柄 | 自己读 SDL / evdev / joystick，插上手柄就能用 |
| 映射手柄 | 本身是键盘软件，掌机上要挂 `gptokeyb` / `gptokeyb2` |
| 不适合手柄 | 依赖鼠标、触控板、桌面窗口，硬映射也别扭 |
| CrossMix 已有 | TrimUI Smart Pro / CrossMix-OS 里已经能用 |

## 🎬 影音播放

1. **mpv**：轻量万能播放器，原生 ARM，硬解强，树莓派 / 香橙派标配
   - 手柄：**映射手柄**（可选 `input-gamepad=yes`，但掌机上不稳定，CrossMix 不用这条）
   - CrossMix：`Emus/VIDEOS`、`Emus/MUSIC`、`Apps/VLC` 都用 **gptokeyb2 + keys.gptk**
   - TSP 播放键：A/B/Start 暂停，左右 5 秒，上下 1 分钟，L1/R1 上一首/下一首，MENU 退出
2. **Kodi**：家庭媒体中心，本地影片、IPTV、插件生态，LibreELEC 就是专门给 ARM 做的 Kodi 系统
   - 手柄：**原生手柄**（装 `kodi-peripheral-joystick` / Joystick Support 插件）
   - 十英尺 UI，电视盒很好用；TSP 上体积大、CPU 重，不建议往 CrossMix 里塞
3. **MoonPlayer**：国产简洁播放器，ARM64 原生，字幕体验好（深度 / 统信 UOS 商店有）
   - 手柄：**不适合手柄**（Qt 桌面，鼠标优先）
4. **VLC**：老牌播放器，ARM64 原生，兼容性广，但硬解不如 mpv
   - 手柄：官方 Qt 界面 **不适合手柄**；无界面的 `cvlc` 可映射
   - CrossMix：**已有 `Apps/VLC`**，浏览用 TermSP 按键，播放走 mpv + gptokeyb2。官方 VideoLAN 没有 TSP 包
5. **XMPlayer**：掌机 Linux（muOS/ArkOS）专用媒体中心，图片 / 音乐 / 视频一体
   - 手柄：**原生菜单 + 映射播放**（XMB 用手柄逛，底层仍是 mpv/ffplay + gptokeyb2）
   - 最接近「掌机专用 VLC」，有 PortMaster 测试包，比 Kodi 更适合 TSP

## 🎵 音乐

1. **Lollypop**：GNOME 精美音乐播放器，管理本地曲库、自动封面
   - 手柄：**不适合手柄**（GTK 桌面）
2. **Audacious**：复古 XMMS 风格播放器，低资源占用
   - 手柄：**映射手柄**（快捷键多，gptokeyb 能凑合）
3. **musikcube**：终端 TUI 音乐播放器，跨平台 ARM，适合无桌面环境
   - 手柄：**映射手柄**（方向 / A 确认 / B 返回即可）
   - TSP 上可塞进 TermSP，但 CrossMix 已有 `Apps/MusicPlayer`（GMU），更省事
4. **网易云音乐（web 版 / 第三方 electron 客户端）**：ARM64 有社区打包版
   - 手柄：**不适合手柄**
5. **Spotify**：官方 Linux 客户端支持 ARM64
   - 手柄：**不适合手柄**（桌面客户端）；掌机更现实的是系统播放器播本地下载

CrossMix 已有：`Apps/MusicPlayer`（GMU，手柄原生/映射都齐）、`Emus/MUSIC`（mpv + gptokeyb）。

## 🎮 模拟器 & 复古游戏（ARM 生态最强部分）

1. **RetroArch**：全能模拟器前端，FC/SFC/MD/GBA/NDS/PS1，原生 ARM，树莓派、RK 掌机标配
   - 手柄：**原生手柄**（SDL gamecontroller，热键可配）
   - CrossMix：**已有**，这是机子的主战场
2. **PPSSPP**：PSP 模拟器，ARM 原生，RK3588 可高分辨率运行 PSP 游戏
   - 手柄：**原生手柄**
   - CrossMix：**已有** `Emus/PSP`（OpenGL / Vulkan）
3. **Azahar（Lime3DS）**：3DS 模拟器，ARM64 可用，RK3588 可玩部分 3DS 游戏
   - 手柄：**原生手柄**（触控还要屏幕）
   - CrossMix：**已有** `Emus/3DS` 启动器（需自备 `Emus/3DS/bin/azahar`）
   - TSP（A133P）只能碰很轻的 3DS，别对 RK3588 的体验
4. **RetroPie**：树莓派专用复古游戏系统，打包全套模拟器 + 前端
   - 手柄：**原生手柄**（EmulationStation）
   - 不是单个 App，是整套系统；CrossMix 已经覆盖同一件事
5. **PortMaster**：掌机 Linux（muOS/JELOS），移植 PC 独立小游戏（星露谷物语、DOOM、半条命等）
   - 手柄：**原生手柄** 或 **映射手柄**（每个 port 自己带 gptokeyb / SDL 配置）
   - CrossMix：**已有** `Apps/PortMaster`
6. **Box64 / Box86**：x86_64/x86 转译层，ARM64 上跑 Linux x86 游戏，搭配 Wine 跑 Windows 游戏
   - 手柄：取决于游戏本身；很多 Windows 游戏还要鼠标
   - TSP 算力不够跑 3A，RK3588 桌面机才有意义
7. **FEX-Emu**：高性能 x86 转译，Ubuntu ARM 可用，可跑 Steam（实验版 Steam Snap）
   - 手柄：Steam Input 可以，但不是掌机方案

## 🎮 原生独立游戏 & 串流

- **Minecraft（Java 版）**：ARM 原生可跑，树莓派 5/RK3588 流畅
  - 手柄：**映射手柄**（官方以键鼠为主，需模组或 gptokeyb）；触控也不完整
- **DOOM、Quake**：开源移植，原生 ARM，极低资源
  - 手柄：**原生手柄**（Chocolate / GZDoom / TyrQuake 都认 SDL）
  - CrossMix：**已有** `Emus/DOOM`、`Emus/TYRQUAKE`
- **Moonlight**：串流客户端，从 Windows 主机串流 3A 游戏到 ARM 小主机；配套 **Sunshine**（Windows 端串流服务端）
  - 手柄：**原生手柄**（机身键当 Xbox 手柄转发给主机，这是它存在的意义）
  - TSP 固件自带 `/usr/trimui/apps/moonlight`；CrossMix 启动时会把 CPU 拉到 performance
  - 退出：**Select + Start**。串流时关掉蓝牙，否则抢 Wi-Fi
- **Steam（ARM64 Snap）**：Ubuntu ARM 实验版，内置 FEX 转译跑 x86 游戏，性能要求高
  - 手柄：Steam Input **原生**，但 TSP 装不了这套桌面栈
- **GCompris**：儿童益智小游戏合集，ARM 原生
  - 手柄：部分活动认手柄，整体仍是 **桌面/触控**，掌机体验一般

## 🖼️ 创意娱乐

- **Krita**：绘画软件，ARM64 原生，RK3588 / 树莓派 5 可用，手绘板支持
  - 手柄：**不适合手柄**（要数位板 / 触控）
- **OBS Studio**：录屏直播，ARM64 原生，RK3588 硬编码可用
  - 手柄：**不适合手柄**
  - CrossMix 录屏走 `Apps/ScreenRecorder`，不是 OBS
- **GIMP**：开源图片修图，ARM 原生，替代 PS
  - 手柄：**不适合手柄**

## 🧩 国产 ARM 桌面（统信 UOS/Deepin）额外娱乐 App

- QQ 音乐、网易云音乐（商店 ARM 包）— **不适合手柄**
- 云游戏客户端：云原神网页版 / 打包客户端 — 手柄看客户端，网页版通常很差
- Ren'Py 启动器（彩咲乙女），直接玩 Ren'Py 视觉小说
  - 手柄：**映射 / 半原生**（Ren'Py 认手柄：A 推进、B 回退）；PortMaster 上已有不少移植

## 🎮 手柄怎么接（尤其是 TrimUI Smart Pro / CrossMix）

机身键在 Linux 里是标准手柄（`TRIMUI Player1`，一般是 `/dev/input/event3` 或 `event4`）。软件吃手柄只有三条路：

| 路 | 做法 | 适合 |
|---|---|---|
| 1. 原生 SDL | 程序自己 `SDL_GameController` / joystick | RetroArch、PPSSPP、Moonlight、多数 PortMaster 游戏 |
| 2. gptokeyb | `Apps/PortMaster/PortMaster/gptokeyb2 -1 程序名 -c keys.gptk` | mpv、桌面播放器、TUI、只认键盘的移植 |
| 3. 终端转键 | 挂在 TermSP / SimpleTerminal 里，A=Enter、B=退格、MENU=ESC | `Apps/TermView`、`Apps/VLC` 的文件浏览 |

**不要原生手柄和 gptokeyb 同时开。** 例如 mpv 开了 `input-gamepad=yes` 再挂 gptokeyb，会双触发、甚至卡住。CrossMix 的 mpv 只走 gptokeyb。

写 `keys.gptk` 时对照程序自己的快捷键。mpv 这一套 CrossMix 已经定好了（`Emus/VIDEOS/keys.gptk`，`Apps/VLC` 原样复用）：

```
start / a / b = enter     # 暂停
left / right              # 快进退 5 秒
up / down                 # 快进退 1 分钟
l1 = b                    # 上一首
r1 = n                    # 下一首
guide / back_up = q       # 退出（会记进度）
```

MENU 长按杀进程用 `thd`：`BTN_MODE 1 sleep 1.2;killall -9 mpv;`

## ✅ 简单选型建议

- 只看电影：**mpv**（桌面原生；TSP 用 `Apps/VLC` 或 `Emus/VIDEOS`）
- 家庭影音盒子：**Kodi**（电视 / RK3588，不要上 TSP）
- 掌机媒体中心：优先 **XMPlayer** 或现成的 **mpv + MusicPlayer**
- 复古怀旧游戏：**RetroArch**（TSP 已装好）
- 串流玩 PC 大作：**Moonlight**（TSP 固件自带，手柄直通）
- 想跑 Windows 游戏：RK3588 + Box64/Wine，不是 TSP
- 做 CrossMix App：游戏走 SDL 手柄；影音 / TUI 走 gptokeyb，别指望官方 Qt/GTK 自己认机身键

## TSP 上已经打成 Apps 的（手柄可用）

拷到 SD 卡后，应用列表里会多出这些入口。已经存在的不重复造：`RetroArch`、`PortMaster`、`MusicPlayer`、`VLC`。

| App | 手柄 | 机子上实际跑什么 |
|---|---|---|
| **Moonlight** | 原生 | 固件自带 `/usr/trimui/apps/moonlight`，Select+Start 退出 |
| **XMPlayer** | 映射 | 默认：视频/音乐/图片浏览 + mpv + gptokeyb；若放入官方 `XMPlayer.sh` 则优先跑官方包 |
| **Musikcube** | 映射 | 默认：扫 `Roms/MUSIC` + mpv；若放入 `bin/musikcube` 则在 TermSP 里跑官方 TUI |
| **Ren'Py** | 映射 | 浏览 `Apps/RenPy/games`、`Roms/RENPY`、`Roms/PORTS`，启动 `launch.sh` |
| **Kodi** | 原生 | **只有启动器**，把 aarch64 `kodi` 放到 `Apps/Kodi/bin/` 才会启动 |

没做成 App 的（没法在 TSP 上真跑，或已经是整套系统）：

- RetroPie、Steam、FEX、Box64：不是单个 App
- Audacious、Minecraft、GCompris：桌面/键鼠软件，硬包也几乎不能玩
- 官方 VLC Qt、Lollypop、Spotify、网易云、Krita、OBS、GIMP：不适合手柄

共享实现：`System/usr/trimui/scripts/gamepadhub/`（浏览界面、mpv 播放、`keys.gptk`）。

>
> 限制提醒：
> 很多 Windows 原生大型 3A **没有 ARM 原生**，靠转译会掉帧；RK3326、全志 H6 / A133P 这类弱芯片，3A 和重桌面播放器都别指望。手柄再好，算力不够也没用。
