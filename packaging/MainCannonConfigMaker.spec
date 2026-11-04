# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-05                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: PyInstaller 打包脚本     #
# =================================== #

# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包脚本（单文件控制台程序）.

用法：
    .venv\\Scripts\\pyinstaller packaging\\MainCannonConfigMaker.spec --noconfirm
产物：dist/MainCannonConfigMaker.exe
"""

from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821 - SPECPATH 由 PyInstaller 注入
BUNDLE = ROOT / "src" / "tool_bundles"

a = Analysis(
    [str(BUNDLE / "maincannon_configmaker.py")],
    pathex=[str(BUNDLE)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pandas", "matplotlib", "PIL", "numpy"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MainCannonConfigMaker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
