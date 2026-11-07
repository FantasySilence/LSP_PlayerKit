# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 边境炮方向判定           #
# =================================== #

# 边境炮方向判定：先看「目标 - 炮口」落在 8 个 45° 扇区的哪一个，得到方向码与
# 三颗 TNT 的落点组合，再查 MOTION_PER_TNT 换算出 3x3 动量矩阵。
from __future__ import annotations

import numpy as np

from ..constants import DIRECTION_POINTS, DIRECTION_TABLE, MOTION_PER_TNT


# ------ 扇区判定 ------ #
def _points(x: float, z: float) -> tuple[str, list[str]]:
    """
    x/z 已相对炮口平移.
    """

    # 参数: x / z 是相对参考点的位移（方块）；返回 (方向码, 三颗 TNT 的落点字母列表)。
    # 8 条分支覆盖由对角线（z = x、z = -x）与坐标轴切出的 8 个 45° 扇区；
    # 顺序沿用旧版 if-elif（从东南偏东开始绕一圈），不能重排。
    # 严格 / 非严格不等号交错，保证任意一点只会命中一条分支。
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


# ------ 落点 → 方向矩阵 → 动量 ------ #
def _directions(points: list[str]) -> np.ndarray:
    """三个落点 → 3x3 方向矩阵（旧版编码顺序与处理顺序差一位，这里保持一致）."""

    # 参数 points: 三个三字母落点（如 "NWD"）；返回 3x3 int 矩阵，元素为 ±1。
    direction = np.zeros((3, 3), dtype=int)
    for i, point in enumerate(points):
        # 旧版把三字母循环左移一位（"NWD" → "WDN"），正好把书写顺序 N/S、E/W、U/D
        # 变成矩阵需要的 X、Y、Z 列序；这是历史编码顺序，保持原样。
        true_point = point[1:] + point[0]
        for j, letter in enumerate(true_point):
            direction[i][j] = DIRECTION_TABLE[letter]
    return direction


def motion_of(directions: np.ndarray) -> np.ndarray:
    """方向矩阵 → 三个 TNT 各自的三轴动量."""

    # 参数 directions: 3x3 的 ±1 方向矩阵；返回 3x3 float 动量矩阵（方块/gt）。
    motion = np.zeros((3, 3), dtype=float)
    for i in range(directions.shape[0]):
        # 第二列是 Y 轴符号：-1 表示落在海泡菜上（向下弹 D），否则落在栅栏门上（U）。
        if directions[i, 1] == -1:  # 落在海泡菜上
            kind = "D"
        else:  # 落在栅栏门上
            kind = "U"
        # X / Z 乘 ±1 决定朝向；Y 不乘符号，两种落点直接对应两套固定常量。
        motion[i, 0] = MOTION_PER_TNT[kind]["X"] * directions[i, 0]
        motion[i, 1] = MOTION_PER_TNT[kind]["Y"]
        motion[i, 2] = MOTION_PER_TNT[kind]["Z"] * directions[i, 2]

    return motion


def get_direction(
    x: float, z: float, origin_x: float, origin_z: float
) -> tuple[np.ndarray, str]:
    """由目标点与参考点求出方向矩阵与方向码。

    参数:
        x: 目标 X 坐标，单位方块。
        z: 目标 Z 坐标，单位方块。
        origin_x: 参考点 X 坐标，单位方块。
        origin_z: 参考点 Z 坐标，单位方块。

    返回:
        (3x3 方向矩阵, 方向码)；矩阵元素为 ±1，行列含义见 _directions。

    说明:
        先把坐标平移到参考点再判扇区，所以调用方直接传世界坐标即可。
    """

    code, landing_points = _points(x - origin_x, z - origin_z)
    return _directions(landing_points), code


def motion_from_code(code: str) -> np.ndarray:
    """
    按用户手选的方向码取 3x3 动量矩阵（手动落点预报用）.
    """

    # 参数 code: 方向码字符串；返回 3x3 float 动量矩阵（方块/gt）；未知码抛 ValueError。
    # 手选方向时没有目标点，直接查 DIRECTION_POINTS 拿三个落点，再走同一条动量换算路径。
    points = DIRECTION_POINTS.get(str(code))
    if points is None:
        raise ValueError(f"未知方向码：{code}")
    return motion_of(_directions(points))
