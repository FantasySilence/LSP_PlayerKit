# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 测试公共配置             #
# =================================== #
# 测试公共配置：把 src/ 加入 sys.path，并提供带临时数据目录的 Api fixture。
# 所有用例都只碰临时目录，不会读写仓库 data/ 或用户 AppData；
# api fixture 每次新建 Runtime（Store 落在 tempfile.mkdtemp 下），用例之间互不影响。

import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
# src 布局：测试直接 import lspkit，不要求先 pip install -e .；
# 放到 sys.path 最前面，避免环境里同名的已安装包抢先命中。


@pytest.fixture()
def api():
    """带临时数据目录的 Api，所有工具共用."""
    # 临时目录由系统 temp 管理；Store 会在其下创建 settings/ 与 backups/。

    from lspkit.api import Api
    from lspkit.platform.locator import Location
    from lspkit.platform.storage import Runtime
    from lspkit.platform.store import Store
    from lspkit.tools import build_registry

    root = Path(tempfile.mkdtemp(prefix="lspkit-test-"))
    # 每个用例一个独立目录，测试之间不会共享设置、站点表或台账。
    runtime = Runtime(
        location=Location(path=root, source="default", writable=True),
        store=Store(root),
        webview_dir=root / "webview",
    )
    return Api(runtime, build_registry())
