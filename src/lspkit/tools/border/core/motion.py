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

from .direction import get_direction, motion_of


def load_motion(
    x: float, z: float, origin_x: float, origin_z: float
) -> tuple[np.ndarray, str]:
    directions, code = get_direction(x, z, origin_x, origin_z)
    return motion_of(directions), code
