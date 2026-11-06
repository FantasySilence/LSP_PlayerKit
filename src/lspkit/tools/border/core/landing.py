# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 边境炮落点预测           #
# =================================== #

from __future__ import annotations

LANDING_Y = 256.0


def trace(
    x_motion: float,
    y_motion: float,
    z_motion: float,
    origin: tuple[float, float, float],
    landing_y: float = LANDING_Y,
) -> dict:
    """
    逐 gt 递推，直到珍珠落到 landing_y 以下.

    返回 points（[tick, x, y, z]）与 landing（最后一刻的位置）.
    """

    x, y, z = (float(v) for v in origin)
    tick = 0
    points = [[tick, x, y, z]]

    while True:
        x = x + x_motion
        y = y + y_motion
        z = z + z_motion
        x_motion = 0.99 * x_motion
        y_motion = 0.99 * (y_motion - 0.03)
        z_motion = 0.99 * z_motion
        tick += 1
        points.append([tick, x, y, z])
        if y < landing_y:
            break

    return {
        "points": points,
        "landing": {"x": x, "y": y, "z": z, "ticks": tick},
    }


def position_at(points: list[list[float]], tick: int) -> dict | None:
    """
    取轨迹中某一 gt 的位置；该时刻已经落地（超出轨迹）则返回 None.
    """

    index = int(tick)
    if index < 0 or index >= len(points):
        return None
    point = points[index]
    return {"tick": index, "x": point[1], "y": point[2], "z": point[3]}


def predict(
    x_motion: float,
    y_motion: float,
    z_motion: float,
    origin: tuple[float, float, float],
    landing_y: float = LANDING_Y,
) -> dict:
    landing = trace(x_motion, y_motion, z_motion, origin, landing_y)["landing"]
    return {"x": landing["x"], "z": landing["z"], "ticks": landing["ticks"]}
