# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 珍珠飞行轨迹递推         #
# =================================== #

from __future__ import annotations

import numpy as np

from ..constants import DAMPING, DIRECTION_MATRICES, GRAVITY, GROUND_Y


def generate(
    x0: float,
    z0: float,
    tnt_num: np.ndarray,
    direction: str,
    max_ticks: int,
    mode: str = "flat",
    settings: dict | None = None,
) -> list[dict]:
    settings = settings or {}
    matrix = np.array(DIRECTION_MATRICES[direction], dtype=float)

    if mode == "eject":
        cfg = settings["eject"]
        x = x_init = x0
        z = z_init = z0
        y = y_init = cfg["yInitPosition"]
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

    points = [{"t": 0, "x": float(x_init), "y": float(y_init), "z": float(z_init)}]
    for tick in range(1, int(max_ticks) + 1):
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


def find_landing(points: list[dict], ground_y: float = GROUND_Y) -> dict | None:
    """
    轨迹里第一个落到地面（y <= ground_y）的点；未落地返回 None.

    Y 只用来判断落地时刻，水平位置仍由 TNT 当量决定（与旧版一致）。
    """

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

    points = generate(
        x0, z0, tnt_num, direction, max_ticks, mode=mode, settings=settings
    )
    landing = find_landing(points, ground_y)
    last = points[-1]
    end = landing or last
    distance = float(np.hypot(end["x"] - x0, end["z"] - z0))
    return {
        "points": points,
        "landing": landing,
        "distance": distance,
        "groundY": float(ground_y),
        "simulatedTicks": int(last["t"]),
    }
