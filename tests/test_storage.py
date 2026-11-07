# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 数据目录测试             #
# =================================== #
# 测试层：platform.storage（Runtime / StorageManager）与 platform.store。
# 策略：pytest 的 tmp_path 充当数据目录，monkeypatch 掉真实用户目录指针，
# 验证切换目录时复制设置、不可写拒绝以及配置包导出/导入。

from __future__ import annotations

from pathlib import Path

import pytest

from lspkit.errors import AppError
from lspkit.platform import locator
from lspkit.platform.storage import Runtime, StorageManager
from lspkit.platform.store import Store


@pytest.fixture()
def runtime(tmp_path):
    """构造一个完全落在 tmp_path 下的 Runtime，避免碰真实 data/ 或 AppData."""
    return Runtime(
        location=locator.Location(path=tmp_path, source="default", writable=True),
        store=Store(tmp_path),
        webview_dir=tmp_path / "webview",
    )


def test_set_dir_copies_settings(runtime, tmp_path, monkeypatch):
    """验证切换数据目录会复制旧设置并记住新来源.

    输入：旧目录存 pearl/app 两份设置；切到 tmp_path/moved。
    期望：新目录出现 settings/pearl.json；runtime.store 能读回 maxTnt=1；
          location.source 变为 "user"。
    """
    monkeypatch.setattr(locator, "set_user_location", lambda path: None)
    # 把 set_user_location 换成 no-op：避免测试把 AppData/location.json 改到临时路径。
    runtime.store.save("pearl", {"maxTnt": 1})
    runtime.store.save("app", {"language": "zh_CN"})

    target = tmp_path / "moved"
    # set_dir 会先写探针、复制 settings/*.json，再 rebind 到新目录。
    manager = StorageManager(runtime)
    info = manager.set_dir(str(target))

    assert info["path"] == str(target)
    assert (target / "settings" / "pearl.json").exists()
    assert runtime.store.load("pearl")["maxTnt"] == 1
    assert runtime.location.source == "user"


def test_set_dir_rejects_unwritable(runtime, tmp_path):
    """验证目标目录不可写时抛 AppError.

    输入：先建一个普通文件 afile，再把 set_dir 指向 afile/child。
    期望：locator._probe 失败，抛 AppError（STORAGE_UNWRITABLE）。
    """
    manager = StorageManager(runtime)
    blocker = tmp_path / "afile"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(AppError):
        manager.set_dir(str(blocker / "child"))


def test_export_import_bundle(runtime, tmp_path):
    """验证配置的导出/导入往返.

    输入：旧目录保存 border.flightTime=400；export_all 得到 {名称: 内容}。
    期望：新 Runtime 的 import_all 后能读回同一个 flightTime。
    """
    runtime.store.save("border", {"flightTime": 400})
    payload = runtime.store.export_all()
    assert "border" in payload

    # import_all 会按名称写 JSON；这里换一个独立目录，模拟「导入到另一台机器」。
    clean = Runtime(
        location=locator.Location(path=tmp_path / "other", source="default", writable=True),
        store=Store(tmp_path / "other"),
        webview_dir=tmp_path / "webview2",
    )
    clean.store.import_all(payload)
    assert clean.store.load("border")["flightTime"] == 400
