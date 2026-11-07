# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 盒数 → 人数 → 批次 → 命令（纯函数） #
# =================================== #

"""
运单生成：盒数 → 人数 → 批次 → 命令文本。

业务口径（改之前先想清楚游戏里的实际影响）：
1. 人数：bots = ceil(盒数 / 每假人盒数)，默认 36 盒/人，即 ceil(盒数/36)；
2. 批次：每批最多 24 人，超出自动切批，批间等用户确认后继续；
3. 名字：按模板 bot_{origin}_{dest}_{index} 渲染，{index} 从 1 递增，
   结果必须满足 Minecraft 的 3–16 位字母数字下划线限制；
4. 命令：每个假人一条 spawn（/execute in <维度> run player ... spawn at x y z）
   加一条 kill（/player <名字> kill），spawn 与 kill 各自按批号对齐。

本模块只拼字符串，不执行、不写文件；真实发送在 platform/autoinput.py。
"""

from __future__ import annotations

from math import ceil

from ..constants import MAX_BOXES, MAX_BOTS, OPERATIONS
from .naming import check_name, render, validate_template

# 维度在命令里必须带命名空间；站点表里存的是不带前缀的短名.
DIMENSION_PREFIX = "minecraft:"


def format_coord(value: float) -> str:
    """
    坐标文本：整数不带小数点，小数最多保留 4 位并去掉尾零.

    例：12.0 → "12"、12.5 → "12.5"、12.50001 → "12.5"。
    坐标会被原样拼进命令，所以必须消除 "12.0" 这种游戏能读但不美观的写法，
    也要避免出现 "-0"（浮点负零转字符串会带负号，游戏里看着别扭）。
    """

    number = float(value)
    # 误差 <1e-9 视为整数，防止浮点运算后出现 11.999999999.
    if abs(number - round(number)) < 1e-9:
        return str(int(round(number)))
    text = f"{number:.4f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def player_count(boxes: int, boxes_per_bot: int) -> int:
    """
    一个假人带 boxes_per_bot 盒，向上取整.

    不足一人份的尾数也要占一个假人，所以用 ceil 而不是整除。
    boxes <= 0 直接返回 0（调用方在 build_plan 里已拦住非正数）。
    """

    if boxes <= 0:
        return 0
    return int(ceil(boxes / float(boxes_per_bot)))


def split_batches(bots: int, bots_per_batch: int) -> list:
    """
    把假人按批切分，返回 [{index, from, to, count}].

    index 从 1 开始；from / to 是闭区间的假人序号，count 是这一批的人数。
    例：50 人、24 人/批 → 3 批（1-24、25-48、49-50）。
    """

    result = []
    start = 1
    index = 1
    while start <= bots:
        # 最后一批不足 bots_per_batch 时截到 bots，不会越界.
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

    坐标取站点自身的 x / y / z；维度决定假人在哪个世界出现。
    """

    dimension = DIMENSION_PREFIX + str(station["dimension"])
    x = format_coord(station["x"])
    y = format_coord(station["y"])
    z = format_coord(station["z"])
    return f"/execute in {dimension} run player {name} spawn at {x} {y} {z}"


def kill_command(name: str) -> str:
    """
    清除假人（按名字全局生效，不需要指定维度）.

    用于运单结束后的收尾，或运单失败时把已生成的假人清掉。
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

    参数：
        origin / dest   已归一化的站点 dict（含 id / name / prefix / 维度 / 坐标）
        boxes           运输盒数，正整数
        operation       spawn_at_origin（在始发站生成）或 spawn_at_dest（反向）
    返回的 keys 前端直接消费：boxes / bots / batches / names / commands /
    killCommands / spawnStation / returnStation，新增字段需同步前端。
    """

    if operation not in OPERATIONS:
        raise ValueError(f"未知操作：{operation}")
    # 同站点搬运没有意义，也会让 {origin}/{dest} 拼出重复前缀.
    if origin["id"] == dest["id"]:
        raise ValueError("始发站和目的站不能是同一个站点")
    # 盒数允许是 "100" 这种字符串，但必须是整数值，不接受 100.5.
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
    # 设置里被改成 0 或负数时兜底，否则下面会除零.
    if boxes_per_bot <= 0 or bots_per_batch <= 0:
        raise ValueError("每假人盒数与每批人数必须大于 0")

    # 模板先整体校验一次，避免逐条渲染时才在循环中间炸掉.
    validate_template(name_template)
    bots = player_count(boxes, boxes_per_bot)
    if bots > MAX_BOTS:
        raise ValueError(f"假人数 {bots} 超过上限 {MAX_BOTS}，请拆成多张运单")

    # spawn_at_dest 表示「搬到目的站后从目的站生成假人往回带」，两边角色互换.
    spawn_station = origin if operation == "spawn_at_origin" else dest
    return_station = dest if operation == "spawn_at_origin" else origin

    batches = split_batches(bots, bots_per_batch)
    commands = []
    kill_commands = []
    names = []
    index = 0

    for bot in range(1, bots + 1):
        # 名字用站点前缀而不是全名，保证长度可控；check_name 兜住超长与非法字符.
        name = check_name(render(name_template, origin["prefix"], dest["prefix"], bot))
        names.append(name)
        index += 1
        # spawn 与 kill 共用同一个 index / bot / batch，前端按 index 对齐两列表.
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

    # spawnStation 存快照：之后站点被改名或删除，台账里仍能看到当时用的坐标.
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
    """
    查某个假人属于第几批；返回 0 表示没匹配到（正常不会发生）.
    """

    for batch in batches:
        if batch["from"] <= bot <= batch["to"]:
            return batch["index"]
    return 0
