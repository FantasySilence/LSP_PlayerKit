# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 假人搬货：站点与导入     #
# =================================== #

import json

import pytest

from lspkit.tools.puppet.core import stations as station_core
from lspkit.tools.puppet.legacy import parse

STATION = {
    "id": "all",
    "name": "重溟洋工业区·全物品",
    "prefix": "all",
    "dimension": "overworld",
    "x": 567,
    "y": 102,
    "z": -595,
}


def test_normalize_accepts_valid():
    station = station_core.normalize(STATION)
    assert station["x"] == 567.0
    assert station["dimension"] == "overworld"
    assert station["note"] == ""


@pytest.mark.parametrize(
    ("patch", "message"),
    [
        ({"name": ""}, "名称不能为空"),
        ({"prefix": "带中文"}, "前缀"),
        ({"prefix": "x" * 13}, "12"),
        ({"dimension": "moon"}, "维度"),
        ({"x": "abc"}, "X"),
        ({"y": 99999}, "Y"),
        ({"x": 1e9}, "范围"),
    ],
)
def test_normalize_rejects_invalid(patch, message):
    with pytest.raises(ValueError, match=message):
        station_core.normalize({**STATION, **patch})


def test_normalize_splits_legacy_name_into_group():
    station = station_core.normalize(STATION)
    assert station["group"] == "重溟洋工业区"
    assert station["name"] == "全物品"


def test_normalize_keeps_explicit_group():
    station = station_core.normalize({**STATION, "name": "仓库", "group": "主城"})
    assert station["group"] == "主城"
    assert station["name"] == "仓库"


def test_normalize_rejects_group_with_space():
    with pytest.raises(ValueError, match="分组"):
        station_core.normalize({**STATION, "name": "仓库", "group": "工业 区"})


def test_parse_line_with_group():
    parsed = parse("仓库 1 2 3 wh 主城 the_end\n")
    station = parsed["stations"][0]
    assert station["name"] == "仓库"
    assert station["group"] == "主城"
    assert station["prefix"] == "wh"
    assert station["dimension"] == "the_end"


def test_normalize_truncates_long_note():
    station = station_core.normalize({**STATION, "note": "x" * 100})
    assert len(station["note"]) == 60


def test_upsert_and_remove():
    stations = []
    stations, created = station_core.upsert(stations, STATION)
    assert created and len(stations) == 1

    moved = dict(STATION, x=600)
    stations, created = station_core.upsert(stations, moved)
    assert not created
    assert stations[0]["x"] == 600.0

    stations = station_core.remove(stations, "all")
    assert stations == []
    with pytest.raises(ValueError):
        station_core.remove(stations, "all")


def test_duplicate_prefix_rejected():
    second = dict(STATION, id="other", name="另一个")
    with pytest.raises(ValueError, match="前缀重复"):
        station_core.upsert([station_core.normalize(STATION)], second)


def test_merge_counts():
    base = [station_core.normalize(STATION)]
    incoming = [
        dict(STATION),  # 完全一样
        dict(STATION, id="vil", name="交易所", prefix="vil", dimension="the_end", x=655),
    ]
    merged, stats = station_core.merge(base, incoming)
    assert len(merged) == 2
    assert stats == {"added": 1, "updated": 0, "duplicated": 1}


def test_parse_stops_json():
    raw = json.dumps(
        {
            "全物品": {
                "coordinate": {"x": 567, "y": 102, "z": -595},
                "dimension": "minecraft:overworld",
                "prefix": "all",
            }
        },
        ensure_ascii=False,
    )
    parsed = parse(raw)
    assert parsed["format"] == "json"
    assert parsed["stations"][0]["prefix"] == "all"
    assert parsed["stations"][0]["x"] == 567


def test_parse_stops_json_unknown_dimension_falls_back():
    raw = json.dumps(
        {"站": {"coordinate": {"x": 1, "y": 2, "z": 3}, "dimension": "moon", "prefix": "m"}},
        ensure_ascii=False,
    )
    parsed = parse(raw, default_dimension="the_end")
    assert parsed["stations"][0]["dimension"] == "the_end"
    assert parsed["warnings"]


def test_parse_command_lines():
    text = (
        "# 注释\n"
        "永夜岛工业区·混凝土工厂 136 48 8 end_concrete\n"
        "重溟洋工业区·全物品 567 102 -595 ov_storage\n"
        "只有名字的站点\n"
    )
    parsed = parse(text)
    assert parsed["format"] == "lines"
    assert [item["prefix"] for item in parsed["stations"]] == ["concrete", "storage"]
    assert parsed["stations"][0]["dimension"] == "the_end"
    assert parsed["stations"][1]["dimension"] == "overworld"
    assert parsed["stations"][0]["name"] == "永夜岛工业区·混凝土工厂"
    assert len(parsed["skipped"]) == 1


def test_parse_new_format_json():
    raw = json.dumps(
        {
            "version": 1,
            "stations": [
                {
                    "name": "交易所",
                    "prefix": "vil",
                    "dimension": "the_end",
                    "x": 655,
                    "y": 48,
                    "z": -180,
                }
            ],
        },
        ensure_ascii=False,
    )
    parsed = parse(raw)
    assert parsed["stations"][0]["name"] == "交易所"


def test_parse_line_with_explicit_dimension():
    text = "测试站点 136 48 8 con the_end\n"
    parsed = parse(text)
    station = parsed["stations"][0]
    assert station["name"] == "测试站点"
    assert station["prefix"] == "con"
    assert station["dimension"] == "the_end"
    assert station["z"] == 8


def test_parse_bad_json():
    with pytest.raises(ValueError, match="JSON"):
        parse("{not json}")


def test_parse_rejects_empty():
    with pytest.raises(ValueError, match="为空"):
        parse("   ")
