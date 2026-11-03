# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 旧版珍珠炮配置迁移       #
# =================================== #

from __future__ import annotations


def _get(raw: dict, *path, default=None):
    node = raw
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def convert(raw: dict) -> dict:
    if "MOTION_FOR_FLAT_FIRE" not in raw:
        return raw
    flat = raw.get("MOTION_FOR_FLAT_FIRE") or {}
    eject = raw.get("MOTION_FOR_EJECTIONS") or {}
    position = raw.get("XZ_INIT_POSITION") or {}
    return {
        "maxTnt": raw.get("MAX_TNT", 3640),
        "tntPerUnit": raw.get("MAX_TNT_UNIT", 260),
        "originX": position.get("X", -31.9375),
        "originZ": position.get("Z", -8.0625),
        "ejectionAvailable": raw.get("IS_EJECTION_AVAILABLE", True),
        "flat": {
            "xzMotion": flat.get("XZ_MOTION", 0.6025678975452011),
            "yMotion": flat.get("Y_MOTION", -0.0011162018688096187),
            "yInitMotion": flat.get("Y_INIT_MOTION", 0.2716278719434352),
            "yInitPosition": flat.get("Y_INIT_POSITION", 178.34722638929412),
        },
        "eject": {
            "xzMotion": eject.get("XZ_MOTION", 0.6026063622295216),
            "yMotion": eject.get("Y_MOTION", 0.000639233791587035),
            "yInitMotion": eject.get("Y_INIT_MOTION", 0.6909788463066233),
            "yInitPosition": eject.get("Y_INIT_POSITION", 178.41212248815643),
        },
    }
