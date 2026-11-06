# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 边境炮对外动作           #
# =================================== #

from __future__ import annotations

from lspkit.errors import AppError
from lspkit.platform import params

from .constants import DIRECTION_CODE_TABLE, DIRECTION_POINTS, DIRECTION_ROTATION
from .core.calculate import calculate
from .core.decompose import decompose
from .core.direction import motion_from_code
from .core.landing import position_at, trace


def _origin(payload: dict, settings: dict) -> tuple[float, float, float]:
    origin = payload.get("origin") or {}
    return (
        params.number(origin, "x", default=settings["originX"], label="炮口 X"),
        params.number(origin, "y", default=settings["originY"], label="炮口 Y"),
        params.number(origin, "z", default=settings["originZ"], label="炮口 Z"),
    )


def calculate_action(payload: dict, ctx) -> dict:
    settings = ctx.settings("border")
    ox, oy, oz = _origin(payload, settings)

    target = params.obj(payload, "target")
    tx = params.number(target, "x", label="目标 X", minimum=-30_000_000, maximum=30_000_000)
    ty = params.number(target, "y", label="目标 Y", minimum=-2048, maximum=4096)
    tz = params.number(target, "z", label="目标 Z", minimum=-30_000_000, maximum=30_000_000)
    flight_time = params.integer(
        payload, "time", default=settings["flightTime"], minimum=1, maximum=100000,
        label="预计飞行时间",
    )

    mode = settings["directionMode"]
    if mode == "origin":
        direction_origin = (ox, oz)
    else:
        direction_origin = (DIRECTION_ROTATION["X"], DIRECTION_ROTATION["Z"])

    rows = calculate((ox, oy, oz), (tx, ty, tz), flight_time, direction_origin)
    return {
        "rows": rows,
        "directionMode": mode,
        "directionOrigin": {"x": direction_origin[0], "z": direction_origin[1]},
    }


def decode_action(payload: dict, ctx) -> dict:
    settings = ctx.settings("border")
    tnt = payload.get("tnt")
    if not isinstance(tnt, list) or len(tnt) != 3:
        raise AppError("INVALID_PAYLOAD", "需要三项 TNT 数量")

    motion = params.obj(payload, "motion")
    origin = payload.get("origin") or {}
    ox = params.number(origin, "x", default=settings["originX"], label="炮口 X")
    oy = params.number(origin, "y", default=settings["originY"], label="炮口 Y")
    oz = params.number(origin, "z", default=settings["originZ"], label="炮口 Z")
    dir_label = str(payload.get("dirLabel") or "")

    result = decompose(
        [int(v) for v in tnt],
        {
            "x": params.number(motion, "x", label="x 动量"),
            "y": params.number(motion, "y", label="y 动量"),
            "z": params.number(motion, "z", label="z 动量"),
        },
        (ox, oy, oz),
        dir_label,
    )
    result["tnt"] = [int(v) for v in tnt]
    return result


def forecast_action(payload: dict, ctx) -> dict:
    """
    手动落点预报：输入三个 TNT 数量并手选方向，直接给出动量、配置与落点.

    与 `decode` 的区别：不需要先算出结果行，方向由用户指定。
    """

    settings = ctx.settings("border")
    tnt = payload.get("tnt")
    if not isinstance(tnt, list) or len(tnt) != 3:
        raise AppError("INVALID_PAYLOAD", "需要三项 TNT 数量")
    try:
        values = [int(v) for v in tnt]
    except (TypeError, ValueError):
        raise AppError("INVALID_INPUT", "TNT 数量必须是整数") from None
    if min(values) < 0:
        raise AppError("NEGATIVE_TNT", "TNT 数量不能为负数")
    if max(values) > 1_000_000:
        raise AppError("INVALID_INPUT", "TNT 数量过大")

    time_value = params.integer(
        payload, "time", default=0, minimum=0, maximum=100000, label="预计飞行时间"
    )

    code = params.choice(
        payload, "dirCode", tuple(DIRECTION_POINTS), default="000"
    )
    ox, oy, oz = _origin(payload, settings)

    motion = motion_from_code(code)
    mx = float(sum(values[i] * motion[i, 0] for i in range(3)))
    my = float(sum(values[i] * motion[i, 1] for i in range(3)))
    mz = float(sum(values[i] * motion[i, 2] for i in range(3)))

    result = decompose(
        values, {"x": mx, "y": my, "z": mz}, (ox, oy, oz), DIRECTION_CODE_TABLE[code]
    )

    # 手填飞行时间时，额外给出该 gt 的珍珠位置（Y < 256 之前才算有效）
    flight = trace(mx, my, mz, (ox, oy, oz))
    at_time = position_at(flight["points"], time_value) if time_value else None
    result.update(
        {
            "tnt": values,
            "dirCode": code,
            "direction": DIRECTION_CODE_TABLE[code],
            "motion": {"x": mx, "y": my, "z": mz},
            "time": time_value,
            "atTime": at_time,
            "landedBefore": bool(time_value and at_time is None),
        }
    )
    if at_time is not None:
        result["text"] = result["text"].rstrip("\n") + (
            f"\n第 {time_value} gt 位置：X {at_time['x']:.3f} / "
            f"Y {at_time['y']:.3f} / Z {at_time['z']:.3f}\n"
        )
    return result
