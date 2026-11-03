# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 珍珠炮方向判定           #
# =================================== #

from __future__ import annotations

import numpy as np

from ..constants import DIRECTION_MATRICES


class Directions:
    @staticmethod
    def judge(x_target: float, z_target: float, x0: float, z0: float):
        destination = np.array([x_target - x0, z_target - z0])
        rotate = np.array(
            [
                [np.cos(np.pi / 4), -np.sin(np.pi / 4)],
                [np.sin(np.pi / 4), np.cos(np.pi / 4)],
            ]
        ).T
        rotated = np.dot(rotate, destination)

        if rotated[0] >= 0 and rotated[1] < 0:
            direction = "east"
        elif rotated[0] > 0 and rotated[1] >= 0:
            direction = "south"
        elif rotated[0] <= 0 and rotated[1] > 0:
            direction = "west"
        else:
            direction = "north"

        return direction, np.array(DIRECTION_MATRICES[direction], dtype=float)
