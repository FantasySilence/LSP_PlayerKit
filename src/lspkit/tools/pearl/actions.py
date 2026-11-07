# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 珍珠炮对外动作           #
# =================================== #

# 珍珠炮的对外动作层：负责解析/校验请求参数、读取本工具设置，再调用 core 里的
# 纯计算函数，把结果整理成前端需要的结构；这里不做数值计算，也不改结果行。
from __future__ import annotations

import numpy as np

from lspkit.errors import AppError
from lspkit.platform import params

from .constants import EJECT_TARGET_Y, GROUND_Y, MAX_SIM_TICKS
from .core.calculate import calculate
from .core.decompose import decompose
from .core.trace import generate, simulate


# ------ 公共参数解析 ------ #
def _origin(payload: dict, settings: dict) -> tuple[float, float]:
    """解析请求里的炮口坐标，缺省时回落到当前设置。

    参数:
        payload: 动作请求体，"origin" 可为 {x, z} 或缺失。
        settings: 当前珍珠炮设置，用 originX / originZ 作为缺省值。

    返回:
        (x, z) 元组，单位方块。
    """

    origin = payload.get("origin") or {}
    return (
        params.number(origin, "x", default=settings["originX"], label="炮口 X"),
        params.number(origin, "z", default=settings["originZ"], label="炮口 Z"),
    )


def _mode(payload: dict, settings: dict) -> str:
    """读取并校验发射模式；炮架未启用抛射时直接报错。

    参数:
        payload: 动作请求体，"mode" 取 flat / eject，缺省 flat。
        settings: 当前设置，用 ejectionAvailable 判断抛射是否开放。

    返回:
        "flat" 或 "eject"。

    异常:
        AppError("EJECT_DISABLED")：请求抛射但当前炮架未启用抛射。
    """

    mode = params.choice(payload, "mode", ("flat", "eject"), default="flat")
    if mode == "eject" and not settings["ejectionAvailable"]:
        raise AppError("EJECT_DISABLED", "当前炮架未启用抛射模式")
    return mode


# ------ 动作实现 ------ #
def calculate_action(payload: dict, ctx) -> dict:
    """按目标坐标搜索候选 TNT 当量，返回方向与结果行。

    参数:
        payload: 请求体，含 target{x, z}，可选 origin{x, z}、maxTnt、mode。
        ctx: 平台动作上下文，用于读取本工具设置。

    返回:
        {"direction": 方向名, "mode": 模式, "rows": 候选行列表}；
        row 的 error 单位方块，ticks 单位 gt，blue/red/total 单位个。

    异常:
        AppError：缺参数、超范围或抛射被禁用时，由 params / _mode 抛出。

    说明:
        maxTnt 在求解时对蓝、红各自做上限检查（与旧版一致），不是两者之和。
    """

    settings = ctx.settings("pearl")
    # 炮口可省略（回落到设置），目标必填。
    origin_x, origin_z = _origin(payload, settings)
    target = params.obj(payload, "target")
    target_x = params.number(target, "x", label="目标 X", minimum=-30_000_000, maximum=30_000_000)
    target_z = params.number(target, "z", label="目标 Z", minimum=-30_000_000, maximum=30_000_000)
    max_tnt = params.integer(
        payload, "maxTnt", default=settings["maxTnt"], minimum=1, maximum=100000,
        label="最大 TNT 数量",
    )
    mode = _mode(payload, settings)

    # 行序由 core 决定：平射按 tick 升序、抛射按误差升序，这里原样透传，不再排序。
    direction, rows = calculate(settings, target_x, target_z, origin_x, origin_z, max_tnt, mode)
    return {"direction": direction, "mode": mode, "rows": rows}


def decode_action(payload: dict, ctx) -> dict:
    """把蓝 / 红 TNT 数量拆成 260 / 10 / 1 三档并生成旧版文本。

    参数:
        payload: 请求体，含 blue、red（非负整数，单位个）。
        ctx: 动作上下文，用于读取 tntPerUnit（每组当量，默认 260）。

    返回:
        decompose 的结果：blue/red 为各档数量列表，blueText/redText 为 "N = a + b" 文本；
        另补上本次使用的 tntPerUnit 便于界面回显。

    异常:
        AppError：数量为负时先被 params.integer 的 minimum 拦成 INVALID_INPUT；
        即使绕过校验，decompose 内部也会再抛 NEGATIVE_TNT 兜底。
    """

    settings = ctx.settings("pearl")
    blue = params.integer(payload, "blue", minimum=0, label="蓝色 TNT")
    red = params.integer(payload, "red", minimum=0, label="红色 TNT")
    result = decompose(blue, red, settings["tntPerUnit"])
    result["tntPerUnit"] = settings["tntPerUnit"]
    return result


def trace_action(payload: dict, ctx) -> dict:
    """按方向与 TNT 数量逐 gt 递推整条轨迹，供曲线绘制使用。

    参数:
        payload: 请求体，含 origin{x, z}（必填）、direction、mode、blue、red、ticks。
        ctx: 动作上下文，用于读取弹道设置。

    返回:
        {"points": [{t, x, y, z}, ...], "mode": 模式, "direction": 方向名}；
        坐标单位方块，t 单位 gt，points[0] 为 t=0 的出膛点。

    异常:
        AppError：缺 origin、方向取值非法或抛射被禁用时由 params / _mode 抛出。

    说明:
        与 simulate 不同，这里 origin 必填且不做落地判定，ticks 默认 350。
    """

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
    # origin 可省略，缺省回落到设置里的炮口坐标（trace 则要求必填）。
    origin = payload.get("origin") or {}
    x0 = params.number(origin, "x", default=settings["originX"], label="炮口 X")
    z0 = params.number(origin, "z", default=settings["originZ"], label="炮口 Z")
    blue = params.integer(payload, "blue", minimum=0, maximum=100000, label="蓝色 TNT")
    red = params.integer(payload, "red", minimum=0, maximum=100000, label="红色 TNT")
    direction = params.choice(
        payload, "direction", ("east", "west", "north", "south"), default="east"
    )
    mode = _mode(payload, settings)
    # 默认模拟时长比当量搜索更长，便于一直画到落地。
    ticks = params.integer(
        payload, "ticks", default=MAX_SIM_TICKS, minimum=1, maximum=2000,
        label="模拟时长",
    )
    # 落地高度默认：抛射取靶层 128，平射取地面 0（与界面提示一致）。
    ground_y = params.number(
        payload, "groundY",
        default=EJECT_TARGET_Y if mode == "eject" else GROUND_Y,
        minimum=-2048, maximum=4096, label="落地高度",
    )

    result = simulate(
        x0, z0, np.array([blue, red]), direction, ticks,
        mode=mode, settings=settings, ground_y=ground_y,
    )
    # 返回体：simulate 的 points / landing / distance / groundY / simulatedTicks，
    # 外加本次输入（方向、模式、蓝 / 红数量、总当量与模拟时长）。
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
