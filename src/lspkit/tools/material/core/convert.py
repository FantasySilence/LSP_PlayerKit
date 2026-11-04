# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 材料数量换算             #
# =================================== #

from __future__ import annotations


def convert(
    entries: list[dict],
    stack_size: int,
    shulker_slots: int,
    overrides: dict | None = None,
) -> dict:
    """
    把每种物品的数量换算成潜影盒 / 组 / 个，支持按材料单独指定堆叠数.
    """

    default_stack = max(1, int(stack_size))
    slots = max(1, int(shulker_slots))
    custom = overrides or {}
    rows: list[dict] = []
    boxes_needed = 0

    for entry in entries:

        name = entry["name"]
        stack = max(1, int(custom.get(name, default_stack)))
        per_box = stack * slots
        count = int(entry["count"])

        shulkers, rest = divmod(count, per_box)
        if stack == 1:
            # 不可堆叠：每个占用一格，没有「组」的概念
            stacks, items = 0, rest
        else:
            stacks, items = divmod(rest, stack)

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

    rows.sort(key=lambda row: (-row["count"], row["name"].lower()))

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
