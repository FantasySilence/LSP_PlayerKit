# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 边境炮对外动作           #
# =================================== #

# 边境炮的对外动作层：解析/校验请求参数、读取本工具设置，再调用 core 的三元求解、
# 拆档与落点预测；方向参考点在这里决定（炮口或旧版写死点），core 只做纯数学。
from __future__ import annotations

from lspkit.errors import AppError
from lspkit.platform import params

from .constants import DIRECTION_CODE_TABLE, DIRECTION_POINTS, DIRECTION_ROTATION
from .core.calculate import calculate
from .core.decompose import decompose
from .core.direction import motion_from_code
from .core.landing import position_at, trace


# ------ 公共参数解析 ------ #
def _origin(payload: dict, settings: dict) -> tuple[float, float, float]:
    """解析请求里的炮口坐标，缺省时回落到当前设置。

    参数:
        payload: 动作请求体，"origin" 可为 {x, y, z} 或缺失。
        settings: 当前边境炮设置，用 originX / originY / originZ 作为缺省值。

    返回:
        (x, y, z) 元组，单位方块。
    """

    origin = payload.get("origin") or {}
    return (
        params.number(origin, "x", default=settings["originX"], label="炮口 X"),
        params.number(origin, "y", default=settings["originY"], label="炮口 Y"),
        params.number(origin, "z", default=settings["originZ"], label="炮口 Z"),
    )


# ------ 动作实现 ------ #
def calculate_action(payload: dict, ctx) -> dict:
    """按目标坐标求解三颗 TNT 的当量，返回候选行。

    参数:
        payload: 请求体，含 target{x, y, z}、可选 origin{x, y, z}、time（预计飞行时间）。
        ctx: 平台动作上下文，用于读取本工具设置。

    返回:
        {"rows": 候选行, "directionMode": 模式, "directionOrigin": {x, z}}；
        row 含 tick（gt）、t1/t2/t3（个）、mx/my/mz（方块/gt）、dirCode/dirLabel。

    异常:
        AppError：缺参数或数值越界时由 params 抛出。

    说明:
        directionMode=origin 时用当前炮口判方向；=fixed 时用旧版写死的 (10000, 10000)，
        这样能逐行复现旧版的解（黄金快照就是这样生成的）。
    """

    settings = ctx.settings("border")
    ox, oy, oz = _origin(payload, settings)

    target = params.obj(payload, "target")
    tx = params.number(target, "x", label="目标 X", minimum=-30_000_000, maximum=30_000_000)
    ty = params.number(target, "y", label="目标 Y", minimum=-2048, maximum=4096)
    tz = params.number(target, "z", label="目标 Z", minimum=-30_000_000, maximum=30_000_000)
    # 预计飞行时间只是搜索起点，单位 gt；范围与界面输入框一致。
    flight_time = params.integer(
        payload, "time", default=settings["flightTime"], minimum=1, maximum=100000,
        label="预计飞行时间",
    )

    # 方向参考点：origin 用当前炮口；fixed 用旧版写死的点，只影响方向判定。
    mode = settings["directionMode"]
    if mode == "origin":
        direction_origin = (ox, oz)
    else:
        direction_origin = (DIRECTION_ROTATION["X"], DIRECTION_ROTATION["Z"])

    # core 返回 tick 升序、最多 MAX_ROWS 行；负当量不在这里过滤，界面照旧版原样显示。
    rows = calculate((ox, oy, oz), (tx, ty, tz), flight_time, direction_origin)
    return {
        "rows": rows,
        "directionMode": mode,
        "directionOrigin": {"x": direction_origin[0], "z": direction_origin[1]},
    }


def decode_action(payload: dict, ctx) -> dict:
    """把一组三颗 TNT 的当量与动量解码成小头 / 大头配置和文本。

    参数:
        payload: 请求体，含 tnt[3]（个）、motion{x, y, z}（方块/gt）、可选 origin、
            dirLabel（方向名或方向码）。
        ctx: 动作上下文，用于读取默认炮口坐标。

    返回:
        decompose 的结果：valid / small / big / landing / dirCode / text，并回填 tnt；
        landing 的 x / z 单位方块，ticks 单位 gt。

    异常:
        AppError("INVALID_PAYLOAD")：tnt 不是长度 3 的列表时抛出。
    """

    settings = ctx.settings("border")
    tnt = payload.get("tnt")
    # 必须正好三项：三颗 TNT 各对应矩阵的一行，多一个少一个都解不了。
    if not isinstance(tnt, list) or len(tnt) != 3:
        raise AppError("INVALID_PAYLOAD", "需要三项 TNT 数量")

    # 动量由前端从选中行带过来，这里不做物理推导，只负责拆档与文案。
    motion = params.obj(payload, "motion")
    origin = payload.get("origin") or {}
    ox = params.number(origin, "x", default=settings["originX"], label="炮口 X")
    oy = params.number(origin, "y", default=settings["originY"], label="炮口 Y")
    oz = params.number(origin, "z", default=settings["originZ"], label="炮口 Z")
    # dirLabel 可能是中文方位名，也可能是 "000" 这样的方向码，decompose 内部会兜底。
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
    # 回填原始当量，方便前端展示或复制。
    result["tnt"] = [int(v) for v in tnt]
    return result


def forecast_action(payload: dict, ctx) -> dict:
    """
    手动落点预报：输入三个 TNT 数量并手选方向，直接给出动量、配置与落点.

    与 `decode` 的区别：不需要先算出结果行，方向由用户指定。
    """

    settings = ctx.settings("border")
    tnt = payload.get("tnt")
    # 与 decode 一样先卡长度，再做逐项数值检查（顺序与旧版一致）。
    if not isinstance(tnt, list) or len(tnt) != 3:
        raise AppError("INVALID_PAYLOAD", "需要三项 TNT 数量")
    # 转 int 可能遇到非数字，单独兜成 INVALID_INPUT，便于前端给出可读提示。
    try:
        values = [int(v) for v in tnt]
    except (TypeError, ValueError):
        raise AppError("INVALID_INPUT", "TNT 数量必须是整数") from None
    if min(values) < 0:
        raise AppError("NEGATIVE_TNT", "TNT 数量不能为负数")
    # 上限只防误输入（一百万），不是物理限制。
    if max(values) > 1_000_000:
        raise AppError("INVALID_INPUT", "TNT 数量过大")

    # 0 表示只看落点；大于 0 时才额外计算该 gt 的位置。
    time_value = params.integer(
        payload, "time", default=0, minimum=0, maximum=100000, label="预计飞行时间"
    )

    # 方向码必须命中 8 个码之一，否则 params.choice 抛 INVALID_INPUT。
    code = params.choice(
        payload, "dirCode", tuple(DIRECTION_POINTS), default="000"
    )
    ox, oy, oz = _origin(payload, settings)

    # 行是第 i 颗 TNT、列是 X / Y / Z；乘当量后逐轴求和即总动量（方块/gt）。
    motion = motion_from_code(code)
    mx = float(sum(values[i] * motion[i, 0] for i in range(3)))
    my = float(sum(values[i] * motion[i, 1] for i in range(3)))
    mz = float(sum(values[i] * motion[i, 2] for i in range(3)))

    # 复用 decode 的同一套拆档逻辑，保证手动预报与解码结果的文案完全一致。
    result = decompose(
        values, {"x": mx, "y": my, "z": mz}, (ox, oy, oz), DIRECTION_CODE_TABLE[code]
    )

    # 手填飞行时间时，额外给出该 gt 的珍珠位置（Y < 256 之前才算有效）
    # trace 一直递推到落地；position_at 取第 time_value 个点，越界就说明那时已落地。
    flight = trace(mx, my, mz, (ox, oy, oz))
    at_time = position_at(flight["points"], time_value) if time_value else None
    result.update(
        {
            # 返回体在 decompose 的字段外，再补本次输入、动量与时间位置供界面使用。
            "tnt": values,
            "dirCode": code,
            "direction": DIRECTION_CODE_TABLE[code],
            "motion": {"x": mx, "y": my, "z": mz},
            "time": time_value,
            "atTime": at_time,
            # 供界面提示「还没到指定 gt 就已经落地」。
            "landedBefore": bool(time_value and at_time is None),
        }
    )
    if at_time is not None:
        # 有具体 gt 时把该时刻坐标追加到文本末尾（旧版也是这种拼接方式）。
        result["text"] = result["text"].rstrip("\n") + (
            f"\n第 {time_value} gt 位置：X {at_time['x']:.3f} / "
            f"Y {at_time['y']:.3f} / Z {at_time['z']:.3f}\n"
        )
    return result
