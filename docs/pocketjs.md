# PocketJS 示例应用 × CrossMix-OS

[PocketJS](https://pocketjs.dev/) 是一套把 Solid / Vue Vapor / Octane 编成原生像素的运行时：QuickJS guest + Rust core，没有浏览器 / DOM。官方和社区已经做了一批完整应用，目标机主要是 **PSP、PS Vita、Nintendo 3DS、Mac、老 iPhone**，不是 Linux ARM 掌机。

本仓库的 CrossMix-OS（TrimUI Smart Pro / Brick）能直接用的只有 **PPSSPP**。  
结论先说：**能上机的做成 `Roms/PSP/*.pbp`（homebrew EBOOT），不要转 ISO。**

---

## 0. 本仓库已经装好的

| 状态 | 应用 | 位置 |
| --- | --- | --- |
| **已装，可玩** | **PSPMAN 0.1.0-alpha.5**（官方包，SHA-256 已校验） | `Roms/PSP/PSPMAN/EBOOT.PBP` + `Apps/PSPMAN` |
| 未装（无预编译包，本机缺 PSP LLVM） | Pocket Figma / 引擎 demo | 见第 3 节，Linux/macOS 上 `bun run psp -- -r` |
| 未装（要自备版权素材） | Pocket Voxel、OpenStrike | 见第 3 节 |
| 不装 | YouTube / Map / Doc / Term / Shell-3DS | 依赖 Mac 伴侣或 3DS 模拟器 |

### 上机怎么开 PSPMAN

1. 把 SD 卡上的这套 CrossMix 原样拷回掌机（或直接在卡上用本仓库）。
2. **Apps → PSPMAN**，或 **PSP → PSPMAN 文件夹 → EBOOT.PBP**。
3. 模拟器选 **PPSSPP 1.17.1 Vulkan（性能）**。
4. 放音乐（立体声 16-bit/44.1 kHz FLAC，或 44.1 kHz MP3）：
   - `Emus/PSP/PPSSPP_1.17.1/.config/ppsspp/MUSIC/`
   - 或 `Emus/PSP/PPSSPP_1.17.1/.config/ppsspp/PSP/MUSIC/`
   - 或已有的 `Roms/MUSIC/`（Apps 入口会尝试 bind 过去；PSP 列表进游戏则不会）
5. 第一次扫描可能要等一会儿。操作：十字选，✕ 确定，○ 返回，START 播放/暂停，□ 曲库/正在播放，L/R 切歌。

完整文件夹也镜像在 PPSSPP 记忆棒：`Emus/PSP/PPSSPP_1.17.1/.config/ppsspp/PSP/GAME/PSPMAN/`。`assets/japanese.pjpf` 必须和 `EBOOT.PBP` 在一起，不要只拷一个 PBP。

---

## 1. 示例应用清单

### 1.1 官网 Ecosystem 主推（完整产品）

| 应用 | 仓库 / 来源 | 官方目标 | 做什么 | CrossMix 能不能跑 |
| --- | --- | --- | --- | --- |
| **OpenStrike** | [pocket-stack/open-strike](https://github.com/pocket-stack/open-strike) | PSP EBOOT、Vita VPK、桌面、Nokia E7 | CS 味单人 FPS：经典 BSP 图、bots、Solid JSX HUD，PSP 锁 60 fps | **能**：PPSSPP 跑 EBOOT。地图是 Valve 版权，仓库不带，要自己提供 GoldSrc `.bsp`/`.wad` 再 cook |
| **Pocket Voxel** | [pocket-stack/pocket-voxel](https://github.com/pocket-stack/pocket-voxel) · [pocketvoxel.games](https://pocketvoxel.games/) | 浏览器、PSP ZIP、Vita VPK | 把美版宝可梦红做成体素 3D 沙盘 | **能**：浏览器先烤 PSP 包，再丢 PPSSPP。必须自备合法美版 Red ROM，仓库不带任何 ROM 数据 |
| **PSPMAN** | [ObsoleteSony](https://www.obsoletesony.com/pspman/)（源码未公开） | PSP `/PSP/GAME/` | Walkman 风本地 FLAC/MP3 播放器，卡带机界面、频谱 | **能**：唯一有现成 alpha 包。放到 PPSSPP 记忆棒 + `Roms/PSP` 入口 |
| **Pocket Figma** | [pocket-stack/pocket-figma](https://github.com/pocket-stack/pocket-figma) | PSP EBOOT、Vita VPK | 用摇杆平移/缩放已烘焙的 Figma 社区文件（不是在线编辑器） | **能**：EBOOT 自包含（tiles 已提交），官方明确 PPSSPP 可直接跑 |
| **Pocket YouTube** | [pocket-stack/pocket-youtube](https://github.com/pocket-stack/pocket-youtube) | 3DS / PSP / Vita | 掌机搜/播 YouTube | **基本不能**：网络在 Mac 伴侣进程（yt-dlp + H.264）。PSP 走 USB `usbhostfs`，3DS/Vita 走局域网。CrossMix 没有这套管线 |
| **Pocket Map** | [pocket-stack/pocket-map](https://github.com/pocket-stack/pocket-map) | 3DS（主）、PSP USB | OSM / 海拉尔地图，Mac 供瓦片和搜索 | **不能实用**：同样依赖 Mac 伴侣；CrossMix 无 3DS 模拟器 |
| **Pocket Doc** | [pocket-stack/pocket-doc](https://github.com/pocket-stack/pocket-doc) | 3DS 双屏 | 上屏读 Markdown，下屏编辑 | **不能**：无 3DS 模拟器，且要 Mac 配对 |
| **Pocket Shell** | [pocket-stack/pocket-shell](https://github.com/pocket-stack/pocket-shell) | 3DS 平铺桌面；另有 iPod / Linux·macOS 桌面壳 | 3DS 上屏窗口、下屏工作区 | **不能当掌机 App**：3DS 版无模拟器；desktop 壳是 PC 桌面 WM，不是 TrimUI framebuffer 程序 |
| **Pocket Term** | [pocket-stack/pocket-term](https://github.com/pocket-stack/pocket-term) | 3DS + Mac | 上屏 Mac shell，下屏触摸键盘 | **不能** |
| **Pocket Character** | [pocket-stack/pocket-character](https://github.com/pocket-stack/pocket-character) | macOS 置顶窗口 | 透明 VRM 桌宠 | **不能**：桌面 widget |
| **Pocket DevTools** | 引擎内置，见 [博客](https://pocketjs.dev/blog/time-travel-devtools/) | USB 调试 | 按帧时间旅行调试 | 开发工具，不是给玩家的 ROM |
| **Pocket Launcher** | [pocketjs `apps/launcher`](https://github.com/pocket-stack/pocketjs/tree/main/apps/launcher) · [LAUNCHER.md](https://github.com/pocket-stack/pocketjs/blob/main/docs/LAUNCHER.md) | PSP / Vita | 多应用生命周期、guest 切换 | 运行时组件，单独当游戏没意义 |

### 1.2 同组织其它示例 / 实验

| 应用 | 仓库 | 说明 | CrossMix |
| --- | --- | --- | --- |
| **Pocket Pi** | [pocket-pi](https://github.com/pocket-stack/pocket-pi) | 嵌入式 Agent 运行时，现跑 Waveshare ESP32-P4/S3 | 不是掌机游戏 |
| **Pocket Openworld** | [pocket-openworld](https://github.com/pocket-stack/pocket-openworld) | Pocket3D 开放世界 POC（桌面 `cargo run`） | 无 PSP/Vita 包 |
| **Pocket Island** | [pocket-island](https://github.com/pocket-stack/pocket-island) | 3DS 社交小岛 + 原生 3DS runtime | 无 3DS 模拟器 |
| **Pocket Vault** | [pocket-vault](https://github.com/pocket-stack/pocket-vault) | 3DS 上的 Obsidian 风笔记，索引在 Mac | 不能 |
| **Pocket Studio** | [pocket-studio](https://github.com/pocket-stack/pocket-studio) | 桌面端生态桥 | 开发机工具 |
| **Pocket Desktop** | 已并入 `pocket-shell/shells/desktop` | Linux/macOS 主题桌面 | PC 用 |
| 引擎 demos | [pocketjs/apps/](https://github.com/pocket-stack/pocketjs/tree/main/apps) | `hero`、`gallery`、`motions`、`cafe`、`cards`、`music`、`note`、`zoomlab` 等验收/演示 | 可用 `bun play psp <name>` 打成 EBOOT，再按下面 PSP 流程放 |

官网 playground：<https://pocketjs.dev/playground/>（电脑浏览器即可，不进 CrossMix）。

---

## 2. 在 CrossMix 上怎么跑

### 2.1 平台对得上什么

| CrossMix 能力 | 路径 | 对 PocketJS 的含义 |
| --- | --- | --- |
| **PSP = PPSSPP 1.17.1 / 1.15.4** | `Emus/PSP/`，ROM 目录 `Roms/PSP` | **主路径**。PPSSPP 原生吃 `.iso` / `.cso` / `.pbp` / 目录里的 `EBOOT.PBP` |
| PSP Minis | `Roms/PSPMINIS` | 不必用，正式 PSP 区即可 |
| Apps | `Apps/<Name>/{config.json,launch.sh,icon.png}` | 只适合包一层「打开某个 .pbp」；没有 Linux ARM 的 PocketJS host，不能把 JS 应用原生编进 Apps |
| PORTS / PortMaster | `Roms/PORTS/*.sh` | 给 PC 移植用，不是 PocketJS |
| NDS | `Emus/NDS` | 不是 3DS |
| 3DS | `Emus/3DS` | Azahar / Lime3DS 启动器，需自备 `Emus/3DS/bin/azahar`。TSP 只能碰很轻的 3DS |
| Vita | 无 | 没有 Vita3K |
| 浏览器 App | 无 | Voxel 网页版只能在电脑上玩 |

PocketJS 官方支持的 OS（PSP / Vita / 老 iOS / Symbian / WinCE / BB10 / e-ink / ESP-IDF / wasm）里，**没有 TrimUI / Allwinner A133 这条 Linux framebuffer host**。所以「封装成 Apps 原生跑」目前做不到。

### 2.2 为什么不要做成 PSP ISO

用户直觉是「PSP 游戏 = ISO」。那是 UMD 商业碟的格式。

PocketJS 官方产物是：

- PSP：`EBOOT.PBP`（再加旁边的 `maps/`、`voxelmon.vxpak` 等）
- 安装布局：`ms0:/PSP/GAME/<App>/EBOOT.PBP`
- 官方验收就在 **PPSSPP** 上跑这份 EBOOT（OpenStrike、Pocket Figma 都写了）

转 ISO 的问题：

1. 需要 popstation 一类 UMD 封装，homebrew 经常找不到相对路径（`maps/` 就在 EBOOT 旁边）。
2. 丢掉 XMB 图标 / PIC1。
3. 官方 GitHub **没有**预编译 ISO，也几乎没有 Release 资产（PSPMAN 除外）。
4. PPSSPP 打开 `.pbp` 和打开 `.iso` 一样进游戏列表。

**正确投放：`Roms/PSP/<名字>.pbp`，或 `Roms/PSP/<名字>/EBOOT.PBP`。**

### 2.3 推荐目录（SD 卡 / 本仓库）

自包含 EBOOT（Figma、大部分 `apps/` demo）：

```text
Roms/PSP/PocketFigma.pbp
Roms/PSP/PocketHero.pbp
Imgs/PSP/PocketFigma.png          # 可选封面，文件名与 ROM 一致
```

带附属文件（OpenStrike 地图、Voxel pak、PSPMAN 资源）：

```text
Roms/PSP/OpenStrike/EBOOT.PBP
Roms/PSP/OpenStrike/maps/*.p3d

Roms/PSP/PocketVoxel/EBOOT.PBP
Roms/PSP/PocketVoxel/voxelmon.vxpak

Roms/PSP/PSPMAN/EBOOT.PBP         # 解压官方 ZIP 后的整个文件夹
```

`Emus/PSP/config.json` **没有 `extlist`**，`Roms/PSP` 里的每个文件都会出现在列表。附属数据务必放进子目录，不要把 `.p3d` / `.vxpak` 摊在 `Roms/PSP/` 根下。

PSPMAN 扫歌看的是 PPSSPP 记忆棒，不是 `Roms/`：

```text
Emus/PSP/PPSSPP_1.17.1/.config/ppsspp/PSP/MUSIC/
# 或
Emus/PSP/PPSSPP_1.17.1/.config/ppsspp/PSP/../../  对应 ms0:/MUSIC/
```

更稳的做法：把官方 `PSPMAN` 文件夹同时拷到记忆棒游戏目录：

```text
Emus/PSP/PPSSPP_1.17.1/.config/ppsspp/PSP/GAME/PSPMAN/EBOOT.PBP
```

然后在 `Roms/PSP` 放一份同名 `.pbp`（或文件夹）给 MainUI 点。音乐放到该记忆棒的 `MUSIC/` 或 `PSP/MUSIC/`。

启动：主界面 → **PSP** → 选对应条目 → 用 **PPSSPP 1.17.1 Vulkan（性能）** 或 OpenGL。PocketJS homebrew 是原生 GE/sceGu，PPSSPP 软件渲染也能过官方 golden，Vulkan 通常更流畅。

### 2.4 若坚持封装成 Apps

只是给某个已放好的 `.pbp` 做快捷方式，例如 `Apps/OpenStrike/`：

```sh
# launch.sh 示意（设备上路径）
HOME=/mnt/SDCARD/Emus/PSP/PPSSPP_1.17.1
cd "$HOME"
./PPSSPPSDL_vulkan /mnt/SDCARD/Roms/PSP/OpenStrike/EBOOT.PBP
```

再配 `config.json` + `icon.png`。功能上和 ROM 列表点一下相同，多一个 Apps 图标而已。没有独立原生程序可编。

---

## 3. 各应用怎么得到能跑的包

GitHub Releases 目前是空的（OpenStrike / Voxel / Figma 都没有现成 EBOOT）。除了 PSPMAN，都要本机编，或走 Voxel 网页导出。

公共前提（PSP 交叉编译）：电脑上装 [Bun](https://bun.sh/) + Rust，然后：

```sh
npm i -g @pocketjs/cli
pocket doctor          # 看缺什么
pocket setup           # 拉齐 pinned 的 pspdev / rust-psp
```

工具链缓存在 `~/.cache/pocket-stack`（可用 `POCKET_STACK_CACHE_DIR`）。这是 **MIPS PSP SDK**，不是给 TrimUI 编 Linux ARM。

### OpenStrike

```sh
git clone --recursive https://github.com/pocket-stack/open-strike
cd open-strike
bun run setup && bun run bootstrap
# 自备 CS 地图：maps/*.bsp + support/*.wad
export OPENSTRIKE_MAPS=/path/to/cs-maps
bun scripts/psp.ts --package    # → dist/PSP/GAME/OpenStrike/
```

把 `dist/PSP/GAME/OpenStrike/` 整个拷到 `Roms/PSP/OpenStrike/`。  
操作：摇杆走，△/✕/□/○ 看，R 开火，L 跳，十字下换弹，SELECT 回菜单。

不能把 cook 好的 `.p3d` 或带图 SIS/EBOOT 公开发布（Valve 版权）。本仓库也不会代放地图。

### Pocket Voxel

电脑浏览器最快：

1. 打开 <https://pocketvoxel.games/>
2. 选择自己的 **美版 Pokémon Red** `.gb`
3. 浏览器本地解码，页面里就能玩
4. 导出 **PSP ZIP**，解压到 `Roms/PSP/PocketVoxel/`（需同时有 `EBOOT.PBP` 和 `voxelmon.vxpak`）

源码路线：`VOXELMON_ROM=... bun tools/voxel.ts import && cook && psp --release`。

### Pocket Figma

```sh
git clone --recursive https://github.com/pocket-stack/pocket-figma
cd pocket-figma
bun run setup
bun run psp -- -r          # → dist/EBOOT.PBP
# 拷到 ms0:/PSP/GAME/PocketFigma/ 或 Roms/PSP/PocketFigma.pbp
```

摇杆/十字平移，L/R 缩放，△/□ 翻页，✕ 适配整页。

### PSPMAN（唯一现成包）

1. 从 [ObsoleteSony Releases](https://www.obsoletesony.com/pspman/releases/) 下 Public Alpha（当前 0.1.0-alpha.5）
2. 解压，确认 `PSPMAN/EBOOT.PBP`
3. 整夹放到 `Roms/PSP/PSPMAN/`
4. 音乐放到 PPSSPP 记忆棒 `MUSIC/` 或 `PSP/MUSIC/`（立体声 16-bit/44.1 kHz FLAC，或 44.1 kHz MP3）

源码不公开，无法从 pocket-stack 复现。

### 引擎自带 demo

```sh
git clone https://github.com/pocket-stack/pocketjs
cd pocketjs && bun install
pocket setup
bun play psp hero          # 或 gallery / motions / cafe ...
```

产物同样是 EBOOT，按 2.3 放入 `Roms/PSP`。

### 3DS / Mac 伴侣系（YouTube、Map、Doc、Term、Vault、Island、Shell-3DS）

CrossMix 只有 `Emus/3DS` 启动器（需自备 Azahar），也没有官方 Mac companion 可接到 TrimUI。这些请在 **New 3DS + Homebrew Launcher + 同网 Mac** 上按各仓库 README 部署。不要放进本仓库的 `Roms/`。

---

## 4. 建议落地顺序

1. **PSPMAN（已完成）**：官方 alpha.5 已放入 `Roms/PSP/PSPMAN/` 和 `Apps/PSPMAN`。
2. **Pocket Figma**：在 **Linux / macOS / WSL** 上 `bun run setup && bun run bootstrap && bun run psp -- -r`，把 `dist/EBOOT.PBP` 存成 `Roms/PSP/PocketFigma.pbp`。Windows 本机缺 clang/llvm-ar，且工具链 PATH 按 `:` 拼接，本轮未编出。
3. **引擎 hero/gallery**：同一套 PSP 工具链。
4. **Pocket Voxel**：自备美版红卡，[网页导出](https://pocketvoxel.games/) PSP ZIP → `Roms/PSP/PocketVoxel/`。
5. **OpenStrike**：自备 CS 地图再编。
6. 不要为 YouTube/Map/Doc 做 Apps 空壳——启动后只会停在 “CONNECT USB / 等 Mac”。

本机已浅克隆源码到仓库外的 `D:\game\pocket-stack\pocket-figma`（含 `vendor/pocketjs`），方便以后在 WSL 里继续编。不要把整个 `rust-lang/rust` 子模块拉下来。
