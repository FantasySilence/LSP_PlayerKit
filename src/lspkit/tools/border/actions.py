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

from .constants import DIRECTION_ROTATION
from .core.calculate import calculate
from .core.decompose import decompose


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
