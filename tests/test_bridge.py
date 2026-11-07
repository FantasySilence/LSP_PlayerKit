# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: API 契约测试             #
# =================================== #

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

from lspkit.api import Api, _export_dir
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
    assert ids == ["pearl", "border", "material", "puppet", "slime"]


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


def test_pearl_panel_defaults_roundtrip(api):
    data = api.settings_get("pearl")["data"]
    assert data["targetX"] == 0
    assert data["targetZ"] == 0
    assert data["fireMode"] == "flat"

    saved = api.settings_save(
        "pearl", {**data, "targetX": 10000, "targetZ": 10000, "fireMode": "eject"}
    )
    assert saved["ok"] is True
    assert api.settings_get("pearl")["data"]["targetX"] == 10000
    assert api.settings_get("pearl")["data"]["fireMode"] == "eject"


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


def test_material_convert(api):
    text = "\n".join(
        [
            "minecraft:white_wool 1728",
            "minecraft:stone, 100000",
            "minecraft:stone 1,000",
            "# comment",
            "unparsed line",
        ]
    )
    result = api.tool_call("material", "convert", {"text": text})
    assert result["ok"] is True, result
    data = result["data"]

    assert data["totals"]["kinds"] == 2
    assert data["totals"]["perBox"] == 1728
    assert data["totals"]["boxesNeeded"] == 60
    assert data["skipped"] == 1
    assert data["warnings"][0]["line"] == 5

    stone = next(row for row in data["items"] if row["name"] == "minecraft:stone")
    assert (stone["count"], stone["shulkers"], stone["stacks"], stone["items"]) == (
        101000,
        58,
        12,
        8,
    )

    wool = next(row for row in data["items"] if row["name"] == "minecraft:white_wool")
    assert (wool["shulkers"], wool["stacks"], wool["items"]) == (1, 0, 0)


def test_material_rejects_empty_input(api):
    blank = api.tool_call("material", "convert", {"text": "   \n\n"})
    assert blank["ok"] is False
    assert blank["error"]["code"] == "INVALID_INPUT"

    nothing = api.tool_call("material", "convert", {"text": "no numbers here"})
    assert nothing["ok"] is False
    assert nothing["error"]["code"] == "NO_ENTRIES"


def test_material_merges_multiple_lists(api):
    texts = [
        {"name": "a.csv", "text": "铁锭 10\n木棍 5"},
        {"name": "b.csv", "text": "铁锭 6\n苹果 2"},
    ]
    result = api.tool_call("material", "convert", {"texts": texts})
    assert result["ok"] is True, result
    data = result["data"]

    counts = {row["name"]: row["count"] for row in data["items"]}
    assert counts == {"铁锭": 16, "木棍": 5, "苹果": 2}
    assert data["totals"]["kinds"] == 3
    assert data["sources"] == [
        {"name": "a.csv", "kinds": 2, "items": 15},
        {"name": "b.csv", "kinds": 2, "items": 8},
    ]

    packed = api.tool_call("material", "pack", {"texts": texts})
    assert packed["ok"] is True, packed
    assert packed["data"]["totals"]["kinds"] == 3


def test_material_multi_lists_validation(api):
    empty = api.tool_call("material", "convert", {"texts": []})
    assert empty["ok"] is False
    assert empty["error"]["code"] == "INVALID_INPUT"

    unparsed = api.tool_call(
        "material", "convert", {"texts": [{"name": "x.csv", "text": "no numbers"}]}
    )
    assert unparsed["ok"] is False
    assert unparsed["error"]["code"] == "NO_ENTRIES"


def test_material_settings_change_capacity(api):
    current = api.settings_get("material")["data"]
    assert current == {"stackSize": "64", "shulkerSlots": 27, "exportDir": ""}

    saved = api.settings_save("material", {**current, "stackSize": "16", "shulkerSlots": 1})
    assert saved["ok"] is True

    result = api.tool_call("material", "convert", {"text": "minecraft:stone 100"})
    row = result["data"]["items"][0]
    assert result["data"]["totals"]["perBox"] == 16
    assert (row["shulkers"], row["stacks"], row["items"]) == (6, 0, 4)
    assert result["data"]["totals"]["boxesNeeded"] == 7

    reset = api.settings_reset("material")
    assert reset["data"] == {"stackSize": "64", "shulkerSlots": 27, "exportDir": ""}


def test_material_parses_litematica_csv(api):
    text = "\n".join(
        [
            '"Item","Total","Missing","Available"',
            '"白色染色玻璃",4766,4766,0',
            '"侦测器",1219,1219,0',
            '"末影箱",55,55,1',
        ]
    )
    result = api.tool_call("material", "convert", {"text": text})
    assert result["ok"] is True, result
    data = result["data"]

    assert data["totals"]["kinds"] == 3
    assert data["totals"]["count"] == 6040
    assert data["totals"]["perBox"] == 1728

    # 名称与导入清单完全一致，数量取 Total 列而不是 Available 列
    assert [row["name"] for row in data["items"]] == ["白色染色玻璃", "侦测器", "末影箱"]
    assert [row["count"] for row in data["items"]] == [4766, 1219, 55]


def test_material_unstackable_uses_items_only(api):
    saved = api.settings_save("material", {"stackSize": "1", "shulkerSlots": 27})
    assert saved["ok"] is True

    text = '"Item","Total"\n"铁砧",100'
    result = api.tool_call("material", "convert", {"text": text})
    row = result["data"]["items"][0]

    assert result["data"]["totals"]["perBox"] == 27
    assert row["stack"] == 1
    assert (row["shulkers"], row["stacks"], row["items"]) == (3, 0, 19)


def test_material_per_item_stack_override(api):
    text = '"Item","Total"\n"铁砧",100\n"石块",100'
    result = api.tool_call("material", "convert", {"text": text, "stacks": {"铁砧": "1"}})
    assert result["ok"] is True, result

    rows = {row["name"]: row for row in result["data"]["items"]}
    assert rows["铁砧"]["stack"] == 1
    assert (rows["铁砧"]["shulkers"], rows["铁砧"]["stacks"], rows["铁砧"]["items"]) == (3, 0, 19)
    assert rows["石块"]["stack"] == 64
    assert (rows["石块"]["shulkers"], rows["石块"]["stacks"], rows["石块"]["items"]) == (0, 1, 36)


def test_material_rejects_bad_stack_override(api):
    result = api.tool_call(
        "material",
        "convert",
        {"text": '"Item","Total"\n"铁砧",10', "stacks": {"铁砧": "32"}},
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


def test_material_ignore_excludes_from_result(api):
    text = '"Item","Total"\n"石头",1000\n"木棍",100\n"铁砧",100'
    result = api.tool_call("material", "convert", {"text": text, "ignore": ["木棍"]})
    assert result["ok"] is True, result
    data = result["data"]

    assert [row["name"] for row in data["items"]] == ["石头", "铁砧"]
    assert data["totals"]["kinds"] == 2
    assert data["totals"]["count"] == 1100
    assert [row["name"] for row in data["ignoredItems"]] == ["木棍"]
    assert data["ignoredItems"][0]["count"] == 100

    plan = api.tool_call("material", "pack", {"text": text, "ignore": ["木棍", "铁砧"]})
    assert plan["ok"] is True, plan
    assert plan["data"]["totals"]["kinds"] == 1
    assert len(plan["data"]["ignoredItems"]) == 2


def test_material_packing_uses_minimum_boxes(api):
    text = '"Item","Total"\n"石头",1000\n"木棍",100\n"铁砧",100'
    result = api.tool_call("material", "pack", {"text": text})
    assert result["ok"] is True, result
    data = result["data"]

    slots = data["totals"]["slots"]
    capacity = data["totals"]["capacity"]
    assert capacity == 27
    assert data["totals"]["boxes"] == -(-slots // capacity)
    assert sum(box["used"] for box in data["boxes"]) == slots
    assert all(box["used"] <= capacity for box in data["boxes"])

    converted = api.tool_call("material", "convert", {"text": text})["data"]
    packed = sum(entry["count"] for box in data["boxes"] for entry in box["entries"])
    assert packed == converted["totals"]["count"]


def test_material_packing_unstackable(api):
    text = '"Item","Total"\n"铁砧",1000'
    result = api.tool_call("material", "pack", {"text": text, "stacks": {"铁砧": "1"}})
    assert result["ok"] is True, result
    data = result["data"]

    assert data["totals"]["capacity"] == 27
    assert data["totals"]["boxes"] == 38
    assert sum(box["used"] for box in data["boxes"]) == 1000
    assert all(len(box["entries"]) == 1 for box in data["boxes"])


class _DialogWindow:
    def __init__(self) -> None:
        self.kwargs: dict | None = None

    def create_file_dialog(self, *args, **kwargs):
        self.kwargs = kwargs
        return None


def test_export_dir_defaults_to_data_output(tmp_path):
    target = _export_dir("", tmp_path)
    assert target == tmp_path / "output"
    assert target.is_dir()

    custom = tmp_path / "custom"
    assert _export_dir(str(custom), tmp_path) == custom
    assert custom.is_dir()


def test_file_save_text_uses_export_dir(api):
    window = _DialogWindow()
    api._rt.window = window

    result = api.file_save_text("plan.csv", "a,b", "")
    assert result["ok"] is True
    assert window.kwargs["save_filename"] == "plan.csv"
    assert str(window.kwargs["directory"]).endswith("output")

    custom = api._rt.location.path / "custom_out"
    api.file_save_text("plan.csv", "a,b", str(custom))
    assert window.kwargs["directory"] == str(custom)


def test_file_open_texts_reads_multiple(api, tmp_path):
    first = tmp_path / "a.csv"
    second = tmp_path / "b.csv"
    first.write_text('"Item","Total"\n"stone",12\n', encoding="utf-8")
    second.write_text("dirt 3\n", encoding="utf-8")

    class _MultiWindow:
        def __init__(self) -> None:
            self.kwargs: dict | None = None

        def create_file_dialog(self, *args, **kwargs):
            self.kwargs = kwargs
            return (str(first), str(second))

    window = _MultiWindow()
    api._rt.window = window

    result = api.file_open_texts()
    assert result["ok"] is True, result
    files = result["data"]["files"]
    assert [item["name"] for item in files] == ["a.csv", "b.csv"]
    assert window.kwargs["allow_multiple"] is True
    assert "stone" in files[0]["text"]
    assert "dirt" in files[1]["text"]

    single = api.file_open_text()
    assert single["data"]["name"] == "a.csv"
    assert window.kwargs["allow_multiple"] is False


def test_material_packing_merges_consecutive_full_boxes(api):
    result = api.tool_call("material", "pack", {"text": "minecraft:stone 5184"})
    assert result["ok"] is True, result
    data = result["data"]

    assert data["totals"]["boxes"] == 3
    groups = data["groups"]
    assert len(groups) == 1
    assert groups[0]["merged"] is True
    assert (groups[0]["from"], groups[0]["to"], groups[0]["boxes"]) == (1, 3, 3)
    assert groups[0]["used"] == 81

    entry = groups[0]["entries"][0]
    assert entry["name"] == "minecraft:stone"
    assert entry["slots"] == 81
    assert entry["count"] == 5184


def test_material_packing_keeps_mixed_and_partial_boxes(api):
    text = "minecraft:stone 1728\nminecraft:dirt 1"
    result = api.tool_call("material", "pack", {"text": text})
    assert result["ok"] is True, result

    groups = result["data"]["groups"]
    assert [group["merged"] for group in groups] == [False, False]
    assert [group["from"] for group in groups] == [1, 2]
    assert groups[1]["used"] < groups[1]["capacity"]

def test_material_accepts_preparsed_sources(api):
    result = api.tool_call(
        "material",
        "convert",
        {
            "sources": [
                {
                    "name": "a.litematic",
                    "entries": [
                        {"name": "石头", "count": 10},
                        {"name": "泥土", "count": 5},
                    ],
                },
                {"name": "b.csv", "text": "石头 3"},
            ]
        },
    )
    assert result["ok"] is True, result
    data = result["data"]

    counts = {row["name"]: row["count"] for row in data["items"]}
    assert counts == {"石头": 13, "泥土": 5}
    assert data["sources"] == [
        {"name": "a.litematic", "kinds": 2, "items": 15},
        {"name": "b.csv", "kinds": 1, "items": 3},
    ]


def test_material_rejects_sources_without_entries(api):
    result = api.tool_call(
        "material", "convert", {"sources": [{"name": "x", "entries": []}]}
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"

def test_material_localizes_preparsed_entries(api):
    result = api.tool_call(
        "material",
        "convert",
        {
            "sources": [
                {
                    "name": "x.litematic",
                    "entries": [{"id": "minecraft:stone", "name": "ignored", "count": 4}],
                }
            ],
            "locale": "en",
        },
    )
    assert result["ok"] is True, result
    assert [row["name"] for row in result["data"]["items"]] == ["Stone"]


def test_open_manual_opens_readme_pdf(api, monkeypatch):
    if not hasattr(os, "startfile"):
        pytest.skip("startfile 仅 Windows 提供")

    import lspkit.api as api_module

    opened: list = []
    monkeypatch.setattr(api_module.os, "startfile", lambda path: opened.append(path))

    assert api.open_manual("zh_CN")["ok"] is True
    assert api.open_manual("en")["ok"] is True
    assert opened[0].endswith("README.pdf")
    assert opened[1].endswith("README.en.pdf")


def test_open_manual_reports_missing_file(api, monkeypatch, tmp_path):
    import lspkit.api as api_module

    monkeypatch.setattr(api_module, "resource_dir", lambda: tmp_path)
    result = api.open_manual("zh_CN")
    assert result["ok"] is False
    assert result["error"]["code"] == "NOT_FOUND"
