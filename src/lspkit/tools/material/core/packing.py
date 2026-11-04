# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 装填方案（最少潜影盒）   #
# =================================== #

from __future__ import annotations


def _new_box(index: int, capacity: int) -> dict:
    return {"index": index, "capacity": capacity, "used": 0, "entries": []}


def _put(box: dict, unit: dict, stacks: int, items: int) -> None:
    """
    往盒子里放材料，同一盒内同名材料合并成一条.
    """

    slots = stacks + (1 if items else 0)
    count = stacks * unit["stack"] + items
    entries = box["entries"]

    if entries and entries[-1]["name"] == unit["name"]:
        entry = entries[-1]
        entry["stacks"] += stacks
        entry["items"] += items
        entry["slots"] += slots
        entry["count"] += count
        return

    entries.append(
        {
            "name": unit["name"],
            "stack": unit["stack"],
            "stacks": stacks,
            "items": items,
            "slots": slots,
            "count": count,
        }
    )


def plan(
    entries: list[dict],
    stack_size: int,
    capacity: int,
    overrides: dict | None = None,
) -> dict:
    """
    按「大件优先、逐盒装满」给出装填方案，盒数为理论最小值.
    """

    cap = max(1, int(capacity))
    default_stack = max(1, int(stack_size))
    custom = overrides or {}
    units: list[dict] = []

    for entry in entries:

        stack = max(1, int(custom.get(entry["name"], default_stack)))
        count = int(entry["count"])
        full, rem = divmod(count, stack)
        slots = full + (1 if rem else 0)
        if slots <= 0:
            continue
        units.append(
            {
                "name": entry["name"],
                "stack": stack,
                "full": full,
                "rem": rem,
                "slots": slots,
                "count": count,
            }
        )

    # 占用格数多的先装，尽量减少同一材料被拆到多个盒子
    units.sort(key=lambda unit: (-unit["slots"], -unit["count"], unit["name"]))

    boxes: list[dict] = []
    current = _new_box(1, cap)

    for unit in units:

        full_left = unit["full"]
        while full_left > 0:
            free = cap - current["used"]
            if free <= 0:
                boxes.append(current)
                current = _new_box(len(boxes) + 1, cap)
                continue
            take = min(full_left, free)
            _put(current, unit, take, 0)
            full_left -= take
            current["used"] += take

        if unit["rem"] > 0:
            if cap - current["used"] <= 0:
                boxes.append(current)
                current = _new_box(len(boxes) + 1, cap)
            _put(current, unit, 0, unit["rem"])
            current["used"] += 1

    if current["entries"]:
        boxes.append(current)

    total_slots = sum(unit["slots"] for unit in units)
    return {
        "boxes": boxes,
        "totals": {
            "boxes": len(boxes),
            "slots": total_slots,
            "capacity": cap,
            "kinds": len(units),
        },
    }
