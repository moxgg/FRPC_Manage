#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
==============================================================================
 FRPC 管理工具 (FrpcManager) —— 单文件版 / Python + tkinter + PushPlus 通知
==============================================================================

【一、依赖安装】
    必选：Python 3.7+（tkinter / subprocess / threading 均为标准库，无需 pip）
          * 部分 Linux 发行版需单独安装：sudo apt-get install python3-tk
    可选：requests（用于健康检测与通知推送；未安装时自动回退标准库 urllib）
          pip install requests
    可选：pystray + pillow（启用系统托盘后台运行；缺失则降级为最小化到任务栏）
          pip install pystray pillow

【二、运行方式】
    python frpc_manager.py
    Windows 下无控制台后台运行：pythonw frpc_manager.py

【三、打包（Windows exe）】
    pip install pyinstaller
    pyinstaller -F -w -n FrpcManager --clean frpc_manager.py
    产物：dist\FrpcManager.exe（-w 表示不显示控制台窗口）

【四、使用说明】
    1. 可执行文件：浏览选择 frpc.exe（Linux/Mac 选 frpc），点“测试”验证；
       若 frpc 需要 -c 指定配置文件，填写“配置文件”。
    2. 进程管理：启动 / 停止 / 重启；状态区实时显示运行状态、PID、运行时长、重启次数。
    3. 健康检测：填写检测 URL、请求方法（GET/POST/HEAD）、超时、间隔、期望状态码、POST 数据；
       接口只接受 GET 时请选 GET（用 POST 会得到 405）；若误用 POST，程序检测到 405 会
       自动改用 GET 重试一次，避免误重启（日志会提示把方法改成 GET）。
       需要账号密码时用“请求认证”：basic 填“用户名:密码”、bearer 填 Token、
       header 填 {"X-Token":"abc"}；也支持直接写在 URL 里 http://user:pass@host/path；
       日志对 URL 中的账号密码自动脱敏。
       请求超时 / 连接失败 / 状态码不符 => 自动重启 frpc。可点“立即检测”手工触发。
    4. 开机自启：写入注册表 HKEY_CURRENT_USER\...\CurrentVersion\Run（仅 Windows）。
    5. 每日定时：勾选并填写 HH:MM，每天到点自动启动 frpc。
    6. 外部通知（PushPlus 推送加 https://www.pushplus.plus）：
       填写 Token 后勾选需要推送的事件，程序会在 frpc 启动 / 停止 / 重启 /
       检测失败 / 异常退出 / 每日定时启动时向微信等渠道推送消息，
       可点“发送测试推送”验证；冷却时间用于防止异常时反复推送刷屏。
    7. 日志：实时显示 frpc 输出 + 程序日志；可保存到文件、清空、打开日志目录。
    8. 配置持久化：写入 config.json（Windows 默认 %APPDATA%\FrpcManager\config.json）。
    9. 最小化运行：点关闭按钮（或“最小化到托盘”）转入后台，托盘图标右键可
       显示主界面 / 启停重启 frpc / 退出；后台期间健康检测、定时、日志照常工作。
       勾选“启动时最小化到托盘”后，开机自启会自动带 --minimized 参数静默后台运行。

【五、代码结构】
    THEME       —— 界面配色 / 字体 / ttk 样式表（浅色扁平风）
    ConfigStore —— 配置读写（JSON 持久化）
    http_post_json —— 统一 JSON POST（requests 优先，缺失回退 urllib）
    App         —— GUI 组装（顶栏 / 左栏控制+状态+计划 / 右栏配置+通知+日志）
    后台线程（健康检测、每日定时、日志读取、通知推送）全部通过 queue + root.after
    与主线程通信，绝不阻塞界面。
==============================================================================
"""

import base64
import datetime
import json
import os
import platform
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

# ---------------------------------------------------------------------------
# 可选依赖：requests（缺失则自动回退 urllib）
# ---------------------------------------------------------------------------
try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None

        # ---- 可选依赖：pystray + Pillow（托盘后台运行；缺失则降级为最小化到任务栏）----
        #     pip install pystray pillow
try:
    import pystray                                  # type: ignore
    from pystray import MenuItem as _TrayItem, Menu as _TrayMenu
    from PIL import Image, ImageDraw, ImageFont     # type: ignore
except Exception:                                   # pragma: no cover
    pystray = None
    _TrayItem = _TrayMenu = None
    Image = ImageDraw = ImageFont = None

import urllib.error
import urllib.request

IS_WINDOWS = sys.platform.startswith("win")
if IS_WINDOWS:
    try:
        import winreg
    except Exception:  # pragma: no cover
        winreg = None

APP_NAME = "FrpcManager"
APP_VERSION = "1.1.0"
REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
PUSHPLUS_URL = "https://www.pushplus.plus/send"

# ===========================================================================
# 界面主题（浅色扁平风）
# ===========================================================================
class THEME:
    HEADER_BG = "#1f2a44"      # 顶栏深蓝
    HEADER_SUB = "#96a5c4"
    BODY_BG = "#f2f5fa"        # 主体背景
    CARD_BG = "#ffffff"        # 卡片背景
    BORDER = "#e2e8f2"
    TEXT = "#1f2a44"
    TEXT_SUB = "#6b7280"
    PRIMARY = "#2563eb"
    PRIMARY_D = "#1d4ed8"
    GREEN = "#16a34a"
    GREEN_D = "#15803d"
    RED = "#dc2626"
    RED_D = "#b91c1c"
    AMBER = "#f59e0b"
    AMBER_D = "#d97706"
    LOG_BG = "#fbfcfe"
    FONT = "Microsoft YaHei UI"
    MONO = "Consolas"


LEVEL_COLOR = {
    "INFO": "#4b5563",
    "FRPC": "#1d4ed8",     # frpc 自身输出
    "OK": "#15803d",
    "WARN": "#b45309",
    "ERROR": "#b91c1c",
    "PUSH": "#7c3aed",     # 通知推送相关
}

# 通知事件定义
EVENT_LABEL = {
    "start": "frpc 启动",
    "stop": "frpc 停止",
    "restart": "frpc 重启",
    "fail": "健康检测失败",
    "crash": "frpc 异常退出",
    "daily": "每日定时启动",
    "test": "测试推送",
}

CHANNELS = ["wechat", "app", "cp", "webhook", "mail", ""]
TEMPLATES = ["txt", "html", "json", "markdown"]
HTTP_METHODS = ["GET", "POST", "HEAD"]
# 健康检测请求的认证方式
AUTH_TYPES = ["none", "basic", "bearer", "header"]
# 去除 frpc 输出里的 ANSI 颜色转义符（如 \x1b[0m）
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


# ===========================================================================
# 配置存储
# ===========================================================================
class ConfigStore:
    """配置持久化：JSON 文件读写，缺失字段自动用默认值补齐。"""

    DEFAULTS = {
        "frpc_path": "",
        "frpc_conf": "",
        "health_url": "",
        "http_method": "POST",      # 检测请求方法：GET / POST / HEAD
        "health_timeout": 5,
        "health_interval": 60,
        "expect_code": 200,
        "post_data": "",
        # 检测请求认证：none / basic / bearer / header
        "auth_type": "none",
        "auth_value": "",
        "health_enabled": True,
        "crash_restart": True,
        "start_on_launch": False,
        "daily_enabled": False,
        "daily_time": "08:00",
        "log_to_file": True,
        "log_path": "",
        "auto_scroll": True,
        "stop_on_exit": True,
        "autostart": False,
        # ---- 最小化 / 托盘后台运行 ----
        "minimize_to_tray": True,      # 关闭窗口时最小化到托盘（而不是退出）
        "start_minimized": False,      # 启动时直接最小化到托盘
        # ---- PushPlus 通知 ----
        "notify_enabled": False,
        "push_token": "",
        "push_channel": "wechat",
        "push_template": "txt",
        "push_topic": "",
        "notify_cooldown": 60,
        "notify_events": {"start": True, "stop": False, "restart": True,
                          "fail": True, "crash": True, "daily": False},
    }

    def __init__(self, path):
        self.path = path
        self.data = dict(self.DEFAULTS)
        self.load()

    def load(self):
        try:
            if os.path.isfile(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    for k, v in loaded.items():
                        self.data[k] = v
        except Exception as e:
            print("[配置加载失败] %s" % e)
        ev = self.data.get("notify_events") or {}
        base = dict(self.DEFAULTS["notify_events"])
        base.update({k: bool(v) for k, v in ev.items() if k in base})
        self.data["notify_events"] = base
        return self.data

    def save(self, data):
        self.data = dict(data)
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            return True, ""
        except Exception as e:
            return False, str(e)

    def get(self, key, default=None):
        return self.data.get(key, self.DEFAULTS.get(key, default))


# ===========================================================================
# Windows 开机自启（注册表）
# ===========================================================================
def autostart_command(minimized=False):
    """生成写入注册表的启动命令（用 pythonw 避免弹出控制台）。"""
    suffix = " --minimized" if minimized else ""
    if getattr(sys, "frozen", False):                 # PyInstaller 打包后的 exe
        return '"%s"%s' % (sys.executable, suffix)
    py = sys.executable
    pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
    if os.path.exists(pyw):
        py = pyw
    return '"%s" "%s"%s' % (py, os.path.abspath(__file__), suffix)


def set_autostart(enable, minimized=False):
    if not IS_WINDOWS or winreg is None:
        return False, "当前平台非 Windows，暂不支持注册表开机自启"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_WRITE)
        if enable:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, autostart_command(minimized))
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True, ("已设置开机自启" if enable else "已取消开机自启")
    except Exception as e:
        return False, "注册表操作失败：%s" % e


def get_autostart():
    if not IS_WINDOWS or winreg is None:
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_READ)
        value, _ = winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return bool(value)
    except Exception:
        return False


def http_post_json(url, payload, timeout=10):
    """统一 JSON POST：(ok, http_code, response_text)。requests 优先，否则 urllib。"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if requests is not None:
        resp = requests.post(url, data=body, headers=headers, timeout=timeout)
        return True, resp.status_code, resp.text
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, resp.getcode(), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return True, e.code, e.read().decode("utf-8", "replace")


# ===========================================================================
# 主应用
# ===========================================================================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("FRPC 管理工具  v%s" % APP_VERSION)
        self.root.geometry("1200x980")
        self.root.minsize(1000, 840)
        self._setup_styles()

        # ---- 路径 ----
        if IS_WINDOWS:
            base = os.environ.get("APPDATA") or os.path.expanduser("~")
            self.base_dir = os.path.join(base, APP_NAME)
        else:
            self.base_dir = os.path.join(os.path.expanduser("~"), ".config", APP_NAME)
        self.cfg_store = ConfigStore(os.path.join(self.base_dir, "config.json"))
        if not self.cfg_store.get("log_path"):
            self.cfg_store.data["log_path"] = os.path.join(self.base_dir, "logs", "frpc_manager.log")

        # ---- 运行时状态 ----
        self.log_queue = queue.Queue()
        self.proc = None                 # subprocess.Popen 对象
        self.proc_lock = threading.RLock()
        self.start_time = None
        self.restart_count = 0
        self.stop_event = threading.Event()
        self.restart_lock = threading.Lock()
        self.last_check_time = None
        self.last_check_result = "未检测"
        self.next_check_ts = 0.0
        self.daily_fired_date = None
        self._notify_last = {}           # 事件 -> 上次推送时间戳（冷却用）
        self.rt = {}                     # 配置快照：后台线程只读它，避免跨线程读 tk 变量

        self._init_vars()
        self._build_ui()
        self._sync_runtime()

        # ---- 后台线程 ----
        threading.Thread(target=self._health_worker, daemon=True).start()
        threading.Thread(target=self._daily_worker, daemon=True).start()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.log("程序启动 | 主机 %s | 配置目录 %s" % (socket.gethostname(), self.base_dir), "INFO")
        if self.get_autostart_state():
            self.var_autostart.set(True)

        # 托盘 + 启动即最小化（--minimized 用于开机自启时静默后台运行）
        self._start_tray()
        if self.var_start_minimized.get() or "--minimized" in sys.argv:
            self.root.after(300, self.hide_to_tray)

        if self.var_start_on_launch.get() and self.var_frpc_path.get():
            self.root.after(800, lambda: self.action_start(silent=True))

        self._tick = 0
        self.root.after(200, self._ui_tick)

    # ------------------------------------------------------------------
    # 样式表
    # ------------------------------------------------------------------
    def _setup_styles(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except Exception:
            pass
        T = THEME
        st.configure(".", background=T.BODY_BG, foreground=T.TEXT,
                     font=(T.FONT, 9), borderwidth=0)
        st.configure("TFrame", background=T.BODY_BG)
        st.configure("Card.TFrame", background=T.CARD_BG, relief="flat")
        st.configure("Card.TLabelframe", background=T.CARD_BG, bordercolor=T.BORDER,
                     lightcolor=T.CARD_BG, darkcolor=T.CARD_BG, relief="solid", borderwidth=1)
        st.configure("Card.TLabelframe.Label", background=T.CARD_BG, foreground=T.PRIMARY,
                     font=(T.FONT, 9, "bold"))
        st.configure("TLabel", background=T.CARD_BG, foreground=T.TEXT)
        st.configure("Sub.TLabel", background=T.CARD_BG, foreground=T.TEXT_SUB)
        st.configure("CardTitle.TLabel", background=T.CARD_BG, foreground=T.TEXT,
                     font=(T.FONT, 10, "bold"))
        st.configure("TEntry", fieldbackground="#ffffff", bordercolor=T.BORDER,
                     lightcolor=T.BORDER, darkcolor=T.BORDER, padding=(6, 4))
        st.configure("TSpinbox", fieldbackground="#ffffff", bordercolor=T.BORDER,
                     lightcolor=T.BORDER, darkcolor=T.BORDER, padding=(4, 3), arrowsize=12)
        st.configure("TCombobox", fieldbackground="#ffffff", bordercolor=T.BORDER,
                     lightcolor=T.BORDER, darkcolor=T.BORDER, padding=(5, 3))
        st.configure("TCheckbutton", background=T.CARD_BG, foreground=T.TEXT, padding=(2, 2))
        st.map("TCheckbutton", background=[("active", T.CARD_BG)])
        st.configure("TSeparator", background=T.BORDER)

        def btn(name, bg, fg="white", active=None):
            st.configure(name, background=bg, foreground=fg, bordercolor=bg,
                         lightcolor=bg, darkcolor=bg, relief="flat",
                         padding=(10, 7), font=(T.FONT, 9, "bold"), anchor="center")
            st.map(name, background=[("active", active or bg), ("disabled", "#cbd5e1")],
                   foreground=[("disabled", "#f8fafc")])

        btn("Green.TButton", T.GREEN, active=T.GREEN_D)
        btn("Red.TButton", T.RED, active=T.RED_D)
        btn("Amber.TButton", T.AMBER, active=T.AMBER_D)
        btn("Blue.TButton", T.PRIMARY, active=T.PRIMARY_D)
        st.configure("Ghost.TButton", background="#ffffff", foreground=T.TEXT,
                     bordercolor=T.BORDER, lightcolor=T.BORDER, darkcolor=T.BORDER,
                     relief="solid", borderwidth=1, padding=(10, 6), font=(T.FONT, 9))
        st.map("Ghost.TButton", background=[("active", "#eef2f9")])

    # ------------------------------------------------------------------
    # 变量
    # ------------------------------------------------------------------
    def _init_vars(self):
        d = self.cfg_store.data
        v, b = tk.StringVar, tk.BooleanVar
        self.var_frpc_path = v(value=d.get("frpc_path", ""))
        self.var_frpc_conf = v(value=d.get("frpc_conf", ""))
        self.var_url = v(value=d.get("health_url", ""))
        self.var_method = v(value=(d.get("http_method") or "POST").upper())
        self.var_timeout = v(value=str(d.get("health_timeout", 5)))
        self.var_interval = v(value=str(d.get("health_interval", 60)))
        self.var_code = v(value=str(d.get("expect_code", 200)))
        self.var_post = v(value=d.get("post_data", ""))
        self.var_auth_type = v(value=d.get("auth_type", "none"))
        self.var_auth_value = v(value=d.get("auth_value", ""))
        self.var_show_auth = b(value=False)
        self.var_health_enabled = b(value=bool(d.get("health_enabled", True)))
        self.var_crash_restart = b(value=bool(d.get("crash_restart", True)))
        self.var_start_on_launch = b(value=bool(d.get("start_on_launch", False)))
        self.var_daily_enabled = b(value=bool(d.get("daily_enabled", False)))
        self.var_daily_time = v(value=d.get("daily_time", "08:00"))
        self.var_log_to_file = b(value=bool(d.get("log_to_file", True)))
        self.var_log_path = v(value=d.get("log_path", ""))
        self.var_auto_scroll = b(value=bool(d.get("auto_scroll", True)))
        self.var_stop_on_exit = b(value=bool(d.get("stop_on_exit", True)))
        self.var_autostart = b(value=False)
        # 最小化 / 托盘
        self.var_minimize_to_tray = b(value=bool(d.get("minimize_to_tray", True)))
        self.var_start_minimized = b(value=bool(d.get("start_minimized", False)))
        # 通知
        self.var_notify_enabled = b(value=bool(d.get("notify_enabled", False)))
        self.var_token = v(value=d.get("push_token", ""))
        self.var_channel = v(value=d.get("push_channel", "wechat"))
        self.var_template = v(value=d.get("push_template", "txt"))
        self.var_topic = v(value=d.get("push_topic", ""))
        self.var_cooldown = v(value=str(d.get("notify_cooldown", 60)))
        self.var_show_token = b(value=False)
        ev = d.get("notify_events") or {}
        self.var_ev = {k: b(value=bool(ev.get(k, False))) for k in EVENT_LABEL if k != "test"}
        # 状态
        self.var_state = v(value="未运行")
        self.var_pid = v(value="-")
        self.var_uptime = v(value="-")
        self.var_restarts = v(value="0")
        self.var_last_check = v(value="-")
        self.var_next_check = v(value="-")

    def _sync_runtime(self):
        """把界面变量快照到普通 dict，供后台线程安全读取（主线程调用）。"""
        def i(x, d):
            try:
                return int(float(str(x).strip()))
            except Exception:
                return d
        self.rt = {
            "frpc_path": self.var_frpc_path.get().strip(),
            "frpc_conf": self.var_frpc_conf.get().strip(),
            "url": self.var_url.get().strip(),
            "method": (self.var_method.get() or "POST").upper(),
            "timeout": max(1, i(self.var_timeout.get(), 5)),
            "interval": max(5, i(self.var_interval.get(), 60)),
            "code": i(self.var_code.get(), 200),
            "post": self.var_post.get(),
            "auth_type": (self.var_auth_type.get() or "none").strip().lower(),
            "auth_value": self.var_auth_value.get().strip(),
            "health_enabled": bool(self.var_health_enabled.get()),
            "crash_restart": bool(self.var_crash_restart.get()),
            "daily_enabled": bool(self.var_daily_enabled.get()),
            "daily_time": self.var_daily_time.get().strip(),
            "log_to_file": bool(self.var_log_to_file.get()),
            "log_path": self.var_log_path.get().strip(),
            "minimize_to_tray": bool(self.var_minimize_to_tray.get()),
            "start_minimized": bool(self.var_start_minimized.get()),
            "notify_enabled": bool(self.var_notify_enabled.get()),
            "push_token": self.var_token.get().strip(),
            "push_channel": self.var_channel.get().strip(),
            "push_template": self.var_template.get().strip() or "txt",
            "push_topic": self.var_topic.get().strip(),
            "notify_cooldown": max(0, i(self.var_cooldown.get(), 60)),
            "notify_events": {k: bool(x.get()) for k, x in self.var_ev.items()},
        }

    def collect_config(self):
        return {
            "frpc_path": self.var_frpc_path.get().strip(),
            "frpc_conf": self.var_frpc_conf.get().strip(),
            "health_url": self.var_url.get().strip(),
            "http_method": (self.var_method.get() or "POST").upper(),
            "health_timeout": self._to_int(self.var_timeout.get(), 5),
            "health_interval": self._to_int(self.var_interval.get(), 60),
            "expect_code": self._to_int(self.var_code.get(), 200),
            "post_data": self.var_post.get(),
            "auth_type": (self.var_auth_type.get() or "none").strip().lower(),
            "auth_value": self.var_auth_value.get().strip(),
            "health_enabled": bool(self.var_health_enabled.get()),
            "crash_restart": bool(self.var_crash_restart.get()),
            "start_on_launch": bool(self.var_start_on_launch.get()),
            "daily_enabled": bool(self.var_daily_enabled.get()),
            "daily_time": self.var_daily_time.get().strip(),
            "log_to_file": bool(self.var_log_to_file.get()),
            "log_path": self.var_log_path.get().strip(),
            "auto_scroll": bool(self.var_auto_scroll.get()),
            "stop_on_exit": bool(self.var_stop_on_exit.get()),
            "autostart": bool(self.var_autostart.get()),
            "minimize_to_tray": bool(self.var_minimize_to_tray.get()),
            "start_minimized": bool(self.var_start_minimized.get()),
            "notify_enabled": bool(self.var_notify_enabled.get()),
            "push_token": self.var_token.get().strip(),
            "push_channel": self.var_channel.get().strip(),
            "push_template": self.var_template.get().strip() or "txt",
            "push_topic": self.var_topic.get().strip(),
            "notify_cooldown": self._to_int(self.var_cooldown.get(), 60),
            "notify_events": {k: bool(x.get()) for k, x in self.var_ev.items()},
        }

    @staticmethod
    def _to_int(x, default):
        try:
            return int(float(str(x).strip()))
        except Exception:
            return default

    # ------------------------------------------------------------------
    # 界面组装
    # ------------------------------------------------------------------
    def _build_ui(self):
        self.root.configure(bg=THEME.BODY_BG)
        self._build_header()

        body = ttk.Frame(self.root, padding=12)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body, width=320)
        left.grid(row=0, column=0, sticky="nswe", padx=(0, 12))
        left.columnconfigure(0, weight=1)
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nswe")
        right.rowconfigure(2, weight=1)
        right.columnconfigure(0, weight=1)

        self._build_control_card(left, 0)
        self._build_status_card(left, 1)
        self._build_schedule_card(left, 2)

        self._build_config_card(right, 0)
        self._build_notify_card(right, 1)
        self._build_log_card(right, 2)

        self._build_footer()

    # ---------------- 顶栏 ----------------
    def _build_header(self):
        bar = tk.Frame(self.root, bg=THEME.HEADER_BG, height=62)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)

        logo = tk.Canvas(bar, width=36, height=36, bg=THEME.HEADER_BG, highlightthickness=0)
        logo.pack(side=tk.LEFT, padx=(16, 10), pady=13)
        logo.create_rectangle(0, 0, 36, 36, fill=THEME.PRIMARY, outline="")
        logo.create_text(18, 19, text="F", fill="white", font=(THEME.FONT, 16, "bold"))

        txt = tk.Frame(bar, bg=THEME.HEADER_BG)
        txt.pack(side=tk.LEFT, pady=11)
        tk.Label(txt, text="FRPC 管理工具", bg=THEME.HEADER_BG, fg="white",
                 font=(THEME.FONT, 13, "bold")).pack(anchor="w")
        tk.Label(txt, text="FRP 客户端运行监控 · 健康自愈 · 外部通知",
                 bg=THEME.HEADER_BG, fg=THEME.HEADER_SUB, font=(THEME.FONT, 8)).pack(anchor="w")

        self.pill = tk.Label(bar, text="● 未运行", bg=THEME.RED, fg="white",
                             font=(THEME.FONT, 9, "bold"), padx=14, pady=5)
        self.pill.pack(side=tk.RIGHT, padx=16)
        self.lbl_clock = tk.Label(bar, text="", bg=THEME.HEADER_BG, fg=THEME.HEADER_SUB,
                                  font=(THEME.FONT, 9))
        self.lbl_clock.pack(side=tk.RIGHT, padx=(0, 6))

    # ---------------- 左：运行控制 ----------------
    def _build_control_card(self, parent, row):
        card = ttk.LabelFrame(parent, text=" 运行控制 ", style="Card.TLabelframe", padding=12)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        card.columnconfigure(0, weight=1)

        ttk.Button(card, text="▶   启动 frpc", style="Green.TButton",
                   command=lambda: self.action_start(False)).grid(row=0, column=0, sticky="ew", pady=3)

        r2 = ttk.Frame(card, style="Card.TFrame")
        r2.grid(row=1, column=0, sticky="ew", pady=3)
        r2.columnconfigure(0, weight=1)
        r2.columnconfigure(1, weight=1)
        ttk.Button(r2, text="■   停止", style="Red.TButton",
                   command=self.action_stop).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(r2, text="⟳   重启", style="Amber.TButton",
                   command=self.action_restart).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        r3 = ttk.Frame(card, style="Card.TFrame")
        r3.grid(row=2, column=0, sticky="ew", pady=3)
        r3.columnconfigure(0, weight=1)
        r3.columnconfigure(1, weight=1)
        ttk.Button(r3, text="立即检测", style="Ghost.TButton",
                   command=self.action_check_now).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(r3, text="保存配置", style="Blue.TButton",
                   command=self.action_save).grid(row=0, column=1, sticky="ew", padx=(4, 0))
        ttk.Button(card, text="⇱  最小化到托盘后台运行", style="Ghost.TButton",
                   command=self.hide_to_tray).grid(row=3, column=0, sticky="ew", pady=3)

    # ---------------- 左：运行状态 ----------------
    def _build_status_card(self, parent, row):
        card = ttk.LabelFrame(parent, text=" 运行状态 ", style="Card.TLabelframe", padding=12)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        card.columnconfigure(1, weight=1)

        def kv(r, key, var):
            ttk.Label(card, text=key, style="Sub.TLabel").grid(row=r, column=0, sticky="w", pady=3)
            ttk.Label(card, textvariable=var, font=(THEME.FONT, 9, "bold")).grid(row=r, column=1, sticky="e")

        ttk.Label(card, text="当前状态", style="Sub.TLabel").grid(row=0, column=0, sticky="w", pady=3)
        self.lbl_state = ttk.Label(card, textvariable=self.var_state,
                                   font=(THEME.FONT, 9, "bold"), foreground=THEME.RED)
        self.lbl_state.grid(row=0, column=1, sticky="e")
        kv(1, "进程 PID", self.var_pid)
        kv(2, "运行时长", self.var_uptime)
        kv(3, "自动重启次数", self.var_restarts)
        ttk.Separator(card).grid(row=4, column=0, columnspan=2, sticky="ew", pady=6)
        kv(5, "上次检测", self.var_last_check)
        kv(6, "下次检测", self.var_next_check)

    # ---------------- 左：自启与计划 ----------------
    def _build_schedule_card(self, parent, row):
        card = ttk.LabelFrame(parent, text=" 自启与计划 ", style="Card.TLabelframe", padding=12)
        card.grid(row=row, column=0, sticky="ew")
        card.columnconfigure(0, weight=1)

        ttk.Checkbutton(card, text="开机自启（写入注册表）", variable=self.var_autostart,
                        command=self.toggle_autostart).grid(row=0, column=0, sticky="w", pady=2)
        ttk.Checkbutton(card, text="程序启动时自动运行 frpc",
                        variable=self.var_start_on_launch).grid(row=1, column=0, sticky="w", pady=2)
        ttk.Checkbutton(card, text="进程意外退出时自动重启",
                        variable=self.var_crash_restart).grid(row=2, column=0, sticky="w", pady=2)
        ttk.Checkbutton(card, text="退出程序时停止 frpc",
                        variable=self.var_stop_on_exit).grid(row=3, column=0, sticky="w", pady=2)

        ttk.Checkbutton(card, text="关闭窗口时最小化到托盘" + ("" if pystray else "（缺 pystray，仅任务栏）"),
                        variable=self.var_minimize_to_tray).grid(row=4, column=0, sticky="w", pady=2)
        ttk.Checkbutton(card, text="启动时最小化到托盘",
                        variable=self.var_start_minimized).grid(row=5, column=0, sticky="w", pady=2)

        ttk.Frame(card, height=1, style="Card.TFrame").grid(row=6, column=0, sticky="ew", pady=8)
        d = ttk.Frame(card, style="Card.TFrame")
        d.grid(row=7, column=0, sticky="ew")
        ttk.Checkbutton(d, text="每日定时启动", variable=self.var_daily_enabled).pack(side=tk.LEFT)
        ttk.Entry(d, width=7, textvariable=self.var_daily_time, justify="center").pack(side=tk.RIGHT)
        ttk.Label(d, text="时间 (HH:MM)", style="Sub.TLabel").pack(side=tk.RIGHT, padx=(0, 6))

    # ---------------- 右：基础配置 ----------------
    def _build_config_card(self, parent, row):
        card = ttk.LabelFrame(parent, text=" 基础配置 ", style="Card.TLabelframe", padding=12)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        card.columnconfigure(1, weight=1)

        def line(r, label, var, btn_text=None, cmd=None):
            ttk.Label(card, text=label, style="Sub.TLabel").grid(
                row=r, column=0, sticky="w", pady=3, padx=(0, 8))
            f = ttk.Frame(card, style="Card.TFrame")
            f.grid(row=r, column=1, sticky="ew", pady=3)
            f.columnconfigure(0, weight=1)
            ttk.Entry(f, textvariable=var).grid(row=0, column=0, sticky="ew")
            if btn_text:
                ttk.Button(f, text=btn_text, style="Ghost.TButton", width=8,
                           command=cmd).grid(row=0, column=1, padx=(6, 0))

        line(0, "frpc 程序", self.var_frpc_path, "浏览", self.browse_frpc)
        line(1, "配置文件(-c)", self.var_frpc_conf, "浏览", self.browse_conf)

        # 检测 URL + 请求方法（很多探测接口只接受 GET，POST 会返回 405）
        ttk.Label(card, text="检测 URL", style="Sub.TLabel").grid(
            row=2, column=0, sticky="w", pady=3, padx=(0, 8))
        uf = ttk.Frame(card, style="Card.TFrame")
        uf.grid(row=2, column=1, sticky="ew", pady=3)
        uf.columnconfigure(0, weight=1)
        ttk.Entry(uf, textvariable=self.var_url).grid(row=0, column=0, sticky="ew")
        ttk.Combobox(uf, width=6, state="readonly", textvariable=self.var_method,
                     values=HTTP_METHODS).grid(row=0, column=1, padx=(6, 0))

        nums = ttk.Frame(card, style="Card.TFrame")
        nums.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 2))
        ttk.Label(nums, text="超时(秒)", style="Sub.TLabel").grid(row=0, column=0)
        ttk.Spinbox(nums, from_=1, to=120, width=6, textvariable=self.var_timeout).grid(row=0, column=1, padx=(4, 16))
        ttk.Label(nums, text="检测间隔(秒)", style="Sub.TLabel").grid(row=0, column=2)
        ttk.Spinbox(nums, from_=5, to=86400, width=8, textvariable=self.var_interval).grid(row=0, column=3, padx=(4, 16))
        ttk.Label(nums, text="期望状态码", style="Sub.TLabel").grid(row=0, column=4)
        ttk.Spinbox(nums, from_=100, to=599, width=6, textvariable=self.var_code).grid(row=0, column=5, padx=(4, 16))
        ttk.Checkbutton(nums, text="开启健康检测", variable=self.var_health_enabled).grid(row=0, column=6)

        ttk.Label(card, text="POST 数据", style="Sub.TLabel").grid(
            row=4, column=0, sticky="w", pady=3, padx=(0, 8))
        ttk.Entry(card, textvariable=self.var_post).grid(row=4, column=1, sticky="ew", pady=3)
        ttk.Label(card, text="留空则不发送请求体；填写 JSON（如 {\"k\":\"v\"}）时自动加 "
                            "Content-Type: application/json（请求体仅 POST 方法发送）",
                  style="Sub.TLabel", font=(THEME.FONT, 8)).grid(row=5, column=1, sticky="w")
        ttk.Label(card, text="请求认证", style="Sub.TLabel").grid(
            row=6, column=0, sticky="w", pady=(6, 3), padx=(0, 8))
        af = ttk.Frame(card, style="Card.TFrame")
        af.grid(row=6, column=1, sticky="ew", pady=(6, 3))
        ttk.Combobox(af, width=10, state="readonly", textvariable=self.var_auth_type,
                     values=AUTH_TYPES).pack(side=tk.LEFT)
        self.entry_auth = ttk.Entry(af, textvariable=self.var_auth_value, show="*")
        self.entry_auth.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Checkbutton(af, text="显示", variable=self.var_show_auth,
                        command=self._toggle_auth_mask).pack(side=tk.LEFT)
        ttk.Label(card, text='basic → 用户名:密码（转 Authorization: Basic）；bearer → Token；'
                            'header → {"X-Token":"abc"} 或每行一行 X-Token: abc；'
                            '也可直接写在 URL 里：http://user:pass@host/path',
                  style="Sub.TLabel", font=(THEME.FONT, 8), wraplength=720,
                  justify="left").grid(row=7, column=1, sticky="w")

        ttk.Button(card, text="测试 frpc 可执行文件", style="Ghost.TButton",
                   command=self.test_frpc).grid(row=8, column=1, sticky="w", pady=(6, 0))

    # ---------------- 右：外部通知 ----------------
    def _build_notify_card(self, parent, row):
        card = ttk.LabelFrame(parent, text=" 外部通知（PushPlus 推送加） ",
                              style="Card.TLabelframe", padding=12)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        card.columnconfigure(1, weight=1)

        ttk.Checkbutton(card, text="启用外部通知推送", variable=self.var_notify_enabled).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        ttk.Label(card, text="Token", style="Sub.TLabel").grid(
            row=1, column=0, sticky="w", pady=3, padx=(0, 8))
        tf = ttk.Frame(card, style="Card.TFrame")
        tf.grid(row=1, column=1, sticky="ew")
        tf.columnconfigure(0, weight=1)
        self.entry_token = ttk.Entry(tf, textvariable=self.var_token, show="*")
        self.entry_token.grid(row=0, column=0, sticky="ew")
        ttk.Checkbutton(tf, text="显示", variable=self.var_show_token,
                        command=self._toggle_token_mask).grid(row=0, column=1, padx=(8, 0))
        ttk.Label(card, text="在 pushplus.plus 登录后获取用户 Token（默认微信公众号渠道）",
                  style="Sub.TLabel", font=(THEME.FONT, 8)).grid(row=2, column=1, sticky="w")

        opts = ttk.Frame(card, style="Card.TFrame")
        opts.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 2))
        ttk.Label(opts, text="渠道", style="Sub.TLabel").grid(row=0, column=0)
        ttk.Combobox(opts, width=10, state="readonly", textvariable=self.var_channel,
                     values=CHANNELS).grid(row=0, column=1, padx=(4, 16))
        ttk.Label(opts, text="模板", style="Sub.TLabel").grid(row=0, column=2)
        ttk.Combobox(opts, width=8, state="readonly", textvariable=self.var_template,
                     values=TEMPLATES).grid(row=0, column=3, padx=(4, 16))
        ttk.Label(opts, text="群组编码", style="Sub.TLabel").grid(row=0, column=4)
        ttk.Entry(opts, width=12, textvariable=self.var_topic).grid(row=0, column=5, padx=(4, 16))
        ttk.Label(opts, text="冷却(秒)", style="Sub.TLabel").grid(row=0, column=6)
        ttk.Spinbox(opts, from_=0, to=3600, width=6, textvariable=self.var_cooldown).grid(row=0, column=7, padx=(4, 0))

        ttk.Label(card, text="推送事件", style="Sub.TLabel").grid(
            row=4, column=0, sticky="nw", pady=(6, 0), padx=(0, 8))
        ev = ttk.Frame(card, style="Card.TFrame")
        ev.grid(row=4, column=1, sticky="w", pady=(6, 0))
        for i, key in enumerate([k for k in EVENT_LABEL if k != "test"]):
            ttk.Checkbutton(ev, text=EVENT_LABEL[key], variable=self.var_ev[key]).grid(
                row=i // 3, column=i % 3, sticky="w", padx=(0, 14), pady=2)

        acts = ttk.Frame(card, style="Card.TFrame")
        acts.grid(row=5, column=1, sticky="w", pady=(8, 0))
        ttk.Button(acts, text="发送测试推送", style="Blue.TButton",
                   command=self.action_test_push).pack(side=tk.LEFT)
        ttk.Label(acts, text="冷却时间用于防止异常时反复推送刷屏", style="Sub.TLabel",
                  font=(THEME.FONT, 8)).pack(side=tk.LEFT, padx=10)

    # ---------------- 右：运行日志 ----------------
    def _build_log_card(self, parent, row):
        card = ttk.LabelFrame(parent, text=" 运行日志 ", style="Card.TLabelframe", padding=10)
        card.grid(row=row, column=0, sticky="nswe")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=1)

        bar = ttk.Frame(card, style="Card.TFrame")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Checkbutton(bar, text="自动滚动", variable=self.var_auto_scroll).pack(side=tk.LEFT)
        ttk.Checkbutton(bar, text="保存到文件", variable=self.var_log_to_file).pack(side=tk.LEFT, padx=10)
        ttk.Button(bar, text="清空", style="Ghost.TButton", width=6,
                   command=self.clear_log).pack(side=tk.LEFT)
        ttk.Button(bar, text="打开日志文件", style="Ghost.TButton", width=12,
                   command=self.open_log_file).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="日志目录", style="Ghost.TButton", width=9,
                   command=self.open_log_dir).pack(side=tk.LEFT)
        ttk.Label(bar, textvariable=self.var_log_path, style="Sub.TLabel",
                  font=(THEME.FONT, 8)).pack(side=tk.LEFT, padx=10)

        self.txt = scrolledtext.ScrolledText(card, wrap=tk.WORD, height=9,
                                             font=(THEME.MONO, 9), bg=THEME.LOG_BG,
                                             relief="solid", borderwidth=1,
                                             highlightbackground=THEME.BORDER)
        self.txt.grid(row=1, column=0, sticky="nswe")
        self.txt.configure(state=tk.DISABLED)
        for lvl, color in LEVEL_COLOR.items():
            self.txt.tag_config(lvl, foreground=color)

    # ---------------- 底栏 ----------------
    def _build_footer(self):
        foot = tk.Frame(self.root, bg=THEME.BODY_BG, height=26)
        foot.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Label(foot, text="  配置：%s" % self.cfg_store.path, bg=THEME.BODY_BG,
                 fg=THEME.TEXT_SUB, font=(THEME.FONT, 8)).pack(side=tk.LEFT)
        tk.Label(foot, text="v%s  |  requests: %s  |  Python %s  " % (
            APP_VERSION, "可用" if requests else "未安装(urllib)", platform.python_version()),
            bg=THEME.BODY_BG, fg=THEME.TEXT_SUB, font=(THEME.FONT, 8)).pack(side=tk.RIGHT)

    def _toggle_token_mask(self):
        self.entry_token.configure(show="" if self.var_show_token.get() else "*")

    def _toggle_auth_mask(self):
        self.entry_auth.configure(show="" if self.var_show_auth.get() else "*")

    # ------------------------------------------------------------------
    # 日志
    # ------------------------------------------------------------------
    def log(self, msg, level="INFO"):
        """线程安全写日志：界面队列 + 可选文件。"""
        now = datetime.datetime.now()
        self.log_queue.put((level, "[%s] [%s] %s" % (now.strftime("%H:%M:%S"), level, msg)))
        if self.rt.get("log_to_file"):
            path = self.rt.get("log_path") or os.path.join(self.base_dir, "logs", "frpc_manager.log")
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "a", encoding="utf-8") as f:
                    f.write("[%s] [%s] %s\n" % (now.strftime("%Y-%m-%d %H:%M:%S"), level, msg))
            except Exception as e:
                self.log_queue.put(("ERROR", "[日志写入文件失败] %s" % e))

    def _drain_log_queue(self):
        """主线程：把队列里的日志刷到界面。"""
        try:
            while True:
                level, line = self.log_queue.get_nowait()
                self.txt.configure(state=tk.NORMAL)
                self.txt.insert(tk.END, line + "\n", level)
                if int(self.txt.index("end-1c").split(".")[0]) > 3000:
                    self.txt.delete("1.0", "300.0")
                if self.var_auto_scroll.get():
                    self.txt.see(tk.END)
                self.txt.configure(state=tk.DISABLED)
        except queue.Empty:
            pass

    def clear_log(self):
        self.txt.configure(state=tk.NORMAL)
        self.txt.delete("1.0", tk.END)
        self.txt.configure(state=tk.DISABLED)
        self.log("界面日志已清空", "INFO")

    def open_log_file(self):
        path = self.var_log_path.get().strip() or os.path.join(self.base_dir, "logs", "frpc_manager.log")
        if not os.path.isfile(path):
            messagebox.showinfo("提示", "日志文件尚不存在：\n%s" % path)
            return
        self._open_path(path)

    def open_log_dir(self):
        d = os.path.dirname(self.var_log_path.get().strip()) or os.path.join(self.base_dir, "logs")
        os.makedirs(d, exist_ok=True)
        self._open_path(d)

    @staticmethod
    def _open_path(path):
        try:
            if IS_WINDOWS:
                os.startfile(path)  # noqa
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("错误", "打开失败：%s" % e)

    # ------------------------------------------------------------------
    # 文件选择 / frpc 测试
    # ------------------------------------------------------------------
    def browse_frpc(self):
        init = os.path.dirname(self.var_frpc_path.get()) if self.var_frpc_path.get() else "."
        path = filedialog.askopenfilename(
            title="选择 frpc 可执行文件", initialdir=init or ".",
            filetypes=[("可执行文件", "*.exe" if IS_WINDOWS else "*"), ("所有文件", "*.*")])
        if path:
            self.var_frpc_path.set(path)
            self.log("已选择 frpc：%s" % path, "INFO")

    def browse_conf(self):
        init = os.path.dirname(self.var_frpc_conf.get() or self.var_frpc_path.get()) or "."
        path = filedialog.askopenfilename(
            title="选择 frpc 配置文件", initialdir=init,
            filetypes=[("配置文件", "*.ini *.toml *.yaml *.yml *.conf"), ("所有文件", "*.*")])
        if path:
            self.var_frpc_conf.set(path)

    def test_frpc(self):
        path = self.var_frpc_path.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showwarning("提示", "请先选择有效的 frpc 可执行文件")
            return
        try:
            out = subprocess.run([path, "--version"], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, timeout=10,
                                 creationflags=self._no_window_flags(), text=True,
                                 encoding="utf-8", errors="replace")
            messagebox.showinfo("frpc 测试", "返回码：%d\n\n输出：\n%s" % (out.returncode, out.stdout.strip()))
            self.log("frpc 测试：%s" % out.stdout.strip().replace("\n", " | "), "OK")
        except Exception as e:
            messagebox.showerror("frpc 测试失败", str(e))
            self.log("frpc 测试失败：%s" % e, "ERROR")

    @staticmethod
    def _no_window_flags():
        return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if IS_WINDOWS else 0

    # ------------------------------------------------------------------
    # 进程管理（subprocess）
    # ------------------------------------------------------------------
    def is_running(self):
        with self.proc_lock:
            return self.proc is not None and self.proc.poll() is None

    def _start_internal(self):
        path = self.rt.get("frpc_path", "").strip()
        if not path:
            return False, "未配置 frpc 可执行文件路径"
        if not os.path.isfile(path):
            return False, "frpc 文件不存在：%s" % path
        if self.is_running():
            return False, "frpc 已在运行中"

        cmd = [path]
        conf = self.rt.get("frpc_conf", "").strip()
        if conf:
            cmd += ["-c", conf]
        try:
            startupinfo = None
            if IS_WINDOWS:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    stdin=subprocess.DEVNULL, cwd=os.path.dirname(path) or None,
                                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                                    creationflags=self._no_window_flags(), startupinfo=startupinfo)
        except Exception as e:
            return False, "启动失败：%s" % e

        with self.proc_lock:
            self.proc = proc
            self.start_time = datetime.datetime.now()
        threading.Thread(target=self._reader, args=(proc.stdout, "FRPC"), daemon=True).start()
        threading.Thread(target=self._reader, args=(proc.stderr, "ERROR"), daemon=True).start()
        return True, "frpc 已启动，PID=%d" % proc.pid

    def _reader(self, pipe, level):
        """读取子进程输出并转入日志（后台线程）。"""
        try:
            for line in iter(pipe.readline, ""):
                line = ANSI_RE.sub("", line).rstrip("\r\n")   # 去掉 ANSI 颜色转义符
                if line:
                    self.log(line, level)
        except Exception:
            pass
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    def _stop_internal(self, timeout=5):
        with self.proc_lock:
            proc = self.proc
            self.proc = None
        if proc is None:
            return True, "frpc 未在运行"
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)
            return True, "frpc 已停止"
        except Exception as e:
            return False, "停止失败：%s" % e
        finally:
            self.start_time = None

    def _restart_internal(self, reason=""):
        with self.restart_lock:
            self.log("正在重启 frpc ...（原因：%s）" % (reason or "手动"), "WARN")
            self._stop_internal()
            time.sleep(1.0)
            ok, msg = self._start_internal()
            if ok:
                self.restart_count += 1
                self.log("重启完成：%s" % msg, "OK")
            else:
                self.log("重启失败：%s" % msg, "ERROR")
            return ok, msg

    # ---- 按钮动作（主线程）----
    def action_start(self, silent=False):
        self._sync_runtime()
        ok, msg = self._start_internal()
        self.log(msg, "OK" if ok else "ERROR")
        if ok:
            self.notify("start", "FRPC 已启动", msg)
        elif not silent:
            messagebox.showerror("启动失败", msg)

    def action_stop(self):
        ok, msg = self._stop_internal()
        self.log(msg, "OK" if ok else "ERROR")
        if ok:
            self.notify("stop", "FRPC 已停止", msg)

    def action_restart(self):
        self._sync_runtime()
        threading.Thread(target=self._restart_and_notify, daemon=True).start()
        self.log("已发起重启任务", "INFO")

    def _restart_and_notify(self):
        ok, msg = self._restart_internal("手动重启")
        if ok:
            self.notify("restart", "FRPC 已重启", msg)

    def action_check_now(self):
        self._sync_runtime()
        threading.Thread(target=self._do_check_and_handle, args=("手动检测",), daemon=True).start()
        self.log("已发起一次健康检测", "INFO")

    def action_save(self):
        self._sync_runtime()
        ok, err = self.cfg_store.save(self.collect_config())
        self.log("配置已保存到 %s" % self.cfg_store.path if ok else "配置保存失败：%s" % err,
                 "OK" if ok else "ERROR")
        if ok:
            messagebox.showinfo("保存配置", "配置已保存。")
        else:
            messagebox.showerror("保存失败", err)

    def action_test_push(self):
        self._sync_runtime()
        self.notify("test", "FRPC 管理工具 - 测试推送",
                    "这是一条来自 FRPC 管理工具的测试消息。")

    def toggle_autostart(self):
        enable = bool(self.var_autostart.get())
        ok, msg = set_autostart(enable, minimized=bool(self.var_start_minimized.get()))
        if not ok:
            self.var_autostart.set(get_autostart())
        self.log("开机自启：%s" % msg, "OK" if ok else "ERROR")
        if not ok:
            messagebox.showwarning("开机自启", msg)

    def get_autostart_state(self):
        return get_autostart()

    # ------------------------------------------------------------------
    # 外部通知（PushPlus 推送加）
    # ------------------------------------------------------------------
    def notify(self, event, title, content=""):
        """按事件推送通知：开关判断 + 事件过滤 + 冷却，实际发送在后台线程。"""
        rt = self.rt
        if not rt.get("notify_enabled"):
            return
        if event != "test" and not rt.get("notify_events", {}).get(event, False):
            return
        token = rt.get("push_token", "").strip()
        label = EVENT_LABEL.get(event, event)
        if not token:
            self.log("未配置 PushPlus Token，跳过推送（%s）" % label, "WARN")
            return
        if event != "test":
            wait = rt.get("notify_cooldown", 60) - (time.time() - self._notify_last.get(event, 0))
            if wait > 0:
                self.log("推送冷却中（%s，%.0f 秒后可再次推送）" % (label, wait), "INFO")
                return
        self._notify_last[event] = time.time()
        threading.Thread(target=self._push_worker,
                         args=(event, token, title, content), daemon=True).start()

    def _push_worker(self, event, token, title, content):
        payload = {
            "token": token,
            "title": title or "FRPC 管理工具",
            "content": "%s\n\n主机：%s\n时间：%s" % (
                content, socket.gethostname(),
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            "template": self.rt.get("push_template", "txt"),
        }
        if self.rt.get("push_channel"):
            payload["channel"] = self.rt.get("push_channel")
        if self.rt.get("push_topic"):
            payload["topic"] = self.rt.get("push_topic")
        label = EVENT_LABEL.get(event, event)
        try:
            _, code, text = http_post_json(PUSHPLUS_URL, payload, timeout=10)
            try:
                res = json.loads(text)
                code = res.get("code", code)
                msg = res.get("msg", "")
            except Exception:
                msg = text[:120]
            if int(code) == 200:
                self.log("PushPlus 推送成功[%s]：%s" % (label, msg), "PUSH")
            else:
                self.log("PushPlus 推送失败[%s]：code=%s %s" % (label, code, msg), "ERROR")
        except Exception as e:
            self.log("PushPlus 推送异常[%s]：%s" % (label, e), "ERROR")

    # ------------------------------------------------------------------
    # 健康检测
    # ------------------------------------------------------------------
    def _build_auth_headers(self):
        """按认证方式生成请求头（密码不写入日志）。"""
        headers = {}
        atype = (self.rt.get("auth_type") or "none").strip().lower()
        value = (self.rt.get("auth_value") or "").strip()
        try:
            if atype == "basic" and value:
                # 格式：用户名:密码  ->  Authorization: Basic base64(user:pass)
                user, _, pwd = value.partition(":")
                token = base64.b64encode(("%s:%s" % (user, pwd)).encode("utf-8")).decode("ascii")
                headers["Authorization"] = "Basic %s" % token
            elif atype == "bearer" and value:
                headers["Authorization"] = "Bearer %s" % value
            elif atype == "header" and value:
                try:
                    for k, val in json.loads(value).items():     # {"X-Token":"abc"}
                        headers[str(k)] = str(val)
                except Exception:
                    for line in value.splitlines():              # 每行：X-Token: abc
                        if ":" in line:
                            k, val = line.split(":", 1)
                            headers[k.strip()] = val.strip()
        except Exception as e:
            self.log("认证信息解析失败：%s" % e, "ERROR")
        return headers

    @staticmethod
    def mask_url(text):
        """日志脱敏：把 URL 中的 user:pass@ 隐藏掉。"""
        return re.sub(r"(://[^/\s:]+):[^/\s]*@", r"\1:***@", str(text))

    def _request_once(self, method, url, body, headers, timeout):
        """发一次请求，返回 (code, error)；code=None 表示连接失败/超时。"""
        if requests is not None:
            resp = requests.request(method, url, data=body, headers=headers, timeout=timeout)
            return resp.status_code, None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.getcode(), None
        except urllib.error.HTTPError as e:
            return e.code, None                       # 4xx/5xx 也是有效响应
        except Exception as e:
            return None, "请求失败（%s）：%s" % (type(e).__name__, e)

    def _check_once(self):
        """执行一次健康检测；POST 收到 405 时自动改用 GET 重试一次（避免误重启）。"""
        url = self.rt.get("url", "").strip()
        if not url:
            return False, "未配置检测 URL"
        timeout = self.rt.get("timeout", 5)
        expect = self.rt.get("code", 200)
        method = (self.rt.get("method") or "POST").upper()
        if method not in HTTP_METHODS:
            method = "POST"

        headers = self._build_auth_headers()
        body = None
        raw = (self.rt.get("post") or "").strip()
        if method == "POST" and raw:                  # 请求体仅 POST 有意义
            try:
                json.loads(raw)
                body, headers["Content-Type"] = raw.encode("utf-8"), "application/json"
            except Exception:
                body, headers["Content-Type"] = raw.encode("utf-8"), "text/plain; charset=utf-8"

        try:
            code, err = self._request_once(method, url, body, headers, timeout)
        except Exception as e:
            return False, "请求失败（%s）：%s" % (type(e).__name__, e)
        if err:
            return False, err
        if code == expect:
            return True, "HTTP %d 正常（%s）" % (code, method)

        # 405 Method Not Allowed：多数只读探测接口只接受 GET，自动改用 GET 重试一次
        if method == "POST" and code == 405:
            self.log("服务端返回 405（不接受 POST），自动改用 GET 重试；"
                     "建议在界面把检测方法改为 GET", "WARN")
            try:
                code2, err2 = self._request_once("GET", url, None, headers, timeout)
            except Exception as e:
                return False, "GET 重试失败（%s）：%s" % (type(e).__name__, e)
            if err2:
                return False, err2
            if code2 == expect:
                return True, "HTTP %d 正常（POST 405，已自动改用 GET）" % code2
            return False, "状态码异常：期望 %d，实际 %d（GET 重试）" % (expect, code2)

        return False, "状态码异常：期望 %d，实际 %d（%s）" % (expect, code, method)

    def _do_check_and_handle(self, reason="周期检测"):
        """检测一次，失败则通知并重启。"""
        if not self.is_running():
            self.last_check_time = datetime.datetime.now()
            self.last_check_result = "未运行（跳过检测）"
            self.log("frpc 未运行，跳过健康检测", "WARN")
            return
        ok, detail = self._check_once()
        self.last_check_time = datetime.datetime.now()
        self.last_check_result = ("正常 - " + detail) if ok else ("异常 - " + detail)
        target = self.mask_url(self.rt.get("url", "").strip())   # 日志不泄露 URL 里的账号密码
        self.log("健康检测[%s] %s：%s" % (reason, target, self.last_check_result),
                 "OK" if ok else "WARN")
        if not ok:
            self.notify("fail", "FRPC 健康检测失败",
                        "检测结果：%s\n即将自动重启 frpc。" % detail)
            threading.Thread(target=self._restart_internal,
                             args=("健康检测失败：" + detail,), daemon=True).start()

    def _health_worker(self):
        """健康检测后台线程：每 interval 秒检测一次。"""
        while not self.stop_event.is_set():
            interval = max(5, self.rt.get("interval", 60) or 60)
            if self.rt.get("health_enabled") and self.rt.get("url"):
                self._do_check_and_handle("周期检测")
                self.next_check_ts = time.time() + interval
            else:
                self.next_check_ts = 0.0
            if self.stop_event.wait(interval):
                break

    # ------------------------------------------------------------------
    # 每日定时启动
    # ------------------------------------------------------------------
    def _daily_worker(self):
        while not self.stop_event.is_set():
            try:
                if self.rt.get("daily_enabled"):
                    t = (self.rt.get("daily_time") or "08:00").strip()
                    hh, mm = (t.split(":") + ["0"])[:2]
                    now = datetime.datetime.now()
                    target = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
                    if now >= target and self.daily_fired_date != now.date():
                        self.daily_fired_date = now.date()
                        if not self.is_running():
                            self.log("每日定时触发，启动 frpc（%s）" % t, "INFO")
                            ok, msg = self._start_internal()
                            self.log(msg, "OK" if ok else "ERROR")
                            if ok:
                                self.notify("daily", "FRPC 每日定时启动", msg)
                        else:
                            self.log("每日定时触发，frpc 已在运行，跳过", "INFO")
            except Exception as e:
                self.log("每日定时解析出错：%s" % e, "ERROR")
            if self.stop_event.wait(20):
                break

    # ------------------------------------------------------------------
    # 界面刷新（主线程定时轮询，避免跨线程操作控件）
    # ------------------------------------------------------------------
    def _ui_tick(self):
        self._drain_log_queue()
        self._tick += 1
        if self._tick % 5 == 0:                     # 约每秒刷新一次
            self._sync_runtime()
            self._refresh_status()
            self.lbl_clock.configure(text=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.root.after(200, self._ui_tick)

    def _refresh_status(self):
        running = self.is_running()
        if running:
            self.var_state.set("运行中")
            self.lbl_state.configure(foreground=THEME.GREEN)
            self.pill.configure(text="● 运行中", bg=THEME.GREEN)
            self.var_pid.set(str(self.proc.pid))
            if self.start_time:
                s = int((datetime.datetime.now() - self.start_time).total_seconds())
                self.var_uptime.set("%02d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60))
        else:
            self.var_state.set("未运行")
            self.lbl_state.configure(foreground=THEME.RED)
            self.pill.configure(text="● 未运行", bg=THEME.RED)
            self.var_pid.set("-")
            self.var_uptime.set("-")
            if self.proc is not None:               # 进程意外退出
                code = self.proc.poll()
                self.proc = None
                self.log("frpc 进程已退出，返回码：%s" % code, "WARN" if code == 0 else "ERROR")
                if self.rt.get("crash_restart"):
                    self.notify("crash", "FRPC 异常退出",
                                "进程退出，返回码：%s\n即将自动重启。" % code)
                    threading.Thread(target=self._restart_internal,
                                     args=("进程意外退出",), daemon=True).start()
                self.start_time = None

        self.var_restarts.set(str(self.restart_count))
        self.var_last_check.set(self.last_check_result if not self.last_check_time
                                else "%s  %s" % (self.last_check_time.strftime("%H:%M:%S"),
                                                 self.last_check_result))
        if self.next_check_ts and self.rt.get("health_enabled"):
            self.var_next_check.set("%d 秒后" % max(0, int(self.next_check_ts - time.time())))
        else:
            self.var_next_check.set("-")

    # ------------------------------------------------------------------
    # 最小化 / 系统托盘后台运行
    # ------------------------------------------------------------------
    def _tray_image(self):
        """运行时绘制托盘图标，不依赖外部图片文件。"""
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([2, 2, 62, 62], radius=14, fill=(37, 99, 235, 255))
        try:
            font = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 42)
        except Exception:
            font = ImageFont.load_default()
        d.text((32, 34), "F", fill=(255, 255, 255, 255), font=font, anchor="mm")
        return img

    def _start_tray(self):
        """启动托盘图标（pystray.run 阻塞，放在 daemon 线程里）。"""
        self.tray = None
        if pystray is None:
            self.log("未安装 pystray / pillow，托盘不可用；关闭窗口将最小化到任务栏"
                     "（pip install pystray pillow 可启用托盘）", "WARN")
            return
        try:
            menu = _TrayMenu(
                _TrayItem(lambda t: "FRPC 状态：" + ("运行中" if self.is_running() else "未运行"),
                          None, enabled=False),
                _TrayMenu.SEPARATOR,
                _TrayItem("显示主界面", self._tray_cb("show"), default=True),
                _TrayItem("启动 frpc", self._tray_cb("start")),
                _TrayItem("停止 frpc", self._tray_cb("stop")),
                _TrayItem("重启 frpc", self._tray_cb("restart")),
                _TrayMenu.SEPARATOR,
                _TrayItem("退出程序", self._tray_cb("quit")),
            )
            self.tray = pystray.Icon(APP_NAME, self._tray_image(), "FRPC 管理工具", menu)
            threading.Thread(target=self.tray.run, daemon=True).start()
            self.log("托盘图标已启动：关闭窗口最小化到托盘，右键托盘可操作", "INFO")
        except Exception as e:
            self.tray = None
            self.log("托盘启动失败：%s" % e, "ERROR")

    def _tray_cb(self, action):
        def cb(icon=None, item=None):
            self.root.after(0, lambda: self._tray_action(action))   # 回到主线程执行
        return cb

    def _tray_action(self, action):
        if action == "show":
            self.show_window()
        elif action == "start":
            self.action_start(False)
        elif action == "stop":
            self.action_stop()
        elif action == "restart":
            self.action_restart()
        elif action == "quit":
            self.do_exit()

    def hide_to_tray(self):
        """隐藏窗口转入后台：健康检测、日志、定时等线程继续运行。"""
        self.root.withdraw()
        if self.tray is None:
            self.root.iconify()
            self.log("已最小化到任务栏（托盘不可用）", "INFO")
        else:
            self.log("已最小化到系统托盘，程序在后台继续运行", "INFO")

    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        try:
            self.root.focus_force()
        except Exception:
            pass

    def _stop_tray(self):
        try:
            if self.tray is not None:
                self.tray.stop()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 退出
    # ------------------------------------------------------------------
    def on_close(self):
        """点关闭按钮：按设置最小化到后台；否则真正退出。"""
        if self.var_minimize_to_tray.get():
            self.hide_to_tray()
            return
        self.do_exit()

    def do_exit(self):
        try:
            if self.var_stop_on_exit.get() and self.is_running():
                if messagebox.askyesno("退出确认", "退出程序将同时停止 frpc 进程，是否继续？"):
                    self._stop_internal()
            self._sync_runtime()
            self.cfg_store.save(self.collect_config())
        except Exception:
            pass
        self._stop_tray()
        self.stop_event.set()
        try:
            self.root.destroy()
        except Exception:
            pass


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
