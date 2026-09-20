AppStore for CrossMix-OS
========================

用 git 只同步仓库里的一部分（Apps、Emus，或其中某一个应用），
不必把整个 CrossMix-OS 克隆到掌机上。

Git 怎么做到只拉部分文件
------------------------
  git clone --filter=blob:none --sparse --depth=1 <仓库>
  git sparse-checkout set Apps
  git sparse-checkout set Emus/PSP Apps/VLC

商店在本机有 git 时走上面这条路；TrimUI 固件通常没有 git，
这时改用 GitHub / Gitee / GitLab 的接口，效果一样：只下载选中的目录。

默认仓库
--------
  https://github.com/cizia64/CrossMix-OS.git   分支 main
  默认稀疏路径：Apps 、 Emus（一般只同步这两项）

自己的 fork / 本仓库改过的应用
------------------------------
  1. 把改过的 Apps、Emus 推到 GitHub / Gitee / GitLab
  2. 商店 → 仓库管理 → 添加仓库（贴 git 地址）
  3. 浏览那个仓库，按目录安装或更新

操作
----
  打开商店先看到 Apps、Emus 的名字和图标
  A 同步当前选中项     → 进入看里面的单个应用/模拟器
  Y 同步               X 卸载
  B 返回               MENU 退出
  仓库管理里按 N 可填 Token（GitHub 匿名接口有次数上限）

命令行（SSH / TermView）
------------------------
  python3 Apps/AppStore/sync.py sources
  python3 Apps/AppStore/sync.py list crossmix Apps
  python3 Apps/AppStore/sync.py install crossmix Apps/VLC
  python3 Apps/AppStore/sync.py install crossmix Emus
  python3 Apps/AppStore/sync.py update

数据写在 Apps/AppStore/data/（已安装清单、自加仓库、git 缓存）。
安装时覆盖包内文件，不会先清空整个目录，本地多出来的文件会留着。

环境变量
--------
  APPSTORE_ROOT   安装根目录，默认 /mnt/SDCARD
  APPSTORE_TOKEN  全局 Token
  APPSTORE_GIT    git 可执行文件路径
