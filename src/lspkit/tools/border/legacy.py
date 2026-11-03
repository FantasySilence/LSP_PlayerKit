# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 旧版边境炮配置迁移       #
# =================================== #

from __future__ import annotations


def convert(raw: dict) -> dict:
    if "default_x_init" not in raw:
        return raw
    return {
        "originX": float(raw.get("default_x_init", 9996.24)),
        "originY": float(raw.get("default_y_init", 256)),
        "originZ": float(raw.get("default_z_init", 9999.24)),
        "targetX": float(raw.get("default_x_target", 0)),
        "targetY": float(raw.get("default_y_target", 128)),
        "targetZ": float(raw.get("default_z_target", 0)),
        "flightTime": int(float(raw.get("default_flying_time", 1200))),
        # 旧版方向判断写死炮口，迁移时保留原行为
        "directionMode": "fixed",
    }
