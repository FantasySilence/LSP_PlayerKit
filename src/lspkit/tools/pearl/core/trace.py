# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 珍珠飞行轨迹递推         #
# =================================== #

# 珍珠飞行轨迹递推：按「先位移、再衰减速度」逐 gt 生成点列，并提供落地判定与
# 单炮模拟；坐标单位方块，时间单位 gt。
from __future__ import annotations

import numpy as np

from ..constants import DAMPING, DIRECTION_MATRICES, GRAVITY, GROUND_Y


# ------ 轨迹生成 ------ #
def generate(
    x0: float,
    z0: float,
    tnt_num: np.ndarray,
    direction: str,
    max_ticks: int,
    mode: str = "flat",
    settings: dict | None = None,
) -> list[dict]:
    """逐 gt 递推珍珠轨迹。

    参数:
        x0: 炮口 X 坐标，单位方块。
        z0: 炮口 Z 坐标，单位方块。
        tnt_num: [蓝, 红] TNT 数量，单位个，顺序必须与方向矩阵的列一致。
        direction: east / west / north / south，决定使用哪一组符号矩阵。
        max_ticks: 递推的 gt 数；返回点数为 max_ticks + 1（含 t=0 的出膛点）。
        mode: "flat" 平射 / "eject" 抛射，决定读取哪一组弹道参数。
        settings: 当前设置；None 视为空字典（调用方需保证对应分块存在）。

    返回:
        [{t, x, y, z}, ...]，t 单位 gt，坐标单位方块，t=0 为出膛点。

    说明:
        递推顺序固定为「先按当前速度位移，再更新速度」：水平 v ← 0.99 v，
        垂直 v ← 0.99 v - 0.03（先乘阻尼、再减重力，终端速度 -3）。
        np.float32(DAMPING) / np.float32(GRAVITY) 不是为了提速：0.99 与 0.03 存成
        float32 后是 0.9900000095... / 0.0299999993...，这正是旧版使用的精度；
        换回 float64 的 0.99 / 0.03 会让轨迹在几十 gt 后偏离黄金快照。
    """

    settings = settings or {}
    matrix = np.array(DIRECTION_MATRICES[direction], dtype=float)

    # 两种模式目前只有读取的配置块不同，公式完全一致；分开写是为了与旧版
    # 一一对应，也让以后按模式分化（例如抛射单独加重力项）时不必再拆函数。
    if mode == "eject":
        cfg = settings["eject"]
        # 初始位置：X / Z 取炮口，Y 取出膛高度（方块）。
        x = x_init = x0
        z = z_init = z0
        y = y_init = cfg["yInitPosition"]
        # 水平动量 = 单 TNT 动量 * 矩阵 * 当量；垂直动量 = 每个 TNT 的 Y 动量 * 总数 + 初速。
        motion = cfg["xzMotion"] * matrix.dot(tnt_num)
        x_motion, z_motion = motion[0], motion[1]
        y_motion = cfg["yMotion"] * sum(tnt_num) + cfg["yInitMotion"]
    else:
        cfg = settings["flat"]
        x = x_init = x0
        z = z_init = z0
        y = y_init = cfg["yInitPosition"]
        motion = cfg["xzMotion"] * matrix.dot(tnt_num)
        x_motion, z_motion = motion[0], motion[1]
        y_motion = cfg["yMotion"] * sum(tnt_num) + cfg["yInitMotion"]

    # 第 0 个点是出膛位置，之后每个 gt 追加一个点。
    points = [{"t": 0, "x": float(x_init), "y": float(y_init), "z": float(z_init)}]
    for tick in range(1, int(max_ticks) + 1):
        # 先用「上一 gt 的速度」位移，再按阻尼/重力更新速度（顺序不能反）。
        x = x + x_motion
        y = y + y_motion
        z = z + z_motion
        x_motion = np.float32(DAMPING) * x_motion
        y_motion = np.float32(DAMPING) * y_motion - np.float32(GRAVITY)
        z_motion = np.float32(DAMPING) * z_motion
        points.append(
            {"t": tick, "x": float(x), "y": float(y), "z": float(z)}
        )
    return points


# ------ 落地判定与模拟入口 ------ #
def find_landing(points: list[dict], ground_y: float = GROUND_Y) -> dict | None:
    """
    轨迹里第一个落到地面（y <= ground_y）的点；未落地返回 None.

    Y 只用来判断落地时刻，水平位置仍由 TNT 当量决定（与旧版一致）。
    """

    # 逐点扫描，第一个满足 y <= ground_y 的点即落地；都不满足说明还在空中。
    for point in points:
        if point["y"] <= ground_y:
            return {
                "tick": int(point["t"]),
                "x": float(point["x"]),
                "y": float(point["y"]),
                "z": float(point["z"]),
            }
    return None


def simulate(
    x0: float,
    z0: float,
    tnt_num: np.ndarray,
    direction: str,
    max_ticks: int,
    mode: str = "flat",
    settings: dict | None = None,
    ground_y: float = GROUND_Y,
) -> dict:
    """
    按「蓝 / 红 TNT 数量 + 方向」直接模拟一炮，并给出落地信息.

    返回 points / landing（未落地为 None）/ distance（水平距离，落点或终点）.
    """

    # 先递推完整轨迹，再做落地判定；两步分开是为了让 trace 动作也能复用 generate。
    points = generate(
        x0, z0, tnt_num, direction, max_ticks, mode=mode, settings=settings
    )
    landing = find_landing(points, ground_y)
    last = points[-1]
    # 没落地就用轨迹最后一点算水平距离（相对于炮口，单位方块）。
    end = landing or last
    distance = float(np.hypot(end["x"] - x0, end["z"] - z0))
    return {
        "points": points,
        "landing": landing,
        "distance": distance,
        "groundY": float(ground_y),
        "simulatedTicks": int(last["t"]),
    }
