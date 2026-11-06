# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 珍珠炮对外动作           #
# =================================== #

from __future__ import annotations

import numpy as np

from lspkit.errors import AppError
from lspkit.platform import params

from .constants import EJECT_TARGET_Y, GROUND_Y, MAX_SIM_TICKS
from .core.calculate import calculate
from .core.decompose import decompose
from .core.trace import generate, simulate


def _origin(payload: dict, settings: dict) -> tuple[float, float]:
    origin = payload.get("origin") or {}
    return (
        params.number(origin, "x", default=settings["originX"], label="炮口 X"),
        params.number(origin, "z", default=settings["originZ"], label="炮口 Z"),
    )


def _mode(payload: dict, settings: dict) -> str:
    mode = params.choice(payload, "mode", ("flat", "eject"), default="flat")
    if mode == "eject" and not settings["ejectionAvailable"]:
        raise AppError("EJECT_DISABLED", "当前炮架未启用抛射模式")
    return mode


def calculate_action(payload: dict, ctx) -> dict:
    settings = ctx.settings("pearl")
    origin_x, origin_z = _origin(payload, settings)
    target = params.obj(payload, "target")
    target_x = params.number(target, "x", label="目标 X", minimum=-30_000_000, maximum=30_000_000)
    target_z = params.number(target, "z", label="目标 Z", minimum=-30_000_000, maximum=30_000_000)
    max_tnt = params.integer(
        payload, "maxTnt", default=settings["maxTnt"], minimum=1, maximum=100000,
        label="最大 TNT 数量",
    )
    mode = _mode(payload, settings)

    direction, rows = calculate(settings, target_x, target_z, origin_x, origin_z, max_tnt, mode)
    return {"direction": direction, "mode": mode, "rows": rows}


def decode_action(payload: dict, ctx) -> dict:
    settings = ctx.settings("pearl")
    blue = params.integer(payload, "blue", minimum=0, label="蓝色 TNT")
    red = params.integer(payload, "red", minimum=0, label="红色 TNT")
    result = decompose(blue, red, settings["tntPerUnit"])
    result["tntPerUnit"] = settings["tntPerUnit"]
    return result


def trace_action(payload: dict, ctx) -> dict:
    settings = ctx.settings("pearl")
    origin = params.obj(payload, "origin")
    x0 = params.number(origin, "x", label="炮口 X")
    z0 = params.number(origin, "z", label="炮口 Z")
    direction = params.choice(
        payload, "direction", ("east", "west", "north", "south"), default="east"
    )
    mode = _mode(payload, settings)
    blue = params.integer(payload, "blue", minimum=0, label="蓝色 TNT")
    red = params.integer(payload, "red", minimum=0, label="红色 TNT")
    ticks = params.integer(payload, "ticks", default=350, minimum=1, maximum=2000, label="模拟时长")
    points = generate(
        x0, z0, np.array([blue, red]), direction, ticks, mode=mode, settings=settings
    )
    return {"points": points, "mode": mode, "direction": direction}


def simulate_action(payload: dict, ctx) -> dict:
    """
    手动模拟：只按输入的蓝 / 红 TNT 数量与方向推算轨迹，不依赖目标坐标.

    与 `trace` 的区别：不需要先选结果行，且会给出落地位置（Y <= groundY）。
    """

    settings = ctx.settings("pearl")
    origin = payload.get("origin") or {}
    x0 = params.number(origin, "x", default=settings["originX"], label="炮口 X")
    z0 = params.number(origin, "z", default=settings["originZ"], label="炮口 Z")
    blue = params.integer(payload, "blue", minimum=0, maximum=100000, label="蓝色 TNT")
    red = params.integer(payload, "red", minimum=0, maximum=100000, label="红色 TNT")
    direction = params.choice(
        payload, "direction", ("east", "west", "north", "south"), default="east"
    )
    mode = _mode(payload, settings)
    ticks = params.integer(
        payload, "ticks", default=MAX_SIM_TICKS, minimum=1, maximum=2000,
        label="模拟时长",
    )
    ground_y = params.number(
        payload, "groundY",
        default=EJECT_TARGET_Y if mode == "eject" else GROUND_Y,
        minimum=-2048, maximum=4096, label="落地高度",
    )

    result = simulate(
        x0, z0, np.array([blue, red]), direction, ticks,
        mode=mode, settings=settings, ground_y=ground_y,
    )
    result.update(
        {
            "direction": direction,
            "mode": mode,
            "blue": blue,
            "red": red,
            "total": blue + red,
            "ticks": ticks,
        }
    )
    return result
