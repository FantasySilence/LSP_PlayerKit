# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 数据目录测试             #
# =================================== #

from __future__ import annotations

from pathlib import Path

import pytest

from lspkit.errors import AppError
from lspkit.platform import locator
from lspkit.platform.storage import Runtime, StorageManager
from lspkit.platform.store import Store


@pytest.fixture()
def runtime(tmp_path):
    return Runtime(
        location=locator.Location(path=tmp_path, source="default", writable=True),
        store=Store(tmp_path),
        webview_dir=tmp_path / "webview",
    )


def test_set_dir_copies_settings(runtime, tmp_path, monkeypatch):
    monkeypatch.setattr(locator, "set_user_location", lambda path: None)
    runtime.store.save("pearl", {"maxTnt": 1})
    runtime.store.save("app", {"language": "zh_CN"})

    target = tmp_path / "moved"
    manager = StorageManager(runtime)
    info = manager.set_dir(str(target))

    assert info["path"] == str(target)
    assert (target / "settings" / "pearl.json").exists()
    assert runtime.store.load("pearl")["maxTnt"] == 1
    assert runtime.location.source == "user"


def test_set_dir_rejects_unwritable(runtime, tmp_path):
    manager = StorageManager(runtime)
    blocker = tmp_path / "afile"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(AppError):
        manager.set_dir(str(blocker / "child"))


def test_export_import_bundle(runtime, tmp_path):
    runtime.store.save("border", {"flightTime": 400})
    payload = runtime.store.export_all()
    assert "border" in payload

    clean = Runtime(
        location=locator.Location(path=tmp_path / "other", source="default", writable=True),
        store=Store(tmp_path / "other"),
        webview_dir=tmp_path / "webview2",
    )
    clean.store.import_all(payload)
    assert clean.store.load("border")["flightTime"] == 400
