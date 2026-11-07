# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 材料数量换算             #
# =================================== #
# 纯函数：输入已解析的条目，输出每种材料的「盒 / 组 / 个」与汇总。
# 不读文件、不碰设置存储，堆叠数与每盒格数均由调用方传入。

from __future__ import annotations

# ------ 换算 ------ #


def convert(
    entries: list[dict],
    stack_size: int,
    shulker_slots: int,
    overrides: dict | None = None,
) -> dict:
    """
    把每种物品的数量换算成潜影盒 / 组 / 个，支持按材料单独指定堆叠数.

    换算方式（与游戏内整理习惯一致）：
    1. per_box = stack * slots 是单盒容量（个/盒）；
    2. divmod(count, per_box) 的商即整盒数，余数再按 stack 拆成整组与零散个数；
    3. 与 per_box 无关的「左右零头」都留在最后一盒里，所以余数不为 0 时多占 1 盒。
    """

    default_stack = max(1, int(stack_size))
    slots = max(1, int(shulker_slots))
    custom = overrides or {}
    rows: list[dict] = []
    boxes_needed = 0

    for entry in entries:

        name = entry["name"]
        # 单材料堆叠数可覆盖全局设置，非法值兜底为 1，避免除零
        stack = max(1, int(custom.get(name, default_stack)))
        per_box = stack * slots
        count = int(entry["count"])

        shulkers, rest = divmod(count, per_box)
        if stack == 1:
            # 不可堆叠：每个占用一格，没有「组」的概念
            stacks, items = 0, rest
        else:
            stacks, items = divmod(rest, stack)

        # 这里按「每种材料的零头各占一盒」累加，是偏保守的上界，
        # 不同材料的零头并不会拼进同一盒；精确的合并方案见 core/packing.py
        if stacks or items:
            boxes_needed += 1
        boxes_needed += shulkers

        rows.append(
            {
                "name": name,
                "stack": stack,
                "count": count,
                "shulkers": shulkers,
                "stacks": stacks,
                "items": items,
            }
        )

    # 数量多的排前面，数量相同按名字排序（lower 避免大小写影响顺序）
    rows.sort(key=lambda row: (-row["count"], row["name"].lower()))

    # totals 是整份清单的合计：kinds 为材料种数（种），perBox 为默认单盒容量（个/盒）；
    # shulkers / stacks / items 是各行结果的简单相加，因此 items 可能超过一组
    totals = {
        "kinds": len(rows),
        "count": sum(row["count"] for row in rows),
        "shulkers": sum(row["shulkers"] for row in rows),
        "stacks": sum(row["stacks"] for row in rows),
        "items": sum(row["items"] for row in rows),
        "perBox": default_stack * slots,
        "boxesNeeded": boxes_needed,
    }
    return {"items": rows, "totals": totals}
