# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 单个 TNT 的动量          #
# =================================== #

# 单个 TNT 的动量：把「方向判定 + 动量查表」合成一步，供三元求解与手动预报复用。
from __future__ import annotations

import numpy as np

from .direction import get_direction, motion_of


# ------ 动量加载 ------ #
def load_motion(
    x: float, z: float, origin_x: float, origin_z: float
) -> tuple[np.ndarray, str]:
    """由目标点与方向参考点算出 3x3 动量矩阵和方向码。

    参数:
        x: 目标 X 坐标，单位方块。
        z: 目标 Z 坐标，单位方块。
        origin_x: 方向参考点 X 坐标，单位方块（炮口，或旧版写死的 10000）。
        origin_z: 方向参考点 Z 坐标，单位方块。

    返回:
        (3x3 动量矩阵, 方向码 "000".."111")；矩阵行是第 i 颗 TNT、列是 X / Y / Z，
        每个元素是该颗 TNT 单独贡献的动量（方块/gt）。

    说明:
        这是 calculate 唯一的方向入口：方向一旦定下，后面的线性方程组就只解当量。
    """

    directions, code = get_direction(x, z, origin_x, origin_z)
    return motion_of(directions), code
