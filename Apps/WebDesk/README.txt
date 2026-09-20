WebDesk for CrossMix-OS
=======================

打开这个 App 后，掌机会在局域网 80 端口起一个网页。
电脑或手机浏览器访问它，可以：

  - 看 IP / 内存 / 磁盘
  - 浏览、上传、下载、改名、删除、改文本
  - 开一个真正的 shell（xterm.js + PTY）

退出 App（B / MENU）后 HTTP 立刻关掉，网页不能再用。
没有打开这个 App 的时候，80 端口不会挂着管理页。

怎么用
------
1. 掌机开 WiFi，连和电脑 / 手机同一局域网
2. Apps 里打开 WebDesk
3. 屏幕上会显示地址和 6 位访问码，例如 http://192.168.1.23/
4. 浏览器打开这个地址，输入访问码
5. 用完按 B / MENU 退出。服务一起停

若 80 被别的程序占着，会自动改用 8088，屏幕上的地址会带端口。

和系统里已有服务的区别
----------------------
SFTPGo（System Tools → NETWORK）走 8080，是常驻服务。
WebDesk 是一个 App：只在你打开它的时候提供网页，退出就关。
SSH（root / tina）仍然可用，这个 App 不替代 SSH。

注意
----
网页终端是 root shell，文件管理也能动整张卡。
只在自己信任的 WiFi 上开，访问码不要发给不认识的人。
关掉 App 后旧标签页会断开。

依赖
----
CrossMix 自带的 Python 3.11，以及 Apps/Terminal（TermSP）。
不需要再装软件包。浏览器打开页面即可，电脑不用装客户端。

命令行（SSH 调试）
----------------
  python3 Apps/WebDesk/webdesk.py
  WEBDESK_PORT=8088 WEBDESK_PIN=123456 python3 Apps/WebDesk/webdesk.py
