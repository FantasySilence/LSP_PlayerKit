# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: PyInstaller 打包脚本     #
# =================================== #

# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包脚本（onedir）.

用法：
    .venv\\Scripts\\pyinstaller packaging\\LSP_PlayerKit.spec --noconfirm
产物：dist/LSP_PlayerKit/LSP_PlayerKit.exe
"""

from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821 - SPECPATH 由 PyInstaller 注入

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[
        (str(ROOT / "web" / "dist"), "web/dist"),
        (str(ROOT / "resources"), "resources"),
    ],
    hiddenimports=[
        "webview.platforms.edgechromium",
        "clr_loader",
        "pythonnet",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pandas", "matplotlib", "PIL"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LSP_PlayerKit",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ROOT / "resources" / "images" / "Ender_Pearl.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="LSP_PlayerKit",
)
