# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 边境炮方向判定           #
# =================================== #

from __future__ import annotations

import numpy as np

from ..constants import DIRECTION_TABLE


def _points(x: float, z: float) -> tuple[str, list[str]]:
    """
    x/z 已相对炮口平移.
    """

    if z < x and x >= 0 and z >= 0:
        return "000", ["NWD", "NWU", "SWU"]
    if z >= x and x > 0 and z >= 0:
        return "100", ["NWD", "NWU", "NEU"]
    if z > -x and x <= 0 and z >= 0:
        return "101", ["NED", "NEU", "NWU"]
    if z <= -x and x <= 0 and z > 0:
        return "111", ["NED", "NEU", "SEU"]
    if z > x and x <= 0 and z <= 0:
        return "110", ["SED", "SEU", "NEU"]
    if z <= x and x < 0 and z <= 0:
        return "010", ["SED", "SEU", "SWU"]
    if z >= -x and x >= 0 and z < 0:
        return "001", ["SWD", "SWU", "NWU"]
    if z < -x and x >= 0 and z <= 0:
        return "011", ["SWD", "SWU", "SEU"]
    # 与炮口重合等退化情况：沿用东南向，避免旧版 UnboundLocalError
    return "000", ["NWD", "NWU", "SWU"]


def get_direction(
    x: float, z: float, origin_x: float, origin_z: float
) -> tuple[np.ndarray, str]:
    code, landing_points = _points(x - origin_x, z - origin_z)

    direction = np.zeros((3, 3), dtype=int)
    for i, point in enumerate(landing_points):
        # 旧版编码顺序与处理顺序差一位，这里保持一致
        true_point = point[1:] + point[0]
        for j, letter in enumerate(true_point):
            direction[i][j] = DIRECTION_TABLE[letter]

    return direction, code
