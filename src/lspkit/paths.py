# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 运行期路径解析           #
# =================================== #

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """
    可执行文件所在目录；开发模式下是仓库根目录.
    """

    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _bundle_dir() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", app_dir()))
    return app_dir()


def resource_dir() -> Path:
    return _bundle_dir() / "resources"


def web_dir() -> Path:
    return _bundle_dir() / "web" / "dist"


def appdata_dir() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / "LSP_PlayerKit"
    return Path.home() / ".lsp_player_kit"


def icon_path() -> Path:
    return resource_dir() / "images" / "Ender_Pearl.ico"


def version_info() -> dict:
    import json

    path = resource_dir() / "version.json"
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        from lspkit import __version__

        return {"version": __version__, "name": "LSP PlayerKit"}
