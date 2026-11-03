# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 边境炮落点预测           #
# =================================== #

from __future__ import annotations


def predict(
    x_motion: float,
    y_motion: float,
    z_motion: float,
    origin: tuple[float, float, float],
    landing_y: float = 256.0,
) -> dict:
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

    return {"x": x, "z": z, "ticks": tick}
