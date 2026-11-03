# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: API 契约测试             #
# =================================== #

import json
import sys
import tempfile
from pathlib import Path

import pytest

from lspkit.api import Api
from lspkit.platform.locator import Location
from lspkit.platform.storage import Runtime
from lspkit.platform.store import Store
from lspkit.tools import build_registry


@pytest.fixture()
def api():
    root = Path(tempfile.mkdtemp(prefix="lspkit-test-"))
    registry = build_registry()
    location = Location(path=root, source="default", writable=True)
    runtime = Runtime(location=location, store=Store(root), webview_dir=root / "webview")
    yield Api(runtime, registry)


def test_app_state_lists_tools(api):
    result = api.app_state()
    assert result["ok"] is True
    ids = [tool["id"] for tool in result["data"]["tools"]]
    assert ids == ["pearl", "border"]


def test_pearl_calculate_and_decode(api):
    result = api.tool_call(
        "pearl", "calculate",
        {"origin": {"x": -31.9375, "z": -8.0625}, "target": {"x": 5000, "z": 5000},
         "maxTnt": 400, "mode": "flat"},
    )
    assert result["ok"] is True, result
    data = result["data"]
    assert data["direction"] in ("east", "west", "north", "south")
    assert data["rows"], "至少应有一组配置"

    row = data["rows"][0]
    decode = api.tool_call("pearl", "decode", {"blue": row["blue"], "red": row["red"]})
    assert decode["ok"] is True
    assert decode["data"]["blueText"].startswith(f"{row['blue']} =")


def test_border_calculate_and_decode(api):
    result = api.tool_call(
        "border", "calculate",
        {"origin": {"x": 9996.24, "y": 256, "z": 9999.24},
         "target": {"x": 0, "y": 128, "z": 0}, "time": 400},
    )
    assert result["ok"] is True, result
    rows = result["data"]["rows"]
    assert len(rows) == 100
    row = rows[0]
    decode = api.tool_call(
        "border", "decode",
        {"tnt": [row["t1"], row["t2"], row["t3"]],
         "motion": {"x": row["mx"], "y": row["my"], "z": row["mz"]},
         "dirLabel": row["dirLabel"],
         "origin": {"x": 9996.24, "y": 256, "z": 9999.24}},
    )
    assert decode["ok"] is True, decode
    assert "3个TNT" in decode["data"]["text"]


def test_invalid_input_returns_envelope_not_exception(api):
    result = api.tool_call("pearl", "calculate", {"target": {"x": "abc", "z": 0}})
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"

    unknown = api.tool_call("nope", "calculate", {})
    assert unknown["ok"] is False
    assert unknown["error"]["code"] == "UNKNOWN_TOOL"


def test_settings_roundtrip_and_validation(api):
    current = api.settings_get("pearl")["data"]
    current["maxTnt"] = 1234
    saved = api.settings_save("pearl", current)
    assert saved["ok"] is True
    assert api.settings_get("pearl")["data"]["maxTnt"] == 1234

    bad = api.settings_save("pearl", {**current, "maxTnt": -1})
    assert bad["ok"] is False
    assert bad["error"]["code"] == "INVALID_SETTING"

    reset = api.settings_reset("pearl")
    assert reset["ok"] is True
    assert reset["data"]["maxTnt"] == 3640


def test_storage_info(api):
    info = api.storage_info()["data"]
    assert "path" in info and "source" in info


class _FakeWindow:
    def __init__(self, path: Path) -> None:
        self._path = path

    def create_file_dialog(self, *args, **kwargs):
        return [str(self._path)]


def test_import_wrong_tool_file_is_rejected(api, tmp_path):
    payload = {
        "default_x_init": "9996.24",
        "default_y_init": "256",
        "default_z_init": "9999.24",
        "default_x_target": "0",
        "default_y_target": "128",
        "default_z_target": "0",
        "default_flying_time": "1200",
    }
    file = tmp_path / "border.json"
    file.write_text(json.dumps(payload), encoding="utf-8")
    api._rt.window = _FakeWindow(file)

    result = api.settings_import_file("pearl")
    assert result["ok"] is False
    assert result["error"]["code"] == "WRONG_TOOL_FILE"


def test_import_legacy_pearl_file(api, tmp_path):
    payload = {
        "IS_EJECTION_AVAILABLE": True,
        "MAX_TNT": 1234,
        "MAX_TNT_UNIT": 260,
        "XZ_INIT_POSITION": {"X": 1.5, "Z": -2.5},
        "MOTION_FOR_FLAT_FIRE": {
            "XZ_MOTION": 0.6,
            "Y_MOTION": -0.001,
            "Y_INIT_MOTION": 0.27,
            "Y_INIT_POSITION": 178.0,
        },
        "MOTION_FOR_EJECTIONS": {
            "XZ_MOTION": 0.6,
            "Y_MOTION": 0.0006,
            "Y_INIT_MOTION": 0.69,
            "Y_INIT_POSITION": 178.4,
        },
    }
    file = tmp_path / "settings.json"
    file.write_text(json.dumps(payload), encoding="utf-8")
    api._rt.window = _FakeWindow(file)

    result = api.settings_import_file("pearl")
    assert result["ok"] is True, result
    assert result["data"]["migrated"] is True
    assert result["data"]["values"]["maxTnt"] == 1234
    assert result["data"]["values"]["originX"] == 1.5
