# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 单个 TNT 的动量          #
# =================================== #

from __future__ import annotations

import numpy as np

from ..constants import MOTION_PER_TNT
from .direction import get_direction


def load_motion(
    x: float, z: float, origin_x: float, origin_z: float
) -> tuple[np.ndarray, str]:
    directions, code = get_direction(x, z, origin_x, origin_z)
    motion = np.zeros((3, 3), dtype=float)

    for i in range(directions.shape[0]):
        if directions[i, 1] == -1:  # 落在海泡菜上
            kind = "D"
        else:  # 落在栅栏门上
            kind = "U"
        motion[i, 0] = MOTION_PER_TNT[kind]["X"] * directions[i, 0]
        motion[i, 1] = MOTION_PER_TNT[kind]["Y"]
        motion[i, 2] = MOTION_PER_TNT[kind]["Z"] * directions[i, 2]

    return motion, code
