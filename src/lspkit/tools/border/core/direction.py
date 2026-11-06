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

from ..constants import DIRECTION_POINTS, DIRECTION_TABLE, MOTION_PER_TNT


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


def _directions(points: list[str]) -> np.ndarray:
    """三个落点 → 3x3 方向矩阵（旧版编码顺序与处理顺序差一位，这里保持一致）."""

    direction = np.zeros((3, 3), dtype=int)
    for i, point in enumerate(points):
        true_point = point[1:] + point[0]
        for j, letter in enumerate(true_point):
            direction[i][j] = DIRECTION_TABLE[letter]
    return direction


def motion_of(directions: np.ndarray) -> np.ndarray:
    """方向矩阵 → 三个 TNT 各自的三轴动量."""

    motion = np.zeros((3, 3), dtype=float)
    for i in range(directions.shape[0]):
        if directions[i, 1] == -1:  # 落在海泡菜上
            kind = "D"
        else:  # 落在栅栏门上
            kind = "U"
        motion[i, 0] = MOTION_PER_TNT[kind]["X"] * directions[i, 0]
        motion[i, 1] = MOTION_PER_TNT[kind]["Y"]
        motion[i, 2] = MOTION_PER_TNT[kind]["Z"] * directions[i, 2]

    return motion


def get_direction(
    x: float, z: float, origin_x: float, origin_z: float
) -> tuple[np.ndarray, str]:
    code, landing_points = _points(x - origin_x, z - origin_z)
    return _directions(landing_points), code


def motion_from_code(code: str) -> np.ndarray:
    """
    按用户手选的方向码取 3x3 动量矩阵（手动落点预报用）.
    """

    points = DIRECTION_POINTS.get(str(code))
    if points is None:
        raise ValueError(f"未知方向码：{code}")
    return motion_of(_directions(points))
