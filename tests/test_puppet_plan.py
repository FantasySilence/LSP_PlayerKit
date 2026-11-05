# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 假人搬货：盒数/批次/命令  #
# =================================== #

import pytest

from lspkit.tools.puppet.core.plan import (
    build_plan,
    format_coord,
    kill_command,
    player_count,
    spawn_command,
    split_batches,
)

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
    assert format_coord(567) == "567"
    assert format_coord(567.0) == "567"
    assert format_coord(-595.5) == "-595.5"
    assert format_coord(-31.9375) == "-31.9375"
    assert format_coord(0.00001) == "0"


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
    assert player_count(boxes, per_bot) == expected


def test_split_batches():
    assert split_batches(7, 24) == [{"index": 1, "from": 1, "to": 7, "count": 7}]
    assert split_batches(24, 24)[0]["count"] == 24
    batches = split_batches(25, 24)
    assert [b["count"] for b in batches] == [24, 1]
    assert batches[1] == {"index": 2, "from": 25, "to": 25, "count": 1}
    assert split_batches(0, 24) == []


def test_commands():
    assert spawn_command("bot_all_vil_1", ORIGIN) == (
        "/execute in minecraft:overworld run player bot_all_vil_1 "
        "spawn at 567 102 -595"
    )
    assert kill_command("bot_all_vil_1") == "/player bot_all_vil_1 kill"


def test_plan_spawn_at_origin():
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
    plan = build_plan(ORIGIN, DEST, 36, operation="spawn_at_dest")
    assert plan["bots"] == 1
    assert "minecraft:the_end" in plan["commands"][0]["text"]
    assert "spawn at 655 48 -180" in plan["commands"][0]["text"]


def test_plan_multi_wave():
    plan = build_plan(ORIGIN, DEST, 865)
    assert plan["bots"] == 25
    assert plan["waves"] == 2
    assert [batch["count"] for batch in plan["batches"]] == [24, 1]
    assert plan["commands"][23]["batch"] == 1
    assert plan["commands"][24]["batch"] == 2


def test_plan_custom_counts():
    plan = build_plan(ORIGIN, DEST, 10, boxes_per_bot=4, bots_per_batch=2)
    assert plan["bots"] == 3
    assert plan["waves"] == 2
    assert [batch["count"] for batch in plan["batches"]] == [2, 1]


def test_plan_name_template():
    plan = build_plan(ORIGIN, DEST, 1, name_template="{origin}_{dest}_{index}")
    assert plan["names"] == ["all_vil_1"]


def test_plan_rejects_bad_template():
    with pytest.raises(ValueError, match="必须包含"):
        build_plan(ORIGIN, DEST, 1, name_template="bot_{origin}_{dest}")
    with pytest.raises(ValueError, match="不认识"):
        build_plan(ORIGIN, DEST, 1, name_template="bot_{origin}_{nope}_{index}")


def test_plan_rejects_too_long_name():
    origin = dict(ORIGIN, prefix="averylongprefix")
    dest = dict(DEST, prefix="anotherlongprefix")
    with pytest.raises(ValueError, match="16"):
        build_plan(origin, dest, 1)


def test_plan_rejects_bad_input():
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
