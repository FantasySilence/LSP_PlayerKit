# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 珍珠炮 TNT 当量计算      #
# =================================== #
# 算法逐行对齐旧版 LSP_PearlCannonConfig，保留其取整、枚举顺序与排序行为。
# 对外只有一个 calculate() 入口，按模式分发到 calculate_flat / calculate_eject：
# 两者都是「先解线性方程组拿初解，再在初解附近枚举微调，取落点误差最小的一组」。

from __future__ import annotations

import numpy as np

from ..constants import (
    DAMPING,
    EJECT_TARGET_Y,
    EJECT_TUNING,
    EJECT_Y_WINDOW,
    FLAT_TUNING,
    MAX_TICKS,
)
from .direction import Directions
from .tuning import generate_combinations


# ------ 公共小工具 ------ #
def _round_ints(values) -> list[int]:
    """把线性方程组的浮点解四舍五入成整数 TNT 数量。

    参数:
        values: 可迭代的浮点数，即方程组解出的每轴当量（理论值）。

    返回:
        list[int]，长度与输入一致，单位个。

    说明:
        用 Python 内置 round（恰好 .5 时取偶，即银行家舍入）再转 int；旧版就是这套写法。
        换成 int(v + 0.5) 之类的写法会在 .5 边界产生 ±1 差异，黄金快照会对不上。
    """

    return [int(round(float(v))) for v in values]


def _row(tick: int, error: float, blue: int, red: int) -> dict:
    """组装一行候选结果。

    参数:
        tick: 飞行时间，单位 gt。
        error: 落点与目标的水平偏差（欧氏距离），单位方块。
        blue: 蓝色 TNT 数量，单位个。
        red: 红色 TNT 数量，单位个。

    返回:
        {error, ticks, blue, red, total}；total 由蓝 + 红相加，不单独求解。
    """

    return {
        "error": float(error),
        "ticks": int(tick),
        "blue": int(blue),
        "red": int(red),
        "total": int(blue) + int(red),
    }


# ------ 平射求解 ------ #
def calculate_flat(
    settings: dict,
    target_x: float,
    target_z: float,
    origin_x: float,
    origin_z: float,
    max_tnt: int,
) -> tuple[str, list[dict]]:
    """平射：对每个飞行时刻解出蓝 / 红 TNT 数量，再做小范围微调。

    参数:
        settings: 当前珍珠炮设置，读取 flat.xzMotion（单 TNT 水平动量，方块/gt）。
        target_x: 目标 X 坐标，单位方块。
        target_z: 目标 Z 坐标，单位方块。
        origin_x: 炮口 X 坐标，单位方块。
        origin_z: 炮口 Z 坐标，单位方块。
        max_tnt: 蓝、红各自的当量上限，单位个（不是两者之和的上限）。

    返回:
        (方向名, 行列表)；方向为 east / west / north / south，行按 tick 升序，
        每行结构见 _row，error 单位方块。

    说明:
        1. 水平位移公式为 s = 100 * v * (1 - 0.99**tick)，其中 v 是单 TNT 动量、
           100 = 1 / (1 - 0.99)；由此反解出该 gt 所需的单 TNT 动量。
        2. 方向矩阵把 (蓝, 红) 映射成 (X, Z) 单位动量，于是解 2x2 方程
           xzMotion * matrix @ (蓝, 红) = 所需动量，得到浮点初解。
        3. 初解取整后越界（<0 或 >max_tnt）的 tick 直接丢弃。
        4. 微调：初解可能落在整数网格外，所以在 ±2 内枚举 25 组，
           用整数当量重算落点、取欧氏误差最小的一组，这一步是精度的主要来源。
        5. 行序沿用 dict 插入顺序（即 tick 升序），平射结果不额外排序。
    """

    # 先判方向：同一组 (target - origin) 既决定方向名，也决定 2x2 符号矩阵。
    direction, matrix = Directions.judge(target_x, target_z, origin_x, origin_z)
    xz_motion = settings["flat"]["xzMotion"]

    # 第一步：逐 tick 解方程，得到每个飞行时刻的浮点初解（取整后存入 preliminary）。
    preliminary: dict[int, list[int]] = {}
    for tick in range(1, MAX_TICKS + 1):
        # 所需单 TNT 动量 = 位移 / (100 * (1 - 0.99**tick))，单位方块/gt。
        b = np.array(
            [
                (target_x - origin_x) / (100 * (1 - DAMPING**tick)),
                (target_z - origin_z) / (100 * (1 - DAMPING**tick)),
            ]
        )
        try:
            solution = np.linalg.solve(xz_motion * matrix, b)
        except np.linalg.LinAlgError:
            # 系数矩阵奇异（方向矩阵退化或动量为 0）时无解，跳过该 tick 继续搜索。
            continue
        x = _round_ints(solution)
        # 负数或超过上限的当量在实际炮架上摆不出来，直接丢弃这一组。
        if 0 <= x[0] <= max_tnt and 0 <= x[1] <= max_tnt:
            preliminary[tick] = x

    # 第二步：在初解附近枚举微调，用整数当量回算落点，保留误差最小的一组。
    final: dict[int, list] = {}
    for tick, base in preliminary.items():
        combos = generate_combinations(np.array(base), FLAT_TUNING)
        best = None
        for combo in combos:
            # 用微调后的整数当量重新合成水平动量，再算该 tick 的落点。
            motion = xz_motion * matrix.dot(combo)
            xt = origin_x + 100 * motion[0] * (1 - DAMPING**tick)
            zt = origin_z + 100 * motion[1] * (1 - DAMPING**tick)
            error = float(np.sqrt((xt - target_x) ** 2 + (zt - target_z) ** 2))
            if best is None or error < best[0]:
                best = (error, combo)
        if best is not None:
            final[tick] = [best[0], best[1]]

    # 汇总成结果行；dict 保留插入顺序，这里天然就是 tick 升序，不额外排序。
    rows = [
        _row(tick, value[0], value[1][0], value[1][1])
        for tick, value in final.items()
    ]
    return direction, rows


# ------ 抛射求解 ------ #
def calculate_eject(
    settings: dict,
    target_x: float,
    target_z: float,
    origin_x: float,
    origin_z: float,
    max_tnt: int,
) -> tuple[str, list[dict]]:
    """抛射：解出能让珍珠在指定高度（128）上命中目标的 TNT 当量。

    参数:
        settings: 当前珍珠炮设置，读取 eject.xzMotion / yMotion / yInitMotion /
            yInitPosition。
        target_x: 目标 X 坐标，单位方块。
        target_z: 目标 Z 坐标，单位方块。
        origin_x: 炮口 X 坐标，单位方块。
        origin_z: 炮口 Z 坐标，单位方块。
        max_tnt: 蓝、红各自的当量上限，单位个。

    返回:
        (方向名, 行列表)；与平射不同，行按 error 升序排列（eject 特有，便于直接取最优），
        error 单位方块。

    说明:
        1. 抛射要求珍珠在 tick gt 时到达 Y = EJECT_TARGET_Y。Y 位移的闭式解是
           y = y0 + 100 * (v0 + 3) * (1 - 0.99**tick) - 3 * tick，
           其中 3 = 0.03 / (1 - 0.99) 是重力带来的每 gt 固定下坠（终端速度 -3）。
        2. 由此反解 v0 = (128 - y0 + 3 * tick) / (100 * (1 - 0.99**tick)) - 3，
           再减掉 yInitMotion、除以 yMotion，得到 Y 方向所需的总当量。
        3. 水平方向与平射相同；第二个约束行取方向矩阵再作用一次目标动量，
           让它与 (蓝, 红) 正交，从而把合成水平动量拉到目标方向上。
        4. 初解取整后仍要过 0..max_tnt 检查；微调放宽到每轴 ±10（441 组）。
        5. 只有合成落点 Y 落在 EJECT_Y_WINDOW（128..129，闭区间）的解才参与比较。
    """

    # 抛射同样先判方向；cfg 指向 eject 那一组弹道参数。
    direction, matrix = Directions.judge(target_x, target_z, origin_x, origin_z)
    cfg = settings["eject"]
    y0 = cfg["yInitPosition"]

    # 第一步：逐 tick 解方程，先求 Y 方向需要的总当量，再解出蓝 / 红的分配。
    preliminary: dict[int, list[int]] = {}
    for tick in range(1, MAX_TICKS + 1):
        # 水平用 100 * (1 - 0.99**tick) 的位移系数，垂直还要减掉重力的固定下坠。
        factor = 100 * (1 - DAMPING**tick)
        px = (target_x - origin_x) / factor
        # 3 * tick 与后面的 -3：把重力项移到等式左边，解出初速度 v0。
        py = (EJECT_TARGET_Y - y0 + 3 * tick) / factor - 3
        pz = (target_z - origin_z) / factor

        # 方向矩阵再作用一次目标动量，作为「水平指向」的约束行。
        p_xz = matrix.dot(np.array([px, pz]))
        # 方程 1：蓝 + 红 = Y 方向所需总当量；方程 2：水平动量与目标方向正交。
        coefs = np.array([[1, 1], p_xz])
        consts = np.array([(py - cfg["yInitMotion"]) / cfg["yMotion"], 0])
        try:
            solution = np.linalg.solve(coefs, consts)
        except np.linalg.LinAlgError:
            # 两行线性相关（例如 p_xz 与 [1, 1] 平行）时无解，跳过该 tick。
            continue
        x = _round_ints(solution)
        if 0 <= x[0] <= max_tnt and 0 <= x[1] <= max_tnt:
            preliminary[tick] = x

    # 第二步：微调并复核，抛射的偏移范围比平射大，且要额外卡 Y 高度窗口。
    final: dict[int, list] = {}
    for tick, base in preliminary.items():
        combos = generate_combinations(np.array(base), EJECT_TUNING)
        best = None
        for combo in combos:
            motion = cfg["xzMotion"] * matrix.dot(combo)
            y_motion = cfg["yMotion"] * sum(combo) + cfg["yInitMotion"]
            xt = origin_x + 100 * motion[0] * (1 - DAMPING**tick)
            # 与递推一致的 Y 位移公式：几何衰减项 + 每 gt 的 -3 下坠。
            yt = y0 + 100 * (y_motion + 3) * (1 - DAMPING**tick) - 3 * tick
            zt = origin_z + 100 * motion[1] * (1 - DAMPING**tick)
            # 高度不在 128..129 的组对抛射没有意义（会砸在别的层），与旧版一致地丢弃。
            if not (EJECT_Y_WINDOW[0] <= yt <= EJECT_Y_WINDOW[1]):
                continue
            error = float(np.sqrt((xt - target_x) ** 2 + (zt - target_z) ** 2))
            if best is None or error < best[0]:
                best = (error, combo)
        if best is not None:
            final[tick] = [best[0], best[1]]

    rows = [
        _row(tick, value[0], value[1][0], value[1][1])
        for tick, value in final.items()
    ]
    # 抛射结果按误差升序，界面可以直接取第一行作为推荐解。
    rows.sort(key=lambda row: row["error"])
    return direction, rows


# ------ 模式分发 ------ #
def calculate(
    settings: dict,
    target_x: float,
    target_z: float,
    origin_x: float,
    origin_z: float,
    max_tnt: int,
    mode: str,
) -> tuple[str, list[dict]]:
    """按发射模式分发到平射 / 抛射求解。

    参数:
        settings: 当前珍珠炮设置。
        target_x: 目标 X 坐标，单位方块。
        target_z: 目标 Z 坐标，单位方块。
        origin_x: 炮口 X 坐标，单位方块。
        origin_z: 炮口 Z 坐标，单位方块。
        max_tnt: 蓝、红各自的当量上限，单位个。
        mode: "flat" 平射 / "eject" 抛射；调用方已用 params.choice 校验取值。

    返回:
        (方向名, 行列表)；行结构见 _row。
    """

    # 非 eject 一律按平射处理，与平台参数校验的取值集合保持一致。
    if mode == "eject":
        return calculate_eject(settings, target_x, target_z, origin_x, origin_z, max_tnt)
    return calculate_flat(settings, target_x, target_z, origin_x, origin_z, max_tnt)
