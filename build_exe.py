#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
一键打包脚本：把 frpc_manager.py 打成单文件无控制台的 Windows exe。
用法：python build_exe.py     （需要先 pip install pyinstaller）
产物：dist/FrpcManager.exe
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ICON = os.path.join(HERE, "icon.ico") if os.path.exists(os.path.join(HERE, "icon.ico")) else None

cmd = [
    sys.executable, "-m", "PyInstaller",
    "-F", "-w",                      # 单文件、无控制台
    "-n", "FrpcManager",
    "--clean", "-y",
    "--distpath", os.path.join(HERE, "dist"),
    "--workpath", os.path.join(HERE, "build"),
    "--specpath", HERE,
]
if ICON:
    cmd += ["--icon", ICON]
cmd.append(os.path.join(HERE, "frpc_manager.py"))

print(">", " ".join(cmd))
raise SystemExit(subprocess.call(cmd))
