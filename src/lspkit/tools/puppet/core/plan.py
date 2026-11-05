# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 盒数 → 人数 → 批次 → 命令（纯函数） #
# =================================== #

from __future__ import annotations

from math import ceil

from ..constants import MAX_BOXES, MAX_BOTS, OPERATIONS
from .naming import check_name, render, validate_template

DIMENSION_PREFIX = "minecraft:"


def format_coord(value: float) -> str:
    """
    坐标文本：整数不带小数点，小数最多保留 4 位并去掉尾零.
    """

    number = float(value)
    if abs(number - round(number)) < 1e-9:
        return str(int(round(number)))
    text = f"{number:.4f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def player_count(boxes: int, boxes_per_bot: int) -> int:
    """
    一个假人带 boxes_per_bot 盒，向上取整.
    """

    if boxes <= 0:
        return 0
    return int(ceil(boxes / float(boxes_per_bot)))


def split_batches(bots: int, bots_per_batch: int) -> list:
    """
    把假人按批切分，返回 [{index, from, to, count}].
    """

    result = []
    start = 1
    index = 1
    while start <= bots:
        end = min(start + bots_per_batch - 1, bots)
        result.append(
            {"index": index, "from": start, "to": end, "count": end - start + 1}
        )
        start = end + 1
        index += 1
    return result


def spawn_command(name: str, station: dict) -> str:
    """
    /execute in <维度> run player <名字> spawn at <x> <y> <z>.
    """

    dimension = DIMENSION_PREFIX + str(station["dimension"])
    x = format_coord(station["x"])
    y = format_coord(station["y"])
    z = format_coord(station["z"])
    return f"/execute in {dimension} run player {name} spawn at {x} {y} {z}"


def kill_command(name: str) -> str:
    """
    清除假人（按名字全局生效，不需要指定维度）.
    """

    return f"/player {name} kill"


def build_plan(
    origin: dict,
    dest: dict,
    boxes: int,
    operation: str = "spawn_at_origin",
    boxes_per_bot: int = 36,
    bots_per_batch: int = 24,
    name_template: str = "bot_{origin}_{dest}_{index}",
) -> dict:
    """
    生成一整张运单：假人数、批次、spawn 命令与 kill 命令.

    非法输入抛 ValueError，由动作层翻译成 AppError.
    """

    if operation not in OPERATIONS:
        raise ValueError(f"未知操作：{operation}")
    if origin["id"] == dest["id"]:
        raise ValueError("始发站和目的站不能是同一个站点")
    try:
        raw_boxes = float(boxes)
    except (TypeError, ValueError):
        raise ValueError("运输数量必须是整数盒") from None
    if abs(raw_boxes - round(raw_boxes)) > 1e-9:
        raise ValueError("运输数量必须是整数盒")
    boxes = int(round(raw_boxes))
    if boxes <= 0:
        raise ValueError("运输数量必须大于 0")
    if boxes > MAX_BOXES:
        raise ValueError(f"单张运单最多 {MAX_BOXES} 盒，请拆成多张")
    if boxes_per_bot <= 0 or bots_per_batch <= 0:
        raise ValueError("每假人盒数与每批人数必须大于 0")

    validate_template(name_template)
    bots = player_count(boxes, boxes_per_bot)
    if bots > MAX_BOTS:
        raise ValueError(f"假人数 {bots} 超过上限 {MAX_BOTS}，请拆成多张运单")

    spawn_station = origin if operation == "spawn_at_origin" else dest
    return_station = dest if operation == "spawn_at_origin" else origin

    batches = split_batches(bots, bots_per_batch)
    commands = []
    kill_commands = []
    names = []
    index = 0

    for bot in range(1, bots + 1):
        name = check_name(render(name_template, origin["prefix"], dest["prefix"], bot))
        names.append(name)
        index += 1
        commands.append(
            {
                "index": index,
                "phase": "spawn",
                "bot": bot,
                "name": name,
                "text": spawn_command(name, spawn_station),
                "batch": _batch_of(batches, bot),
            }
        )
        kill_commands.append(
            {
                "index": index,
                "phase": "kill",
                "bot": bot,
                "name": name,
                "text": kill_command(name),
                "batch": _batch_of(batches, bot),
            }
        )

    return {
        "boxes": boxes,
        "bots": bots,
        "boxesPerBot": int(boxes_per_bot),
        "botsPerBatch": int(bots_per_batch),
        "waves": len(batches),
        "batches": batches,
        "names": names,
        "commands": commands,
        "killCommands": kill_commands,
        "operation": operation,
        "spawnStation": {
            "id": spawn_station["id"],
            "name": spawn_station["name"],
            "group": spawn_station.get("group", ""),
            "dimension": spawn_station["dimension"],
            "x": spawn_station["x"],
            "y": spawn_station["y"],
            "z": spawn_station["z"],
        },
        "returnStation": {
            "id": return_station["id"],
            "name": return_station["name"],
        },
    }


def _batch_of(batches: list, bot: int) -> int:
    for batch in batches:
        if batch["from"] <= bot <= batch["to"]:
            return batch["index"]
    return 0
