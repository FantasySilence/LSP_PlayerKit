# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 珍珠炮专用常量           #
# =================================== #

from __future__ import annotations

MAX_TICKS = 300
FLAT_TUNING = range(-2, 3)
EJECT_TUNING = range(-10, 11)
EJECT_TARGET_Y = 128
EJECT_Y_WINDOW = (128, 129)

DAMPING = 0.99
GRAVITY = 0.03

# 手动模拟的落地高度（Y 坐标）；轨迹里第一次低于它就视为落地
GROUND_Y = 0.0
MAX_SIM_TICKS = 600

# 45° 旋转后的四象限 → 方向与动量矩阵
DIRECTION_MATRICES = {
    "east": [[1, 1], [-1, 1]],
    "west": [[-1, -1], [-1, 1]],
    "north": [[1, -1], [-1, -1]],
    "south": [[1, -1], [1, 1]],
}
