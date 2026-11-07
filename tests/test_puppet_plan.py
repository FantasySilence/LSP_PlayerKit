# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 假人搬货：盒数/批次/命令  #
# =================================== #
# 测试层：puppet.core.plan / naming 的纯函数（盒数→人数→批次→命令文本）。
# 策略：边界值 + 精确字符串断言；不依赖设置存储、不执行命令。

import pytest

from lspkit.tools.puppet.core.plan import (
    build_plan,
    format_coord,
    kill_command,
    player_count,
    spawn_command,
    split_batches,
)

# 两个站点只作为纯函数输入：前缀决定假人名，维度/坐标决定 spawn 命令文本。
ORIGIN = {
    "id": "all",
    "name": "重溟洋工业区·全物品",
    "prefix": "all",
    "dimension": "overworld",
    "x": 567,
    "y": 102,
    "z": -595,
}
DEST = {
    "id": "vil",
    "name": "永夜岛工业区·村民交易所",
    "prefix": "vil",
    "dimension": "the_end",
    "x": 655,
    "y": 48,
    "z": -180,
}


def test_format_coord():
    """验证坐标文本的取整与去尾零规则.

    输入：整数、整数值浮点、负小数、四位小数、极小正数。
    期望：整数不带 .0；-595.5 / -31.9375 保留；0.00001 经 4 位小数后变 "0"。
    """
    assert format_coord(567) == "567"
    assert format_coord(567.0) == "567"
    assert format_coord(-595.5) == "-595.5"
    assert format_coord(-31.9375) == "-31.9375"
    # 1e-5 小于 4 位小数的分辨率，格式化后是 0.0000，再去尾零就是 "0"。
    assert format_coord(0.00001) == "0"


# 每假人 36 盒；覆盖 0/1、36 的整数倍、以及 250/863/864/865 这些取整边界。
@pytest.mark.parametrize(
    ("boxes", "per_bot", "expected"),
    [
        (0, 36, 0),
        (1, 36, 1),
        (35, 36, 1),
        (36, 36, 1),
        (37, 36, 2),
        (72, 36, 2),
        (250, 36, 7),
        (863, 36, 24),
        (864, 36, 24),
        (865, 36, 25),
    ],
)
def test_player_count(boxes, per_bot, expected):
    """验证「盒数 → 假人数」的向上取整边界.

    输入：每假人 36 盒，盒数取 0/1/35/36/37/72/250/863/864/865。
    期望：不足一人份也占 1 人；36 的倍数不额外加人；250->7、865->25。
    """
    assert player_count(boxes, per_bot) == expected


def test_split_batches():
    """验证按 24 人/批切分批次.

    输入：7、24、25、0 人。
    期望：7 人 1 批；24 人 1 批；25 人切成 24+1 两批且第二批 from=to=25；0 人无批次。
    """
    assert split_batches(7, 24) == [{"index": 1, "from": 1, "to": 7, "count": 7}]
    assert split_batches(24, 24)[0]["count"] == 24
    batches = split_batches(25, 24)
    assert [b["count"] for b in batches] == [24, 1]
    assert batches[1] == {"index": 2, "from": 25, "to": 25, "count": 1}
    assert split_batches(0, 24) == []


def test_commands():
    """验证 spawn / kill 命令的精确文本.

    输入：假人名 bot_all_vil_1，站点坐标 (567,102,-595)、维度 overworld。
    期望：spawn 带 minecraft: 命名空间与 "spawn at 567 102 -595"；kill 为 /player ... kill。
    """
    assert spawn_command("bot_all_vil_1", ORIGIN) == (
        "/execute in minecraft:overworld run player bot_all_vil_1 "
        "spawn at 567 102 -595"
    )
    assert kill_command("bot_all_vil_1") == "/player bot_all_vil_1 kill"


def test_plan_spawn_at_origin():
    """验证默认「在始发站生成」的运单结构.

    输入：两站、250 盒、operation 缺省（spawn_at_origin）。
    期望：7 人、1 波、7 条 spawn + 7 条 kill；名字从 bot_all_vil_1 到 _7；
          spawn 命令使用始发站维度与坐标。
    """
    plan = build_plan(ORIGIN, DEST, 250)
    assert plan["bots"] == 7
    assert plan["waves"] == 1
    assert len(plan["commands"]) == 7
    assert len(plan["killCommands"]) == 7
    assert plan["names"][0] == "bot_all_vil_1"
    assert plan["names"][-1] == "bot_all_vil_7"
    assert "minecraft:overworld" in plan["commands"][0]["text"]
    assert "spawn at 567 102 -595" in plan["commands"][0]["text"]
    assert plan["commands"][0]["phase"] == "spawn"
    assert plan["killCommands"][0]["phase"] == "kill"


def test_plan_spawn_at_dest():
    """验证反向搬运「在目的站生成」使用目的站维度与坐标.

    输入：36 盒、operation="spawn_at_dest"。
    期望：1 人；命令使用 the_end 与目的站坐标 (655,48,-180)。
    """
    plan = build_plan(ORIGIN, DEST, 36, operation="spawn_at_dest")
    assert plan["bots"] == 1
    assert "minecraft:the_end" in plan["commands"][0]["text"]
    assert "spawn at 655 48 -180" in plan["commands"][0]["text"]


def test_plan_multi_wave():
    """验证超过 24 人时自动分批.

    输入：865 盒 -> 25 人（ceil(865/36)）。
    期望：2 波，批次人数 [24,1]；第 24 条命令属于第 1 批，第 25 条属于第 2 批。
    """
    plan = build_plan(ORIGIN, DEST, 865)
    assert plan["bots"] == 25
    assert plan["waves"] == 2
    assert [batch["count"] for batch in plan["batches"]] == [24, 1]
    assert plan["commands"][23]["batch"] == 1
    assert plan["commands"][24]["batch"] == 2


def test_plan_custom_counts():
    """验证自定义每假人盒数与每批人数.

    输入：10 盒、boxes_per_bot=4、bots_per_batch=2。
    期望：3 人（ceil(10/4)）；2 波，批次人数 [2,1]。
    """
    plan = build_plan(ORIGIN, DEST, 10, boxes_per_bot=4, bots_per_batch=2)
    assert plan["bots"] == 3
    assert plan["waves"] == 2
    assert [batch["count"] for batch in plan["batches"]] == [2, 1]


def test_plan_name_template():
    """验证自定义名字模板替换.

    输入：name_template="{origin}_{dest}_{index}"、1 盒。
    期望：名字为 "all_vil_1"（模板里没写 bot_ 前缀，输出也不补）。
    """
    plan = build_plan(ORIGIN, DEST, 1, name_template="{origin}_{dest}_{index}")
    assert plan["names"] == ["all_vil_1"]


def test_plan_rejects_bad_template():
    """验证名字模板缺少/含未知占位符时被拒绝.

    输入：没有 {index} 的模板；含 {nope} 的模板。
    期望：ValueError，消息分别包含「必须包含」与「不认识」。
    """
    with pytest.raises(ValueError, match="必须包含"):
        build_plan(ORIGIN, DEST, 1, name_template="bot_{origin}_{dest}")
    with pytest.raises(ValueError, match="不认识"):
        build_plan(ORIGIN, DEST, 1, name_template="bot_{origin}_{nope}_{index}")


def test_plan_rejects_too_long_name():
    """验证渲染后的假人名超过 16 位会被拒绝.

    输入：两个 14 字符前缀，默认模板会拼出超过 16 位的名字。
    期望：ValueError，消息含 "16"（Minecraft 用户名上限）。
    """
    origin = dict(ORIGIN, prefix="averylongprefix")
    dest = dict(DEST, prefix="anotherlongprefix")
    with pytest.raises(ValueError, match="16"):
        build_plan(origin, dest, 1)


def test_plan_rejects_bad_input():
    """验证 build_plan 对非法参数统一抛 ValueError.

    输入：盒数 0 / -5 / 1.5；始发=目的；operation="teleport"。
    期望：前三者抛 ValueError；同站点的消息含「不能是同一个」；未知操作也拒绝。
    """
    with pytest.raises(ValueError):
        build_plan(ORIGIN, DEST, 0)
    with pytest.raises(ValueError):
        build_plan(ORIGIN, DEST, -5)
    with pytest.raises(ValueError):
        build_plan(ORIGIN, DEST, 1.5)
    with pytest.raises(ValueError, match="不能是同一个"):
        build_plan(ORIGIN, dict(ORIGIN), 1)
    with pytest.raises(ValueError):
        build_plan(ORIGIN, DEST, 1, operation="teleport")
