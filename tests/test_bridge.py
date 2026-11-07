# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: API 契约测试             #
# =================================== #
# 测试层：Api 门面与 pearl / border / material 的 actions 契约（公开 JSON 信封）。
# 策略：每个用例用临时数据目录和真实 Registry，走 api.tool_call / settings_*；
# 文件对话框用假 window 替换，不启动 WebView、不碰真实用户配置。

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
    """为本文件提供独立 Api；同名 fixture 优先于 conftest 的版本.

    每个测试新建临时目录与 Store，保证设置 / 站点 / 台账互不串味；
    yield 让用例结束后临时对象自然回收。
    """
    root = Path(tempfile.mkdtemp(prefix="lspkit-test-"))
    # 临时目录 + 真实 Registry：验证的是 Api 与工具的装配，而不是 mock。
    registry = build_registry()
    location = Location(path=root, source="default", writable=True)
    runtime = Runtime(location=location, store=Store(root), webview_dir=root / "webview")
    # webview_dir 也放在临时目录，避免任何缓存写到仓库或用户目录。
    yield Api(runtime, registry)


def test_app_state_lists_tools(api):
    """验证首屏工具清单的顺序与完整性.

    输入：空数据目录下的 api.app_state()。
    期望：五个工具按注册顺序 pearl / border / material / puppet / slime 返回。
    """
    result = api.app_state()
    assert result["ok"] is True
    ids = [tool["id"] for tool in result["data"]["tools"]]
    # 顺序即侧边栏顺序；新增工具或调整顺序时这里要同步更新。
    assert ids == ["pearl", "border", "material", "puppet", "slime"]


def test_pearl_calculate_and_decode(api):
    """验证珍珠炮 calculate 与 decode 的联动.

    输入：旧默认炮口 (-31.9375, -8.0625)、目标 (5000, 5000)、maxTnt=400、平射。
    期望：返回合法方向且至少一行；取第一行解码后 blueText 以 "N =" 开头。
    """
    # maxTnt 是蓝 / 红各自的上限，不是两者之和（与旧版口径一致）。
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
    # decompose 的文本格式是 "数量 = 各档相加"，因此只需确认前缀。
    assert decode["data"]["blueText"].startswith(f"{row['blue']} =")


def test_border_calculate_and_decode(api):
    """验证边境炮 calculate 与 decode 的联动.

    输入：旧默认炮口 (9996.24,256,9999.24)、目标 (0,128,0)、预计飞行时间 400gt。
    期望：从 400gt 起返回 100 行候选；首行解码文本包含固定的「3个TNT」前缀。
    """
    result = api.tool_call(
        "border", "calculate",
        {"origin": {"x": 9996.24, "y": 256, "z": 9999.24},
         "target": {"x": 0, "y": 128, "z": 0}, "time": 400},
    )
    assert result["ok"] is True, result
    rows = result["data"]["rows"]
    assert len(rows) == 100
    # 这里 400gt 的输入没有奇异 tick，因此正好是 MAX_ROWS=100 行（每行 +1gt）。
    row = rows[0]
    decode = api.tool_call(
        "border", "decode",
        {"tnt": [row["t1"], row["t2"], row["t3"]],
         "motion": {"x": row["mx"], "y": row["my"], "z": row["mz"]},
         "dirLabel": row["dirLabel"],
         "origin": {"x": 9996.24, "y": 256, "z": 9999.24}},
    )
    assert decode["ok"] is True, decode
    # 解码文本的标题固定为「3个TNT对应的配置信息为：」。
    assert "3个TNT" in decode["data"]["text"]


def test_invalid_input_returns_envelope_not_exception(api):
    """验证非法输入以失败信封返回，而不是抛异常.

    输入：目标 x 传字符串 "abc"；以及不存在的工具 id "nope"。
    期望：ok=False，错误码分别为 INVALID_INPUT 与 UNKNOWN_TOOL。
    """
    result = api.tool_call("pearl", "calculate", {"target": {"x": "abc", "z": 0}})
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"
    # 前端只按 envelope 的 ok/code 分支，后端不能把 traceback 漏到 JS 层。

    unknown = api.tool_call("nope", "calculate", {})
    assert unknown["ok"] is False
    assert unknown["error"]["code"] == "UNKNOWN_TOOL"


def test_settings_roundtrip_and_validation(api):
    """验证设置保存、非法值拒绝与恢复默认.

    输入：读取 pearl 设置，改 maxTnt=1234 保存；再保存 -1；最后 reset。
    期望：1234 能读回；-1 报 INVALID_SETTING；重置后回到出厂值 3640。
    """
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
    # 3640 是 pearl 出厂 maxTnt，重置必须回到这个旧版默认值。
    assert reset["data"]["maxTnt"] == 3640


def test_pearl_panel_defaults_roundtrip(api):
    """验证珍珠炮面板默认值与保存回读.

    输入：默认设置；再保存 targetX/Z=10000、fireMode=eject。
    期望：默认 target 为 (0,0)、fireMode=flat；保存后能读回新值。
    """
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
    """验证 storage_info 至少带路径与来源.

    输入：临时数据目录的 api.storage_info()。
    期望：data 中含 path 与 source 两个键（前端存储面板依赖）。
    """
    info = api.storage_info()["data"]
    assert "path" in info and "source" in info


class _FakeWindow:
    """替代 pywebview 窗口：create_file_dialog 固定返回预置路径，不弹真实对话框."""
    def __init__(self, path: Path) -> None:
        self._path = path

    def create_file_dialog(self, *args, **kwargs):
        return [str(self._path)]


def test_import_wrong_tool_file_is_rejected(api, tmp_path):
    """验证把边境炮配置当珍珠炮导入时会被拒绝.

    输入：含 border 旧键（default_x_init 等）的 JSON，tool 传 pearl。
    期望：ok=False，错误码 WRONG_TOOL_FILE（没有任何 pearl schema 字段）。
    """
    # 这些键是边境炮旧配置的字段名，pearl schema 一个都不认识。
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
    """验证旧版珍珠炮 JSON 能迁移成新设置.

    输入：旧键 IS_EJECTION_AVAILABLE / MAX_TNT / XZ_INIT_POSITION 等。
    期望：migrated=True，maxTnt=1234，originX=1.5（旧坐标结构被展平）。
    """
    # 迁移由 tools/pearl/legacy.py 完成；这里只断言几个有代表性的字段。
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
    """验证材料清单解析、去重合并与换算.

    输入：含重复石头、带逗号数量、注释行与无法解析行的文本。
    期望：2 种材料、单盒 1728、共需 60 盒、跳过 1 行；石头合并为 101000。
    """
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

    # kinds 只统计解析成功的材料；注释行被忽略，不进入 skipped 计数。
    assert data["totals"]["kinds"] == 2
    assert data["totals"]["perBox"] == 1728
    # 60 = 石头 58 个整盒 + 1 个零头盒 + 羊毛 1 个整盒（零头按材料各占一盒）。
    assert data["totals"]["boxesNeeded"] == 60
    assert data["skipped"] == 1
    # 行号从 1 开始；第 5 行是 "unparsed line"，第 4 行是注释。
    assert data["warnings"][0]["line"] == 5

    stone = next(row for row in data["items"] if row["name"] == "minecraft:stone")
    # 101000 / 1728 = 58 盒余 776 个；776 / 64 = 12 组余 8 个。
    assert (stone["count"], stone["shulkers"], stone["stacks"], stone["items"]) == (
        101000,
        58,
        12,
        8,
    )

    wool = next(row for row in data["items"] if row["name"] == "minecraft:white_wool")
    # 1728 正好是一整盒（64 × 27），因此 1 盒 0 组 0 个。
    assert (wool["shulkers"], wool["stacks"], wool["items"]) == (1, 0, 0)


def test_material_rejects_empty_input(api):
    """验证材料换算对空输入与无数字输入的错误码.

    输入：只有空白字符的 text；以及没有数量的 "no numbers here"。
    期望：前者 INVALID_INPUT（文本为空），后者 NO_ENTRIES（解析不出条目）。
    """
    blank = api.tool_call("material", "convert", {"text": "   \n\n"})
    assert blank["ok"] is False
    assert blank["error"]["code"] == "INVALID_INPUT"

    nothing = api.tool_call("material", "convert", {"text": "no numbers here"})
    assert nothing["ok"] is False
    assert nothing["error"]["code"] == "NO_ENTRIES"


def test_material_merges_multiple_lists(api):
    """验证多份清单按名称跨文件求和.

    输入：a.csv 铁锭 10 / 木棍 5；b.csv 铁锭 6 / 苹果 2。
    期望：铁锭 16、木棍 5、苹果 2；sources 摘要按文件分别统计。
    """
    texts = [
        {"name": "a.csv", "text": "铁锭 10\n木棍 5"},
        {"name": "b.csv", "text": "铁锭 6\n苹果 2"},
    ]
    result = api.tool_call("material", "convert", {"texts": texts})
    assert result["ok"] is True, result
    data = result["data"]

    counts = {row["name"]: row["count"] for row in data["items"]}
    # a.csv 的 items=15 是 10+5；b.csv 的 items=8 是 6+2。
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
    """验证多清单入参的空列表与空内容校验.

    输入：texts=[]；以及只有无数字文本的单份清单。
    期望：分别是 INVALID_INPUT 与 NO_ENTRIES。
    """
    empty = api.tool_call("material", "convert", {"texts": []})
    assert empty["ok"] is False
    assert empty["error"]["code"] == "INVALID_INPUT"

    unparsed = api.tool_call(
        "material", "convert", {"texts": [{"name": "x.csv", "text": "no numbers"}]}
    )
    assert unparsed["ok"] is False
    assert unparsed["error"]["code"] == "NO_ENTRIES"


def test_material_settings_change_capacity(api):
    """验证改设置后单盒容量与换算结果随之变化.

    输入：默认值（64 堆叠、27 格）；改成 stackSize=16、shulkerSlots=1。
    期望：perBox=16，石头 100 个 = 6 盒余 4 个，boxesNeeded=7；reset 回默认。
    """
    current = api.settings_get("material")["data"]
    assert current == {"stackSize": "64", "shulkerSlots": 27, "exportDir": ""}

    saved = api.settings_save("material", {**current, "stackSize": "16", "shulkerSlots": 1})
    assert saved["ok"] is True

    result = api.tool_call("material", "convert", {"text": "minecraft:stone 100"})
    row = result["data"]["items"][0]
    assert result["data"]["totals"]["perBox"] == 16
    # perBox = 16 × 1 = 16；6 个整盒 + 1 个零头盒 = 7（偏保守的上界）。
    assert (row["shulkers"], row["stacks"], row["items"]) == (6, 0, 4)
    assert result["data"]["totals"]["boxesNeeded"] == 7

    reset = api.settings_reset("material")
    assert reset["data"] == {"stackSize": "64", "shulkerSlots": 27, "exportDir": ""}


def test_material_parses_litematica_csv(api):
    """验证解析 Litematica 导出的材料 CSV.

    输入：表头 Item/Total/Missing/Available 与三行材料。
    期望：3 种、总数 6040（4766+1219+55），perBox=1728；数量取 Total 列。
    """
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

    # 名称保持清单原样；Missing / Available 列不参与统计。
    # 名称与导入清单完全一致，数量取 Total 列而不是 Available 列
    assert [row["name"] for row in data["items"]] == ["白色染色玻璃", "侦测器", "末影箱"]
    assert [row["count"] for row in data["items"]] == [4766, 1219, 55]


def test_material_unstackable_uses_items_only(api):
    """验证不可堆叠材料只按「个」计算.

    输入：stackSize="1" 时换算 100 个铁砧。
    期望：perBox=27，铁砧 3 盒余 19 个，stacks=0。
    """
    saved = api.settings_save("material", {"stackSize": "1", "shulkerSlots": 27})
    assert saved["ok"] is True

    text = '"Item","Total"\n"铁砧",100'
    result = api.tool_call("material", "convert", {"text": text})
    row = result["data"]["items"][0]

    assert result["data"]["totals"]["perBox"] == 27
    assert row["stack"] == 1
    assert (row["shulkers"], row["stacks"], row["items"]) == (3, 0, 19)


def test_material_per_item_stack_override(api):
    """验证按材料单独覆盖堆叠数.

    输入：铁砧覆盖为 1、石块沿用 64，各 100 个。
    期望：铁砧 3 盒余 19；石块 1 组余 36（0 整盒）。
    """
    text = '"Item","Total"\n"铁砧",100\n"石块",100'
    result = api.tool_call("material", "convert", {"text": text, "stacks": {"铁砧": "1"}})
    assert result["ok"] is True, result

    rows = {row["name"]: row for row in result["data"]["items"]}
    # stacks 的键是材料显示名（「铁砧」/「石块」），值只能是 "64" / "16" / "1"。
    assert rows["铁砧"]["stack"] == 1
    assert (rows["铁砧"]["shulkers"], rows["铁砧"]["stacks"], rows["铁砧"]["items"]) == (3, 0, 19)
    assert rows["石块"]["stack"] == 64
    assert (rows["石块"]["shulkers"], rows["石块"]["stacks"], rows["石块"]["items"]) == (0, 1, 36)


def test_material_rejects_bad_stack_override(api):
    """验证非法的单材料堆叠数会被拒绝.

    输入：stacks={"铁砧": "32"}。
    期望：ok=False，INVALID_INPUT（只允许 64 / 16 / 1）。
    """
    result = api.tool_call(
        "material",
        "convert",
        {"text": '"Item","Total"\n"铁砧",10', "stacks": {"铁砧": "32"}},
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


def test_material_ignore_excludes_from_result(api):
    """验证忽略名单不参与换算，但仍在 ignoredItems 中展示.

    输入：石头 1000、木棍 100、铁砧 100，忽略木棍。
    期望：结果只剩石头与铁砧，总数 1100；木棍出现在 ignoredItems。
    """
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
    """验证装填方案的盒数等于理论下界且不超容量.

    输入：石头 1000、木棍 100、铁砧 100（默认 64×27 容量）。
    期望：capacity=27，盒数=ceil(slots/容量)，每盒用量不超容量，且总数守恒。
    """
    text = '"Item","Total"\n"石头",1000\n"木棍",100\n"铁砧",100'
    result = api.tool_call("material", "pack", {"text": text})
    assert result["ok"] is True, result
    data = result["data"]

    slots = data["totals"]["slots"]
    capacity = data["totals"]["capacity"]
    assert capacity == 27
    assert data["totals"]["boxes"] == -(-slots // capacity)
    # ceil(slots / capacity) 是任何方案的下界，plan 逐盒装满正好达到它。
    assert sum(box["used"] for box in data["boxes"]) == slots
    assert all(box["used"] <= capacity for box in data["boxes"])

    converted = api.tool_call("material", "convert", {"text": text})["data"]
    packed = sum(entry["count"] for box in data["boxes"] for entry in box["entries"])
    assert packed == converted["totals"]["count"]


def test_material_packing_unstackable(api):
    """验证不可堆叠材料的装填方案.

    输入：铁砧 1000 个、堆叠数覆盖为 1（每格 1 个）。
    期望：每盒 27 格，需 38 盒（ceil(1000/27)），每盒只有一条材料记录。
    """
    text = '"Item","Total"\n"铁砧",1000'
    result = api.tool_call("material", "pack", {"text": text, "stacks": {"铁砧": "1"}})
    assert result["ok"] is True, result
    data = result["data"]

    assert data["totals"]["capacity"] == 27
    assert data["totals"]["boxes"] == 38
    assert sum(box["used"] for box in data["boxes"]) == 1000
    assert all(len(box["entries"]) == 1 for box in data["boxes"])


class _DialogWindow:
    """记录 create_file_dialog 的 kwargs 并返回 None，用来验证保存时传的目录/文件名."""
    def __init__(self) -> None:
        self.kwargs: dict | None = None

    def create_file_dialog(self, *args, **kwargs):
        self.kwargs = kwargs
        return None


def test_export_dir_defaults_to_data_output(tmp_path):
    """验证导出目录的默认值与自定义值.

    输入：directory="" 与一个自定义路径。
    期望：空值落到 <数据目录>/output 并自动创建；自定义路径原样返回且创建。
    """
    target = _export_dir("", tmp_path)
    assert target == tmp_path / "output"
    assert target.is_dir()

    custom = tmp_path / "custom"
    assert _export_dir(str(custom), tmp_path) == custom
    assert custom.is_dir()


def test_file_save_text_uses_export_dir(api):
    """验证保存文本时把导出目录与文件名传给文件对话框.

    输入：filename="plan.csv"、directory=""；再用自定义目录调用一次。
    期望：save_filename 原样传递；空目录落到 output，自定义目录原样使用。
    """
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
    """验证多选文件读取与单选文件的 allow_multiple 标记.

    输入：假窗口依次返回 a.csv、b.csv。
    期望：files 顺序与内容正确；多选时 allow_multiple=True，单选时 False。
    """
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
    """验证连续满装单材料盒会被合并成一组.

    输入：石头 5184 个（= 3 × 1728，正好 3 个满盒）。
    期望：3 盒、1 组；组标记 merged=True，from/to=1..3，used=81 格。
    """
    result = api.tool_call("material", "pack", {"text": "minecraft:stone 5184"})
    assert result["ok"] is True, result
    data = result["data"]

    assert data["totals"]["boxes"] == 3
    groups = data["groups"]
    assert len(groups) == 1
    assert groups[0]["merged"] is True
    assert (groups[0]["from"], groups[0]["to"], groups[0]["boxes"]) == (1, 3, 3)
    assert groups[0]["used"] == 81
    # 81 = 3 盒 × 27 格；每组 entries 只有一条合并后的石头记录。

    entry = groups[0]["entries"][0]
    assert entry["name"] == "minecraft:stone"
    assert entry["slots"] == 81
    assert entry["count"] == 5184


def test_material_packing_keeps_mixed_and_partial_boxes(api):
    """验证混装盒与未装满盒不会被合并.

    输入：石头 1728（满盒）+ 泥土 1（第二盒只占 1 格）。
    期望：两组都 merged=False，from 分别为 1、2，第二组 used 小于容量。
    """
    text = "minecraft:stone 1728\nminecraft:dirt 1"
    result = api.tool_call("material", "pack", {"text": text})
    assert result["ok"] is True, result

    groups = result["data"]["groups"]
    assert [group["merged"] for group in groups] == [False, False]
    assert [group["from"] for group in groups] == [1, 2]
    assert groups[1]["used"] < groups[1]["capacity"]

def test_material_accepts_preparsed_sources(api):
    """验证已解析条目（如 .litematic）与文本来源可以混用.

    输入：a.litematic 的 entries（石头 10、泥土 5）+ b.csv 文本（石头 3）。
    期望：石头 13、泥土 5；sources 摘要按来源分别统计。
    """
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
    """验证所有来源都没有有效条目时报 INVALID_INPUT.

    输入：sources=[{name:"x", entries:[]}]。
    期望：ok=False，INVALID_INPUT（空 entries 会被跳过，最终没有来源）。
    """
    result = api.tool_call(
        "material", "convert", {"sources": [{"name": "x", "entries": []}]}
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"

def test_material_localizes_preparsed_entries(api):
    """验证带 id 的已解析条目会按 locale 重新取名.

    输入：id=minecraft:stone、name="ignored"、locale="en"。
    期望：结果名是 "Stone"，说明 id 优先于传入的 name。
    """
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
    """验证打开说明文件时按语言选择 PDF 并调用系统打开.

    输入：locale zh_CN / en；monkeypatch os.startfile 记录路径。
    期望：依次打开 README.pdf 与 README.en.pdf；非 Windows 跳过（无 startfile）。
    """
    if not hasattr(os, "startfile"):
        # os.startfile 只有 Windows 提供；其它平台无法验证「交给系统打开」这一步。
        pytest.skip("startfile 仅 Windows 提供")

    import lspkit.api as api_module

    opened: list = []
    monkeypatch.setattr(api_module.os, "startfile", lambda path: opened.append(path))

    assert api.open_manual("zh_CN")["ok"] is True
    assert api.open_manual("en")["ok"] is True
    assert opened[0].endswith("README.pdf")
    assert opened[1].endswith("README.en.pdf")


def test_open_manual_reports_missing_file(api, monkeypatch, tmp_path):
    """验证说明文件缺失时返回 NOT_FOUND.

    输入：把 resource_dir 指到空临时目录后调用 open_manual("zh_CN")。
    期望：ok=False，错误码 NOT_FOUND（不抛异常）。
    """
    import lspkit.api as api_module

    monkeypatch.setattr(api_module, "resource_dir", lambda: tmp_path)
    result = api.open_manual("zh_CN")
    assert result["ok"] is False
    assert result["error"]["code"] == "NOT_FOUND"
