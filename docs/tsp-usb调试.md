# TrimUI Smart Pro：USB 有线连电脑调试

CrossMix-OS 跑在 TrimUI Smart Pro（TSP）上。机子是 **Tina Linux（OpenWrt 系）**，不是 Android，但固件自带 `adbd`，所以 USB 有线调试走的是 **ADB**，不是串口，也不是「插上就变成 U 盘」。

结论先说：

| 你想做什么 | 用哪条路 | 机子还能不能玩 / 跑 App |
|---|---|---|
| **有线进 shell、看进程、推文件、调 App** | 底部 USB-C + ADB | **能**，MainUI / App 继续跑 |
| 日常改脚本、看日志、SFTP | WiFi + SSH（`root` / `tina`） | 能 |
| 把整张 SD 卡当 U 盘拷大文件 | Apps → **USB Storage** | **不能**，会卸掉 SD、杀进程，退出后重启 |
| 大批量拷 ROM | **拔卡 + 读卡器**（最稳） | 关机再拔 |

**调试 App 不要开 USB Storage。** 那个模式会 `umount /mnt/SDCARD`、杀掉 MainUI，退出还要重启。CrossMix 的实现在 `System/resources/usb_storage/launch.sh`，最后调用的是 `/bin/setusbconfig mass_storage,adb`。

---

## 1. 硬件：口、线、电脑

TSP 有两个 USB-C，用途不一样（linux-sunxi 记的是 1 个 USB2.0 Host + 1 个 USB2.0 OTG）：

| 口 | 位置 | 角色 | 连电脑？ |
|---|---|---|---|
| **OTG / 充电口** | **机身底部**，充电也是这个 | 当 USB 设备（gadget）：ADB、U 盘 | **要连这个** |
| Host 口 | 机身顶部 | 插手柄、U 盘、读卡器 | 不要拿来连 PC |

线必须是 **能传数据** 的 USB-C ↔ USB-A，或 USB-C ↔ USB-C。充电专用线、部分劣质 C-to-C 只会充电，Windows 完全看不到设备。包装里那根不一定能传数据，不行就换一根确认过的。

电脑这边（你现在是 Windows）：

- 机子要 **开机**，进到 CrossMix 主界面再插线
- 先不要开 USB Storage
- 插上后 Windows 可能会响一声「发现设备」，但 **资源管理器不会多出一个盘**——这是正常的，默认是 ADB 复合设备，不是大容量存储

---

## 2. 有线调试主路径：ADB

### 2.1 电脑安装 platform-tools

任选一种：

```powershell
winget install --id Google.PlatformTools
```

或手动下 [Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools)，解压后把目录加进 PATH。确认：

```powershell
adb version
```

### 2.2 Windows 驱动

插上底部 USB-C 后，打开 **设备管理器**：

- 已经出现 **Android Composite ADB Interface** / **ADB Interface** → 驱动够了
- 出现 **未知设备**、**Android**、感叹号 → 要装 ADB 驱动

常用来源：

1. Google USB Driver（Android Studio SDK Manager 里的 `Google USB Driver`）
2. TrimUI 刷机包 PhoenixSuite 自带的 `PhoenixSuite/Drivers/`（社区给 Smart / Smart Pro 都用过）
3. [Universal ADB Driver](https://adb.clockworkmod.com/) 一类社区包

装完后对那个未知设备：**更新驱动程序 → 浏览计算机 → 选 Android ADB Interface**。不要装成 WinUSB 随便一个设备，否则 `adb devices` 永远是空的。

### 2.3 第一次连上

机子开着、主界面、底部口、数据线：

```powershell
adb kill-server
adb start-server
adb devices
```

正常会看到一台 `device`（不是 `unauthorized`）。TSP 的 ADB **没有授权弹窗**，不需要点「允许调试」。

```powershell
adb shell
```

进的是 **root shell**。常见挂载：

| 路径 | 是什么 |
|---|---|
| `/mnt/SDCARD` | CrossMix 整张 SD 卡（Apps、Emus、Roms、System） |
| `/usr/trimui` | 机身内置固件（MainUI、自带 App） |
| `/mnt/UDISK` | 机身 eMMC 用户区 |
| `/tmp` | tmpfs，重启就没 |

本仓库在电脑上的 `Apps/`、`System/`，对应机子上就是 `/mnt/SDCARD/Apps/`、`/mnt/SDCARD/System/`。

### 2.4 调 CrossMix App 时常用命令

在 **电脑 PowerShell**（不必先 `adb shell`）：

```powershell
# 推一个改过的脚本上去（例：TermView）
adb push "d:\game\CrossMix-OS\Apps\TermView\termview.py" /mnt/SDCARD/Apps/TermView/termview.py

# 拉日志 / 配置回来
adb pull /mnt/SDCARD/Apps/TermView/config.json .

# 在机子上跑一条命令
adb shell "ps | grep -i termview"
adb shell "ls -l /mnt/SDCARD/Apps/TermView"

# 看内核 / Tina 日志
adb shell dmesg
adb shell logread
```

进 shell 之后再调：

```sh
export PATH="/mnt/SDCARD/System/bin:/mnt/SDCARD/System/usr/trimui/scripts:$PATH"
export LD_LIBRARY_PATH="/mnt/SDCARD/System/lib:/usr/trimui/lib:${LD_LIBRARY_PATH:-}"

cd /mnt/SDCARD/Apps/TermView
ls -l
# 不要从 ADB 直接抢 framebuffer 去开带 SDL 的 App，会和 MainUI 抢屏幕闪屏。
# 机子上用手柄点 Apps 启动；电脑这边用 adb 看进程、日志、改文件。
```

从远程会话跑带画面的程序时，CrossMix wiki 的建议是先停掉主界面，否则抢显示：

```sh
killall -9 runtrimui.sh MainUI
```

只在你明确要「全屏接管」时才杀。普通改脚本、看 log，**别杀 MainUI**。

### 2.5 如果 `adb devices` 是空的

按这个顺序排：

1. 换线、换电脑口；确认插的是 **底部** USB-C
2. 设备管理器里有没有未知 USB；没驱动就 `adb` 看不见
3. `adb kill-server` 再 `adb start-server`（有时要管理员开终端）
4. 机子上开一次 WiFi SSH（见下一节），连上去执行：

```sh
/bin/setusbconfig adb
# 若 adbd 没在跑：
adbd &
```

5. 仍然没有 → 先走 WiFi SSH 调试，ADB 当加分项。不要为了「看见 U 盘」去开 USB Storage，那不是调试模式。

USB Storage 退出时会 `/bin/setusbconfig none` 再杀掉 `adbd` 然后 **重启**。所以用完 USB Storage 之后 ADB 会暂时没了，重启后才恢复固件默认状态。

---

## 3. WiFi SSH：日常调试（不是 USB，但最好用）

CrossMix 默认开 SSH（dropbear）。开机脚本会把 root 密码设成 `tina`（`System/starts/°customization.sh` 里的 `echo "root:tina" | chpasswd`），主机名是 `TSP`。

机子：

1. 打开 WiFi，连和电脑同一局域网
2. `System Tools` → `NETWORK` → `Display IP` 看地址
3. 若 SSH 被关了：`System Tools` → `NETWORK` → `SSH` → `SSH Server - enable`

电脑（PowerShell 自带 OpenSSH 客户端）：

```powershell
ssh root@TSP
# 解析不了 TSP 就用 IP：
ssh root@192.168.x.x
```

| 项 | 值 |
|---|---|
| 用户 | `root` |
| 密码 | `tina` |
| 端口 | `22` |
| 主机名 | `TSP` |

WinSCP / FileZilla 走 **SFTP、端口 22**，同一套账号，适合拖文件。SSH 登入时 CrossMix 会问要不要开 **dev profile**（`System/usr/trimui/scripts/ssh_profile.sh`）：选 Y 会自动带上 `/mnt/SDCARD/System/bin` 和对应 `LD_LIBRARY_PATH`，在远程跑 CrossMix 自带工具更省事。

同一套网络工具还可以开（都不是 USB）：

| 服务 | 入口 | 账号 |
|---|---|---|
| Telnet | System Tools → TELNET | `root` / `tina`，明文，不建议 |
| SFTPGo FTP | 端口 21 | `trimui` / `trimui` |
| SFTPGo 网页 | `http://TSP:8080` | `admin` / `admin` |
| SMB | `\\TSP` 或 `\\IP` | 无密码；安全模式 `root` / `trimui` |

**ADB 有线** 和 **SSH WiFi** 可以同时用：USB 改文件、SSH 看输出，或反过来。

---

## 4. USB Storage：只拷卡，不调程序

想把 SD 卡当 U 盘（不拔卡）时：

1. 底部 USB-C 接到电脑
2. 机子 Apps → **USB Storage**
3. 第一次会出说明图，按 **A** 继续（B 取消）
4. 脚本会杀掉占用 SD 的进程、卸载 `/mnt/SDCARD`，再 `setusbconfig mass_storage,adb`
5. Windows 这时才应该出现盘符
6. 拷完后：**先在 Windows 托盘安全弹出**，再在机子上按说明退出（一般是 B）。退出会重启

注意：

- 社区反馈这条路 **不稳定**，大容量 FAT32 卡 Windows 会反复「扫描并修复」，也有人卡在「按 B 退出」。卡住就 **长按电源** 强制关机
- 有人遇到过拷文件导致卡损坏。大文件、日常同步优先 **读卡器** 或 **SFTP**
- 这个模式下 SD 已经卸掉，**不能**在机子上跑你刚拷上去的 App

---

## 5. 推荐工作流（改本仓库里的 App）

以改 `Apps/TermView`、`Apps/VLC` 这类 CrossMix App 为例：

1. 电脑上改文件（这个 Git 仓库）
2. **小改动**：`adb push` 对应路径到 `/mnt/SDCARD/...`，或 WinSCP 拖过去  
   **大改动 / 很多文件**：关机，拔卡，读卡器拷
3. 机子上从 Apps 再进一次（或杀进程后重新点图标）
4. 电脑 `adb shell` / `ssh`：`ps`、`logread`、看 `/tmp` 下的输出
5. 需要全屏独占时再 `killall -9 runtrimui.sh MainUI`，测完重启最干净

路径对照：

```text
电脑:  d:\game\CrossMix-OS\Apps\TermView\launch.sh
机子:  /mnt/SDCARD/Apps/TermView/launch.sh
```

---

## 6. 这台机器做不到 / 不要指望的

- **不是 Android Studio 那套 USB debugging。** 没有 apk、没有 logcat 缓冲（`adb logcat` 基本没用），`adb shell` 就是一台 Linux。
- **USB-C 不是 UART。** 真要 115200 串口得拆机焊板子上标了 RX/TX/GND 的焊盘，会失去保修。日常调试用不到。
- **没有现成的「USB 网卡 / RNDIS」App。** 不能指望插上 USB 就变成 `192.168.x.x` 再 SSH。要 SSH 走 WiFi；要有线 shell 走 ADB。
- **顶部 USB-C 连电脑没用**（那是 Host）。
- 插上 USB **不会自动出现 U 盘**。要盘符就开 USB Storage；要调试就用 ADB。

---

## 7. 故障对照

| 现象 | 多半是 |
|---|---|
| 插上没反应 | 充电线 / 插了顶部口 / 机子没开机 |
| Windows 叮一声但没有盘 | **正常**（ADB 模式）。去 `adb devices`，不要找盘符 |
| `adb devices` 空白 | 驱动、线、端口；设备管理器里的未知设备 |
| `unauthorized` | 少见。重启 `adb` 服务；TSP 通常不弹授权 |
| USB Storage 有盘但拷完卡坏 / Windows 一直修复 | 换读卡器或 SFTP；不要在拷的时候拔线 |
| USB Storage 按 B 退不出 | 长按电源重启 |
| SSH 连不上 | WiFi 没连上、SSH 被关、不在同一网段；用 Display IP，不要死记 `TSP` |
| ADB 能进，但 `/mnt/SDCARD` 是空的或不存在 | 你开着 USB Storage，卡已经被卸掉了 |

---

## 8. 和仓库脚本的对应关系

| 行为 | 文件 |
|---|---|
| USB Storage 切 gadget、卸 SD、杀进程 | `System/resources/usb_storage/launch.sh` |
| 开机设 `root:tina`、hostname `TSP` | `System/starts/°customization.sh` |
| 开机按配置拉起 dropbear | `System/starts/ex_init.sh` |
| System Tools 开/关 SSH | `Apps/SystemTools/Menu/NETWORK##SSH (state)/` |
| SSH 登录时的 PATH / 库 | `System/usr/trimui/scripts/ssh_profile.sh` |
| 显示 IP | `Apps/SystemTools/Menu/NETWORK/Display IP.sh` |

官方 Wiki（网络服务、USB Storage 说明）：[CrossMix Apps](https://github.com/cizia64/CrossMix-OS/wiki/Apps)。
