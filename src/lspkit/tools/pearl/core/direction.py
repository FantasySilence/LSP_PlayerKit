# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 珍珠炮方向判定           #
# =================================== #

# 珍珠炮方向判定：把「目标 - 炮口」的位移旋转 45° 后看落在哪个象限，据此选方向名，
# 并取出该象限固定的 2x2 符号矩阵 —— 求解器用它把 (蓝, 红) 映射成 (X, Z) 动量。
from __future__ import annotations

import numpy as np

from ..constants import DIRECTION_MATRICES


# ------ 象限判定与矩阵查表 ------ #
class Directions:
    """方向判定的命名空间：只有一个静态方法，不需要实例化。"""

    @staticmethod
    def judge(x_target: float, z_target: float, x0: float, z0: float):
        """判断目标相对炮口的方位，并返回该方位的动量符号矩阵。

        参数:
            x_target: 目标 X 坐标，单位方块。
            z_target: 目标 Z 坐标，单位方块。
            x0: 炮口 X 坐标，单位方块。
            z0: 炮口 Z 坐标，单位方块。

        返回:
            (方向名, 2x2 矩阵)；方向名取 east / west / north / south，
            矩阵是 float64 的 numpy 数组，行是 X / Z 轴、列是蓝 / 红 TNT 数量。

        说明:
            先旋转 45° 是为了让沿对角线摆放的 TNT 与坐标轴对齐，这样四个象限的
            符号组合只剩 ±1 四种，可直接查 DIRECTION_MATRICES，不必逐点三角函数。
        """

        # 位移向量（目标 - 炮口），单位方块。
        destination = np.array([x_target - x0, z_target - z0])
        # 取转置后左乘，等价于把位移顺时针旋转 45°（旧版写法，不要改成 R·d）。
        rotate = np.array(
            [
                [np.cos(np.pi / 4), -np.sin(np.pi / 4)],
                [np.sin(np.pi / 4), np.cos(np.pi / 4)],
            ]
        ).T
        rotated = np.dot(rotate, destination)

        # 四个分支的 >=0 / >0 交错，保证平面被完整划分且互不重叠；
        # 正好落在轴或对角线上时归属固定的一侧，不会两个象限同时命中。
        if rotated[0] >= 0 and rotated[1] < 0:
            direction = "east"
        elif rotated[0] > 0 and rotated[1] >= 0:
            direction = "south"
        elif rotated[0] <= 0 and rotated[1] > 0:
            direction = "west"
        else:
            direction = "north"

        # 符号矩阵按方向名查表后转成 float，供后续线性方程直接使用。
        return direction, np.array(DIRECTION_MATRICES[direction], dtype=float)
