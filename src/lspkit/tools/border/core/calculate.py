# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 边境炮三元 TNT 求解      #
# =================================== #

# 边境炮三元 TNT 求解：对每个候选飞行时刻解一个 3x3 线性方程组，得到三颗 TNT 的当量，
# 再用整数当量回算真实动量；方向由目标相对参考点的位置决定（见 core/direction）。
from __future__ import annotations

import numpy as np

from ..constants import DIRECTION_CODE_TABLE, MAX_ROWS
from .motion import load_motion


# ------ 三元求解 ------ #
def calculate(
    origin: tuple[float, float, float],
    target: tuple[float, float, float],
    flight_time: int,
    direction_origin: tuple[float, float],
) -> list[dict]:
    """对候选飞行时刻逐个解出三颗 TNT 的当量。

    参数:
        origin: 炮口坐标 (x, y, z)，单位方块。
        target: 目标坐标 (x, y, z)，单位方块。
        flight_time: 起始飞行时间，单位 gt；从它开始连续尝试 MAX_ROWS 个时刻。
        direction_origin: 判方向用的参考点 (x, z)，单位方块
            （当前炮口，或 directionMode=fixed 时旧版写死的 (10000, 10000)）。

    返回:
        list[dict]：每行 {tick, t1, t2, t3, mx, my, mz, dirCode, dirLabel}；
        tick 单位 gt，t1..t3 单位个，mx/my/mz 单位方块/gt。

    说明:
        1. 水平位移系数 factor = 100 * (1 - 0.99**tick)，与珍珠炮共用同一套阻尼运动学。
        2. px / pz 是该 gt 水平方向需要的单 TNT 动量；py 是垂直方向。
           py 的除数写的是 (factor - 3) 而不是 factor，再单独减 3；它与递推式
           y = y0 + 100 * (v + 3) * (1 - 0.99**t) - 3 * t 的严格反解
           (ty - oy + 3 * tick) / factor - 3 并不等价，属于旧版的历史写法；
           为了逐行复刻，这里不作修正。
        3. 方程组：动量矩阵（行 = 第 i 颗 TNT，列 = X / Y / Z）转置后每行是一个轴，
           与 (px, py, pz) 拼成增广矩阵，解 A @ (t1, t2, t3) = p。
        4. 取整用 int(round(...))（恰好 .5 时取偶）；取整后回算 mx/my/mz，
           让界面显示的是「真实能摆出来的整数当量」对应的动量。
        5. 奇异矩阵（例如两颗 TNT 的落点方向重合）时 solve 抛 LinAlgError，
           跳过该 tick，不中断整轮搜索。
        6. 这里不过滤负数当量：负解也保留在结果里，是否可用交给界面/调用方判断。
    """

    ox, oy, oz = origin
    tx, ty, tz = target
    x0, z0 = direction_origin

    # 先定方向，拿到三颗 TNT 的 3x3 动量矩阵与方向码。
    motion, code = load_motion(tx, tz, x0, z0)
    label = DIRECTION_CODE_TABLE[code]

    rows: list[dict] = []
    # 从预计飞行时间开始连续往后再试 MAX_ROWS 个 gt。
    for tick in range(int(flight_time), int(flight_time) + MAX_ROWS):
        # 100 = 1 / (1 - 0.99)；(1 - 0.99**tick) 是阻尼累计系数。
        factor = 100 * (1 - 0.99**tick)
        px = (tx - ox) / factor
        # py 用 (factor - 3) 做除数，与递推式的严格反解不等价（旧版写法，复刻不改）。
        py = (ty - oy + 3 * tick) / (factor - 3)
        pz = (tz - oz) / factor

        # 增广矩阵：每行一个轴，最后一列是该轴需要的总动量，前 3 列是三颗 TNT 的贡献。
        matrix = np.vstack((motion, np.array([px, py, pz]))).T
        try:
            solution = np.linalg.solve(matrix[:, :-1], matrix[:, -1])
        except np.linalg.LinAlgError:
            continue

        # 取整：与珍珠炮相同的银行家舍入，保证两套工具的取整行为一致。
        tnt = [int(round(float(v))) for v in solution]
        # 用整数当量回算真实动量，供界面显示与实际配置一致。
        real_px = float(sum(tnt[i] * motion[i, 0] for i in range(3)))
        real_py = float(sum(tnt[i] * motion[i, 1] for i in range(3)))
        real_pz = float(sum(tnt[i] * motion[i, 2] for i in range(3)))

        rows.append(
            {
                "tick": tick,
                "t1": tnt[0],
                "t2": tnt[1],
                "t3": tnt[2],
                "mx": real_px,
                "my": real_py,
                "mz": real_pz,
                # 整批候选共享同一个方向码 / 方位名，不随 tick 变化。
                "dirCode": code,
                "dirLabel": label,
            }
        )
    return rows
