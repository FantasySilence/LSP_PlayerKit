# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 测试公共配置             #
# =================================== #

import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture()
def api():
    """带临时数据目录的 Api，所有工具共用."""

    from lspkit.api import Api
    from lspkit.platform.locator import Location
    from lspkit.platform.storage import Runtime
    from lspkit.platform.store import Store
    from lspkit.tools import build_registry

    root = Path(tempfile.mkdtemp(prefix="lspkit-test-"))
    runtime = Runtime(
        location=Location(path=root, source="default", writable=True),
        store=Store(root),
        webview_dir=root / "webview",
    )
    return Api(runtime, build_registry())
