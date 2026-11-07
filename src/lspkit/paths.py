# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 运行期路径解析           #
# =================================== #
# 本文件职责：回答“资源在哪、数据默认写哪”这类路径问题。
# 源码运行与 PyInstaller 打包后的目录结构不同，全部差异都收敛在这个文件里。

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    """是否运行在 PyInstaller 打包出的 exe 中（打包后 sys.frozen 为 True）。"""

    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """
    可执行文件所在目录；开发模式下是仓库根目录.
    """

    if is_frozen():
        # 打包后：exe 所在目录就是用户能看见的“应用目录”，数据默认放在它旁边的 data/
        return Path(sys.executable).resolve().parent
    # 源码运行：本文件是 <仓库>/src/lspkit/paths.py，往上两级即仓库根目录
    return Path(__file__).resolve().parents[2]


def _bundle_dir() -> Path:
    """只读资源（web/dist、resources）的根目录；打包后是 PyInstaller 的临时解包目录。"""

    if is_frozen():
        # sys._MEIPASS 由 PyInstaller 注入，指向它解压 datas 的临时目录；取不到就退回 exe 目录
        return Path(getattr(sys, "_MEIPASS", app_dir()))
    return app_dir()


def resource_dir() -> Path:
    """图标、内置说明文档、版本号等只读资源所在目录。"""

    return _bundle_dir() / "resources"


def web_dir() -> Path:
    """前端构建产物目录（npm run build 的输出），由本地 HTTP 服务托管给 WebView。"""

    return _bundle_dir() / "web" / "dist"


def appdata_dir() -> Path:
    """用户级配置目录：Windows 用 %APPDATA%/LSP_PlayerKit，其它平台退回 ~/.lsp_player_kit。"""

    base = os.environ.get("APPDATA")
    if base:
        # Windows 下 %APPDATA% 形如 C:\Users\<用户名>\AppData\Roaming，不随程序位置变化
        return Path(base) / "LSP_PlayerKit"
    return Path.home() / ".lsp_player_kit"


def icon_path() -> Path:
    """窗口与任务栏图标（.ico）；文件不存在时调用方会跳过设置图标。"""

    return resource_dir() / "images" / "Ender_Pearl.ico"


def version_info() -> dict:
    """读取 resources/version.json（含 version / name）；读不到就退回代码内的 __version__。"""

    import json

    path = resource_dir() / "version.json"
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # 延迟导入：paths 被 lspkit/__init__ 早期引用，顶层导入会形成循环
        from lspkit import __version__

        return {"version": __version__, "name": "LSP PlayerKit"}
