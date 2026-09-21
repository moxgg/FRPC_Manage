# FRPC 管理工具（FrpcManager）

一个**单文件、零复杂依赖**的 FRP 客户端图形化管理工具：负责 frpc 的启动/停止/重启、健康检测自动自愈、开机自启与每日定时、PushPlus 外部通知、日志留存，以及最小化到系统托盘的后台运行。

| 项目 | 说明 |
|---|---|
| 当前版本 | v1.1.0 |
| 主程序 | `frpc_manager.py`（单文件，标准库 tkinter 实现） |
| 已构建产物 | `dist/FrpcManager.exe`（单文件、无控制台、约 21 MB） |
| 支持平台 | Windows 优先（注册表自启、托盘）；Linux/macOS 可运行，自启与托盘相关功能受限 |
| Python 要求 | 3.7 及以上 |

---

## 目录

- [1. 功能一览](#1-功能一览)
- [2. 目录结构](#2-目录结构)
- [3. 快速开始](#3-快速开始)
- [4. 界面与使用方法](#4-界面与使用方法)
- [5. 配置项详解](#5-配置项详解)
- [6. 健康检测详解](#6-健康检测详解)
- [7. 外部通知（PushPlus）](#7-外部通知pushplus)
- [8. 最小化与托盘后台运行](#8-最小化与托盘后台运行)
- [9. 开机自启与每日定时](#9-开机自启与每日定时)
- [10. 日志](#10-日志)
- [11. 构建方法](#11-构建方法)
- [12. 常见问题 FAQ](#12-常见问题-faq)
- [13. 依赖说明](#13-依赖说明)

---

## 1. 功能一览

| 功能 | 说明 |
|---|---|
| 可执行文件选择 | 文件选择框选取 frpc.exe，可一键"测试"验证；支持 `-c` 指定配置文件 |
| 进程管理 | 启动 / 停止 / 重启，实时显示运行状态、PID、运行时长、重启次数 |
| 崩溃自愈 | 勾选"进程意外退出时自动重启"后，frpc 崩溃会自动拉起 |
| 健康检测 | 定时请求指定 URL；超时 / 连接失败 / 状态码不符 → 自动重启 frpc |
| 请求方法 | 支持 GET / POST / HEAD；POST 收到 405 会**自动改用 GET 重试**，避免误重启 |
| 请求认证 | Basic（用户名:密码）、Bearer Token、自定义请求头；URL 内嵌 `user:pass@host` 亦可 |
| 开机自启 | 一键写入/清除注册表 `HKEY_CURRENT_USER\...\CurrentVersion\Run` |
| 每日定时 | 指定 HH:MM 自动启动 frpc；支持检测间隔周期设置 |
| 程序启动自运行 | 打开程序即自动启动 frpc |
| 外部通知 | 通过 **PushPlus（推送加）** 推送启动/停止/重启/检测失败/异常退出/每日启动事件，带冷却防刷屏 |
| 日志 | 分级彩色显示 frpc 输出与程序日志，可落盘、清空、打开日志目录 |
| 配置持久化 | 所有设置写入 `config.json`，下次启动自动加载 |
| 最小化运行 | 关闭窗口最小化到系统托盘，后台继续检测；双击托盘图标唤出界面 |

所有耗时操作（健康检测、日志采集、通知推送、定时调度）都在**后台线程**执行，通过队列 + `root.after` 与界面通信，绝不卡界面。

---

## 2. 目录结构

```
pyfrpc/
├── frpc_manager.py       # 主程序（单文件，全部功能实现在这里）
├── build_exe.py          # 一键打包脚本（调用 PyInstaller）
├── icon.ico              # 应用图标（蓝底 "F"，由 PIL 生成）
├── FrpcManager.spec      # PyInstaller 打包配置（自动生成，可手工微调）
├── README.md             # 本文档
├── dist/                 # 构建产物目录
│   └── FrpcManager.exe   # 打包好的单文件可执行程序
├── build/                # 构建中间产物（可删除）
└── .tools/               # 构建用 Python 环境（本机专用于打包，可删除）
    └── Python312/        #   Python 3.12.8（含 tkinter/TclTk）
```

> `.tools/` 只是本机为了打包而静默安装的 Python 环境，**运行时不需要它**；如果你已有带 tkinter 的 Python，可直接删除该目录。

---

## 3. 快速开始

### 方式 A：直接用打包好的 exe（推荐，无需装 Python）

1. 双击 `dist/FrpcManager.exe`（无任何控制台窗口）。
2. 在「基础配置」中点击**浏览**选择你的 `frpc.exe`。
3. 若 frpc 需要 `-c` 指定配置文件，填写「配置文件(-c)」。
4. 填写「检测 URL」，并在右侧把请求方法改成你的接口支持的方法（多数静态探测页面选 **GET**）。
5. 点击「启动 frpc」，观察「运行状态」与「运行日志」。
6. 按需配置通知、托盘、开机自启，最后点「保存配置」。

### 方式 B：用源码运行

```bash
# 安装可选依赖（推荐，非必需）
pip install requests          # HTTP 请求，缺失时自动回退标准库 urllib
pip install pystray pillow    # 系统托盘，缺失时降级为任务栏最小化

# 运行
python frpc_manager.py

# Windows 下无控制台后台运行
pythonw frpc_manager.py
```

Linux 发行版若提示缺少 tkinter，先装系统包：`sudo apt-get install python3-tk`。

---

## 4. 界面与使用方法

```
┌──────────────────────────────────────────────────────────────┐
│  F  FRPC 管理工具                      2026-09-21 16:00  ● 运行中 │  ← 顶栏：logo / 时钟 / 状态胶囊
├───────────────────┬──────────────────────────────────────────┤
│ ▶ 启动 frpc        │ 基础配置                                  │
│ ■ 停止  ⟳ 重启     │   frpc 程序   [路径............] [浏览]    │
│ 立即检测 保存配置  │   配置文件    [路径............] [浏览]    │
│ ⇱ 最小化到托盘     │   检测 URL    [URL.............] [GET ▾]  │
│                   │   超时/间隔/状态码  ☑ 开启健康检测         │
│ 运行状态           │   POST 数据 / 请求认证                    │
│  状态/PID/时长     ├──────────────────────────────────────────┤
│  上次/下次检测     │ 外部通知（PushPlus）                       │
│                   │   Token / 渠道 / 模板 / 群组 / 冷却        │
│ 自启与计划         │   ☑ 推送事件（启动/停止/重启/失败/…）      │
│  ☑ 开机自启        ├──────────────────────────────────────────┤
│  ☑ 关闭最小化托盘  │ 运行日志（分级彩色，可落盘/清空/打开）     │
│  ☐ 启动时最小化    │                                          │
│  每日定时 08:00    │                                          │
└───────────────────┴──────────────────────────────────────────┘
```

- **左栏**：运行控制（启停重启、立即检测、保存配置、最小化到托盘）、运行状态（状态/PID/运行时长/重启次数/上次与下次检测）、自启与计划（开机自启、启动自运行、崩溃自启、退出停止、关闭最小化到托盘、启动时最小化、每日定时）。
- **右栏**：基础配置、外部通知、运行日志（自动滚动、保存到文件、清空、打开日志文件/目录）。
- **底栏**：配置文件路径、版本号、requests 是否可用、Python 版本。

首次使用只需三步：选 frpc 路径 → 填检测 URL 与方法 → 启动。其余功能默认即可工作。

---

## 5. 配置项详解

配置保存在 **Windows：`%APPDATA%\FrpcManager\config.json`**（Linux/macOS：`~/.config/FrpcManager/config.json`），关闭程序自动保存，也可点「保存配置」立即写入。

| 字段 | 默认值 | 说明 |
|---|---|---|
| `frpc_path` | `""` | frpc 可执行文件路径 |
| `frpc_conf` | `""` | frpc 配置文件路径（等价于 `-c` 参数，可留空） |
| `health_url` | `""` | 健康检测地址 |
| `http_method` | `"POST"` | 检测方法：`GET` / `POST` / `HEAD` |
| `health_timeout` | `5` | 单次请求超时（秒，最小 1） |
| `health_interval` | `60` | 检测间隔（秒，最小 5） |
| `expect_code` | `200` | 期望 HTTP 状态码 |
| `post_data` | `""` | POST 请求体（仅 POST 发送；填 JSON 自动加 `Content-Type: application/json`） |
| `auth_type` | `"none"` | 认证方式：`none` / `basic` / `bearer` / `header` |
| `auth_value` | `""` | 认证内容（basic 填 `用户名:密码`；bearer 填 Token；header 填 JSON 或每行 `Name: value`） |
| `health_enabled` | `true` | 是否开启健康检测 |
| `crash_restart` | `true` | frpc 意外退出时自动重启 |
| `start_on_launch` | `false` | 本程序启动时自动运行 frpc |
| `daily_enabled` / `daily_time` | `false` / `"08:00"` | 每日定时启动与时间 |
| `log_to_file` / `log_path` | `true` / `""` | 是否落盘及日志路径（留空用默认） |
| `auto_scroll` | `true` | 日志自动滚动 |
| `stop_on_exit` | `true` | 退出程序时一并停止 frpc |
| `autostart` | `false` | 开机自启（写入注册表） |
| `minimize_to_tray` | `true` | 关闭窗口时最小化到托盘而非退出 |
| `start_minimized` | `false` | 启动时直接最小化到托盘 |
| `notify_enabled` | `false` | 是否启用 PushPlus 通知 |
| `push_token` | `""` | PushPlus Token |
| `push_channel` | `"wechat"` | 渠道：wechat/app/cp/webhook/mail |
| `push_template` | `"txt"` | 模板：txt/html/json/markdown |
| `push_topic` | `""` | 群组编码（留空只发给自己） |
| `notify_cooldown` | `60` | 同一事件推送冷却秒数（防刷屏） |
| `notify_events` | 见下 | 事件开关：start=True、stop=False、restart=True、fail=True、crash=True、daily=False |

---

## 6. 健康检测详解

**检测逻辑**：每隔 `health_interval` 秒向 `health_url` 发一次请求（方法由 `http_method` 决定）。满足以下任一情况判定为异常并**自动重启 frpc**：

- 请求超时（超过 `health_timeout` 秒）
- 连接失败（拒绝连接、DNS 失败等）
- 返回状态码 ≠ `expect_code`

**关于 405（最常见的坑）**：不少探测接口（如 IIS 静态页面）**只接受 GET**，用 POST 会返回 `405 Method Not Allowed`。程序内置兜底：**POST 收到 405 时自动改用 GET 重试一次**，成功即判正常，并在日志提示把方法改成 GET。建议直接在界面把方法选为 **GET**。

> 判别技巧：在 PowerShell 里 `curl` 实际是 `Invoke-WebRequest` 的别名，默认发 **GET**，所以它显示 200 而程序用 POST 显示 405。可用 `curl.exe -X POST <url>`（真正的 curl）或 `Invoke-WebRequest -Method POST <url>` 对比验证。

**携带账号密码**（三种方式，任选）：

| 方式 | 填法 | 实际效果 |
|---|---|---|
| Basic 认证 | 认证方式选 `basic`，认证信息填 `admin:密码` | `Authorization: Basic <base64>` |
| Bearer | 认证方式选 `bearer`，填 Token | `Authorization: Bearer <token>` |
| 自定义头 | 认证方式选 `header`，填 `{"X-Token":"abc"}` 或每行 `X-Token: abc` | 附加任意请求头 |
| URL 内嵌 | 直接写 `http://user:密码@host/path` | requests/urllib 原生支持 |

**安全**：日志对 URL 中的账号密码自动脱敏，显示为 `http://admin:***@host/path`；认证框默认打码，可勾"显示"查看。

---

## 7. 外部通知（PushPlus）

1. 到 <https://www.pushplus.plus> 登录并复制你的 **Token**。
2. 界面「外部通知」区勾选"启用外部通知推送"，粘贴 Token，选择渠道/模板（默认 wechat + txt），需要发给群组时填群组编码。
3. 勾选要推送的事件：**启动 / 停止 / 重启 / 检测失败 / 异常退出 / 每日定时启动**。
4. 点「发送测试推送」验证；推送结果以紫色 `PUSH` 级别写入日志。

- 接口：`POST https://www.pushplus.plus/send`（返回 `code=200` 即提交成功）。
- **冷却时间**（默认 60 秒）防止异常时反复推送刷屏；同一事件在冷却期内只推一次。
- 消息正文会自动附带主机名与时间。

---

## 8. 最小化与托盘后台运行

- 需要可选依赖：`pip install pystray pillow`（exe 中已内置）。
- **关闭窗口 = 最小化到托盘**（默认开启），后台的健康检测、每日定时、日志采集全部继续运行。
- **双击托盘图标**唤出主界面；右键菜单包含：显示主界面 / 启动 frpc / 停止 frpc / 重启 frpc / 退出程序，菜单顶部显示当前 frpc 状态。
- 也可点控制区的「⇱ 最小化到托盘后台运行」按钮随时收起。
- 命令行参数：`FrpcManager.exe --minimized` 启动即进入后台。
- 勾选「启动时最小化到托盘」后，**开机自启的注册表命令会自动追加 `--minimized`**，开机后静默驻留托盘、不弹窗口。
- 未安装 pystray/pillow 时自动降级：关闭窗口最小化到任务栏，日志会提示如何启用托盘。
- 真正退出请用托盘菜单的「退出程序」（若勾选了"退出程序时停止 frpc"，会先询问是否停掉 frpc）。

---

## 9. 开机自启与每日定时

- **开机自启**：勾选后写入 `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`，值名为 `FrpcManager`；取消勾选即删除。程序启动时会读回注册表真实状态并同步勾选框。
- 源码运行时自启命令形如：`"pythonw.exe" "D:\...\frpc_manager.py" [--minimized]`；打包后为 `"...\FrpcManager.exe" [--minimized]`（用 pythonw 避免弹出控制台）。
- **每日定时**：勾选并填写 `HH:MM`（如 `08:30`），每天到点自动启动 frpc（已在运行则跳过，按日期去重不会重复触发）。

---

## 10. 日志

- 界面按级别着色：INFO（灰）、FRPC（蓝，frpc 自身输出）、OK（绿）、WARN（橙）、ERROR（红）、PUSH（紫）。
- 勾选"保存到文件"后写入 **Windows：`%APPDATA%\FrpcManager\logs\frpc_manager.log`**（可在界面修改路径）。
- 支持自动滚动、清空界面日志、打开日志文件、打开日志目录。
- 界面日志超过 3000 行会自动裁剪，长时间运行不会膨胀。
- frpc 输出中的 ANSI 颜色转义符（如 `\x1b[0m`）会被自动清除，日志干净可读。

---

## 11. 构建方法

### 11.1 准备环境

需要一个**带 tkinter** 的 Python（Windows 官方安装包默认包含；用命令行静默安装时要显式带上 `Include_tcltk=1`，否则会缺少 Tcl/Tk）：

```powershell
# 示例：静默安装 Python 3.12.8 到指定目录
python-3.12.8-amd64.exe /quiet InstallAllUsers=0 TargetDir=D:\py312 Include_tcltk=1 Include_launcher=0
```

安装构建依赖：

```bash
pip install pyinstaller          # 必需，用于打包
pip install requests             # 可选，打进 exe 后 HTTP 能力更完整（缺失时程序回退 urllib）
pip install pystray pillow       # 可选，打进 exe 后支持系统托盘
```

### 11.2 打包命令

```bash
pyinstaller -F -w -n FrpcManager --clean -y --icon icon.ico frpc_manager.py
```

- `-F` 单文件；`-w` 无控制台窗口；`--icon` 指定图标；`--clean` 清理缓存。
- 也可直接运行封装好的脚本：

```bash
python build_exe.py
```

产物：`dist/FrpcManager.exe`（单文件，约 21 MB，含 requests + pystray + pillow）。

### 11.3 减小体积（可选）

不需要托盘或 requests 时，可在**未安装**这些包的干净环境里打包，程序仍可运行（HTTP 回退 urllib、托盘降级任务栏），体积可显著下降。也可用 `--exclude-module` 精确裁剪。

### 11.4 常见构建问题

| 现象 | 原因 / 解决 |
|---|---|
| `ModuleNotFoundError: No module named 'tkinter'` | 当前 Python 缺 Tcl/Tk；换官方安装包重装并确认 `Include_tcltk=1` |
| 覆盖旧 exe 时报删除/回收站错误 | 先手动删除 `dist\FrpcManager.exe`（或改名）再打包 |
| exe 启动闪退 | 临时去掉 `-w` 重新打包，用控制台版查看报错 |
| 杀毒软件误报 | PyInstaller 单文件 exe 常见误报，加入白名单即可 |
| 想更新图标 | 替换 `icon.ico` 后重新打包（脚本会自动带上 `--icon`） |

### 11.5 构建后验证

```bash
FrpcManager.exe              # 正常显示主界面
FrpcManager.exe --minimized  # 无主窗口、托盘出现图标、进程保持运行
```

---

## 12. 常见问题 FAQ

**Q：curl 访问返回 200，程序却报 405 并一直重启？**
A：curl/PowerShell 的 `curl` 默认发 GET，程序默认发 POST，而你的接口不接受 POST。把「检测 URL」右侧方法改成 **GET** 即可（新版本也会自动用 GET 重试）。

**Q：日志里出现 `[0m`、`[31m` 之类乱码？**
A：这是 frpc 输出的 ANSI 颜色转义符，新版本已自动清除；如仍出现请确认使用的是最新 exe。

**Q：关掉窗口后程序没退出？**
A：这是设计行为——默认最小化到托盘后台继续检测。要退出请用托盘右键菜单「退出程序」；想恢复成"关闭即退出"，取消勾选「关闭窗口时最小化到托盘」。

**Q：收不到推送？**
A：依次检查：① 勾选了"启用外部通知推送"；② Token 正确（用"发送测试推送"验证）；③ 对应事件已勾选；④ 冷却时间未到；⑤ 日志中 `PUSH` 行的返回信息。

**Q：开机自启没生效？**
A：确认以当前用户身份勾选成功（写的是 HKCU，不需要管理员权限）；若移动过 exe/源码位置，需重新勾选一次以刷新注册表里的路径。

**Q：配置或日志在哪？**
A：配置 `%APPDATA%\FrpcManager\config.json`；日志 `%APPDATA%\FrpcManager\logs\frpc_manager.log`（界面底栏会显示实际路径）。

**Q：frpc 明明启动了，检测却一直失败？**
A：检测 URL 应填**穿透后能访问的业务地址**（通过 frps 暴露的域名/端口），不是 frps 的控制端口；先用浏览器或 curl 确认该地址可达，再回填到程序。

**Q：能同时管理多个 frpc 实例吗？**
A：当前版本是单实例管理；需要多实例可复制多份程序并各自使用独立配置目录运行。

---

## 13. 依赖说明

| 依赖 | 是否必需 | 用途 | 缺失时的行为 |
|---|---|---|---|
| Python 3.7+（含 tkinter） | **必需** | GUI 与运行时 | 无法运行 |
| `requests` | 可选 | 健康检测与通知推送的 HTTP 请求 | 自动回退标准库 `urllib`，功能不受影响 |
| `pystray` + `pillow` | 可选 | 系统托盘后台运行 | 降级为最小化到任务栏，其余功能正常 |
| `pyinstaller` | 仅构建时需要 | 打包 exe | 不影响源码运行 |

程序遵循"**能不装就不装**"的原则：只装标准库也能完整运行核心能力，可选依赖只会增强体验。
