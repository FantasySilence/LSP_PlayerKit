# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 边境炮三元 TNT 求解      #
# =================================== #

from __future__ import annotations

import numpy as np

from ..constants import DIRECTION_CODE_TABLE, MAX_ROWS
from .motion import load_motion


def calculate(
    origin: tuple[float, float, float],
    target: tuple[float, float, float],
    flight_time: int,
    direction_origin: tuple[float, float],
) -> list[dict]:
    ox, oy, oz = origin
    tx, ty, tz = target
    x0, z0 = direction_origin

    motion, code = load_motion(tx, tz, x0, z0)
    label = DIRECTION_CODE_TABLE[code]

    rows: list[dict] = []
    for tick in range(int(flight_time), int(flight_time) + MAX_ROWS):
        factor = 100 * (1 - 0.99**tick)
        px = (tx - ox) / factor
        py = (ty - oy + 3 * tick) / (factor - 3)
        pz = (tz - oz) / factor

        matrix = np.vstack((motion, np.array([px, py, pz]))).T
        try:
            solution = np.linalg.solve(matrix[:, :-1], matrix[:, -1])
        except np.linalg.LinAlgError:
            continue

        tnt = [int(round(float(v))) for v in solution]
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
                "dirCode": code,
                "dirLabel": label,
            }
        )
    return rows
