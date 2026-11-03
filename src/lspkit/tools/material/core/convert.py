# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 材料数量换算             #
# =================================== #

from __future__ import annotations


def convert(entries: list[dict], stack_size: int, shulker_slots: int) -> dict:
    """
    把每种物品的数量换算成潜影盒 / 组 / 个.
    """

    per_box = max(1, stack_size) * max(1, shulker_slots)
    rows: list[dict] = []
    boxes_needed = 0

    for entry in entries:

        count = int(entry["count"])
        shulkers, rest = divmod(count, per_box)
        stacks, items = divmod(rest, stack_size)

        if stacks or items:
            boxes_needed += 1
        boxes_needed += shulkers

        rows.append(
            {
                "name": entry["name"],
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
        "perBox": per_box,
        "boxesNeeded": boxes_needed,
    }
    return {"items": rows, "totals": totals}
