# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 假人搬货：站点与导入     #
# =================================== #
# 测试层：puppet.core.stations 的站点规整/增删合并，以及 legacy 导入解析。
# 策略：纯函数 + 错误消息断言；不读写站点文件，覆盖旧格式与新格式的兼容。

import json

import pytest

from lspkit.tools.puppet.core import stations as station_core
from lspkit.tools.puppet.legacy import parse

# 代表性站点：名称含「工业区·全物品」旧格式，normalize 会拆成 group + name。
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
    """验证合法站点被规整成固定字段.

    输入：完整 STATION（坐标 567 是整数）。
    期望：x 变成 float 567.0，维度保留，缺省 note 补成空串。
    """
    station = station_core.normalize(STATION)
    assert station["x"] == 567.0
    assert station["dimension"] == "overworld"
    assert station["note"] == ""


# 每个 patch 只改 STATION 的一个字段，message 是期望的报错关键词。
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
    """验证各类非法站点字段被拒绝并给出可读原因.

    输入：空名称、中文前缀、13 位前缀、moon 维度、非数字 X、超界 Y、超界 X。
    期望：ValueError，消息分别命中对应关键词（前缀上限 12、Y 上限 2048 等）。
    """
    with pytest.raises(ValueError, match=message):
        # match 用正则子串匹配；「范围」对应世界边界 ±30,000,000。
        station_core.normalize({**STATION, **patch})


def test_normalize_splits_legacy_name_into_group():
    """验证旧命名「工业区·地点」自动拆成分组与短名称.

    输入：name="重溟洋工业区·全物品"，未显式给 group。
    期望：group="重溟洋工业区"，name="全物品"。
    """
    station = station_core.normalize(STATION)
    assert station["group"] == "重溟洋工业区"
    assert station["name"] == "全物品"


def test_normalize_keeps_explicit_group():
    """验证显式分组优先于名称拆分.

    输入：name="仓库"、group="主城"。
    期望：两者原样保留，不会被「·」规则改写。
    """
    station = station_core.normalize({**STATION, "name": "仓库", "group": "主城"})
    assert station["group"] == "主城"
    assert station["name"] == "仓库"


def test_normalize_rejects_group_with_space():
    """验证分组 tag 不允许空白字符.

    输入：group="工业 区"。
    期望：ValueError，消息含「分组」。
    """
    with pytest.raises(ValueError, match="分组"):
        station_core.normalize({**STATION, "name": "仓库", "group": "工业 区"})


def test_parse_line_with_group():
    """验证 7 列文本（名称 x y z 前缀 分组 维度）的解析.

    输入："仓库 1 2 3 wh 主城 the_end"。
    期望：name=仓库、group=主城、prefix=wh、dimension=the_end。
    """
    parsed = parse("仓库 1 2 3 wh 主城 the_end\n")
    station = parsed["stations"][0]
    assert station["name"] == "仓库"
    assert station["group"] == "主城"
    assert station["prefix"] == "wh"
    assert station["dimension"] == "the_end"


def test_normalize_truncates_long_note():
    """验证超长备注被截断而不是报错.

    输入：note 为 100 个 "x"。
    期望：长度截到 60（NOTE_MAX），保存不被拒绝。
    """
    station = station_core.normalize({**STATION, "note": "x" * 100})
    # 60 是 NOTE_MAX：备注只做展示，超长直接截断，不报错。
    assert len(station["note"]) == 60


def test_upsert_and_remove():
    """验证站点新增/更新/删除的返回值.

    输入：空表 -> 新增 STATION -> 同 id 改 x=600 -> 删除 -> 再删一次。
    期望：created 依次为 True/False；更新后 x=600.0；删除后为空；再删抛 ValueError。
    """
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
    """验证不同 id 但相同前缀的站点被拒绝.

    输入：已有 all，再 upsert id=other、前缀仍为 all。
    期望：ValueError，消息含「前缀重复」（同前缀会生成同名假人）。
    """
    second = dict(STATION, id="other", name="另一个")
    with pytest.raises(ValueError, match="前缀重复"):
        station_core.upsert([station_core.normalize(STATION)], second)


def test_merge_counts():
    """验证合并统计 added/updated/duplicated.

    输入：已有 all；导入完全相同的 all，以及 id/prefix 都不同的 vil。
    期望：结果 2 条；统计 added=1、updated=0、duplicated=1。
    """
    base = [station_core.normalize(STATION)]
    # 完全相同的条目只计 duplicated，不覆盖；vil 的 id/prefix 都新，计 added。
    incoming = [
        dict(STATION),  # 完全一样
        dict(STATION, id="vil", name="交易所", prefix="vil", dimension="the_end", x=655),
    ]
    merged, stats = station_core.merge(base, incoming)
    assert len(merged) == 2
    assert stats == {"added": 1, "updated": 0, "duplicated": 1}


def test_parse_stops_json():
    """验证旧版 stops.json（对象键=站点名）的解析.

    输入：{"全物品": {coordinate, dimension: minecraft:overworld, prefix: all}}。
    期望：format="json"；prefix=all；x=567；维度去掉 minecraft: 前缀。
    """
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
    """验证不认识的维度回落成默认值并记 warning.

    输入：dimension="moon"，default_dimension="the_end"。
    期望：站点维度为 the_end；warnings 非空。
    """
    raw = json.dumps(
        {"站": {"coordinate": {"x": 1, "y": 2, "z": 3}, "dimension": "moon", "prefix": "m"}},
        ensure_ascii=False,
    )
    parsed = parse(raw, default_dimension="the_end")
    assert parsed["stations"][0]["dimension"] == "the_end"
    assert parsed["warnings"]


def test_parse_command_lines():
    """验证纯文本站点表的列数识别与注释/坏行处理.

    输入：注释行、end_concrete / ov_storage 两条 5 列行、一条只有名字的行。
    期望：format="lines"；两条站点前缀为 concrete/storage，维度分别为 the_end/overworld；
          只有名字的行进入 skipped（长度 1）。
    """
    text = (
        "# 注释\n"
        "永夜岛工业区·混凝土工厂 136 48 8 end_concrete\n"
        "重溟洋工业区·全物品 567 102 -595 ov_storage\n"
        "只有名字的站点\n"
    )
    parsed = parse(text)
    # 前缀里的 end_ / ov_ 会被剥离并折算成维度；名称里的「·」原样保留。
    assert parsed["format"] == "lines"
    assert [item["prefix"] for item in parsed["stations"]] == ["concrete", "storage"]
    assert parsed["stations"][0]["dimension"] == "the_end"
    assert parsed["stations"][1]["dimension"] == "overworld"
    assert parsed["stations"][0]["name"] == "永夜岛工业区·混凝土工厂"
    assert len(parsed["skipped"]) == 1


def test_parse_new_format_json():
    """验证新版 {"version":1,"stations":[...]} 结构的解析.

    输入：一条 name=交易所 的站点。
    期望：格式识别为 json，站点名读回。
    """
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
    """验证 6 列文本（名称 x y z 前缀 维度）的解析.

    输入："测试站点 136 48 8 con the_end"。
    期望：prefix=con、dimension=the_end、z=8（显式维度优先于默认值）。
    """
    text = "测试站点 136 48 8 con the_end\n"
    parsed = parse(text)
    station = parsed["stations"][0]
    assert station["name"] == "测试站点"
    assert station["prefix"] == "con"
    assert station["dimension"] == "the_end"
    assert station["z"] == 8


def test_parse_bad_json():
    """验证坏 JSON 抛 ValueError 且消息带 JSON.

    输入："{not json}"。
    期望：ValueError，match="JSON"。
    """
    with pytest.raises(ValueError, match="JSON"):
        parse("{not json}")


def test_parse_rejects_empty():
    """验证空/纯空白导入被拒绝.

    输入："   "。
    期望：ValueError，消息含「为空」。
    """
    with pytest.raises(ValueError, match="为空"):
        parse("   ")
