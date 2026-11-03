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

from ..constants import DAMPING, DIRECTION_MATRICES, GRAVITY


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
