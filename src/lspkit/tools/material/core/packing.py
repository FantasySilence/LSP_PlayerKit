# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 装填方案（最少潜影盒）   #
# =================================== #
# 纯函数：把「每种材料要多少个」折成「每种材料占几格」，再把格子装进潜影盒。
# 半组允许拆散，所以材料可以跨盒，问题退化为「容量为 cap 的盒子装 S 个格」。

from __future__ import annotations

# ------ 盒子构造 ------ #


def _new_box(index: int, capacity: int) -> dict:
    """
    新建一个空盒，index 从 1 开始，capacity 为格数（格/盒）.
    """

    return {"index": index, "capacity": capacity, "used": 0, "entries": []}


def _put(box: dict, unit: dict, stacks: int, items: int) -> None:
    """
    往盒子里放材料，同一盒内同名材料合并成一条.

    一次放入分两段：先放整组（stacks，单位：组），再放零散（items，单位：个），
    零散个数不足一组也占一整格，因此格数 slots = stacks + (items > 0)。
    同名材料连续放入时合并到上一条，避免同一盒里出现重复行。
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


# ------ 分组合并 ------ #


def _group_boxes(boxes: list[dict]) -> list[dict]:
    """
    把「连续且满装、只放单一材料」的盒子合并成一组，便于界面节省空间.

    只合并相邻、同材料、同堆叠数且已装满的盒子：它们的内容完全一样，
    合并后用一个 from–to 区间表示即可。其他盒子原样作为单盒组输出，
    因此 groups 中的每一组按顺序拼起来仍与 boxes 一一对应。
    """

    groups: list[dict] = []
    run: list[dict] = []

    def flush() -> None:
        if not run:
            return
        first = run[0]
        entry = first["entries"][0]
        merged = {
            "name": entry["name"],
            "stack": entry["stack"],
            "stacks": sum(box["entries"][0]["stacks"] for box in run),
            "items": sum(box["entries"][0]["items"] for box in run),
            "slots": sum(box["entries"][0]["slots"] for box in run),
            "count": sum(box["entries"][0]["count"] for box in run),
        }
        groups.append(
            {
                "from": first["index"],
                "to": run[-1]["index"],
                "boxes": len(run),
                "capacity": first["capacity"],
                "used": sum(box["used"] for box in run),
                "entries": [merged],
                "merged": len(run) > 1,
            }
        )
        run.clear()

    for box in boxes:
        entries = box["entries"]
        pure = len(entries) == 1 and box["used"] >= box["capacity"]
        if pure:
            if run and (
                run[0]["entries"][0]["name"] != entries[0]["name"]
                or run[0]["entries"][0]["stack"] != entries[0]["stack"]
            ):
                flush()
            run.append(box)
            continue

        flush()
        groups.append(
            {
                "from": box["index"],
                "to": box["index"],
                "boxes": 1,
                "capacity": box["capacity"],
                "used": box["used"],
                "entries": entries,
                "merged": False,
            }
        )

    flush()
    return groups


# ------ 主入口 ------ #


def plan(
    entries: list[dict],
    stack_size: int,
    capacity: int,
    overrides: dict | None = None,
) -> dict:
    """
    按「大件优先、逐盒装满」给出装填方案，盒数为理论最小值.

    盒数为什么是最少：每种材料的「占用格数」= ceil(count / stack)，
    即整组数加上「有零头时多占的 1 格」，与它被装进哪个盒子无关。
    记总占用格数 S、每盒容量 cap，则任何方案都至少需要 ceil(S / cap) 盒；
    下面的逐盒装满恰好只把每个格子放进一次，用满前 ceil(S/cap) - 1 盒、
    最后一盒装剩下的格子，因此盒数正好等于这个下界，也就是最少盒数。
    先装占用格数多的材料，是为了让同种材料尽量落在相邻盒子，减少跨盒拆散。
    """

    cap = max(1, int(capacity))
    default_stack = max(1, int(stack_size))
    custom = overrides or {}
    units: list[dict] = []

    for entry in entries:

        stack = max(1, int(custom.get(entry["name"], default_stack)))
        count = int(entry["count"])
        # full 是整组数（组），rem 是不足一组的零散个数（个）
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

        # 先按整组连续装，盒子装满就换下一个
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

        # 零散个数单独占一格：当前盒满了就另起一盒，绝不跨盒拆分
        if unit["rem"] > 0:
            if cap - current["used"] <= 0:
                boxes.append(current)
                current = _new_box(len(boxes) + 1, cap)
            _put(current, unit, 0, unit["rem"])
            current["used"] += 1

    if current["entries"]:
        boxes.append(current)

    # totals.slots 是总占用格数（格），capacity 是单盒格数（格/盒），
    # boxes 应等于 ceil(slots / capacity)，可与上面的下界互相验证
    total_slots = sum(unit["slots"] for unit in units)
    return {
        "boxes": boxes,
        "groups": _group_boxes(boxes),
        "totals": {
            "boxes": len(boxes),
            "slots": total_slots,
            "capacity": cap,
            "kinds": len(units),
        },
    }
