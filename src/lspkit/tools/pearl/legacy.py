# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 旧版珍珠炮配置迁移       #
# =================================== #

from __future__ import annotations


# 旧版珍珠炮配置迁移：把 Tkinter 版 JSON 的全大写键翻译成新 schema 的点号结构；
# 文件里没有 MOTION_FOR_FLAT_FIRE 键时视为已是新格式，原样返回，避免二次迁移。


# ------ 取值与键名翻译 ------ #
# 注意：convert 走的是扁平的 raw.get，这个按路径取值的小工具目前没有被调用，
# 保留它是为了兼容旧版可能出现的嵌套配置路径，删掉不影响当前迁移结果。
def _get(raw: dict, *path, default=None):
    """按路径逐层读取嵌套字典，任一环缺失或类型不对就返回 default。

    参数:
        raw: 待读取的原始字典（旧版 JSON 根对象）。
        *path: 逐层的键名，例如 ("flat", "XZ_MOTION")。
        default: 任一层取不到时返回的值；不做类型转换。

    返回:
        命中的值（可能是 dict），或 default。
    """

    node = raw
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def convert(raw: dict) -> dict:
    """把旧版珍珠炮配置转换成新版设置结构（键名从全大写改为驼峰/点号路径）。

    参数:
        raw: 旧版 JSON 的根字典；也可能已经是新格式。

    返回:
        新格式设置字典；若 raw 里没有 MOTION_FOR_FLAT_FIRE，说明它已是新格式，
        直接原样返回（不做任何键名猜测，避免把新配置改坏）。
    """

    # 这个键是旧版配置的「指纹」：只有在旧文件里才会出现。
    if "MOTION_FOR_FLAT_FIRE" not in raw:
        return raw
    # 三个子对象都可能缺失，用 or {} 兜底后再逐项取值。
    flat = raw.get("MOTION_FOR_FLAT_FIRE") or {}
    eject = raw.get("MOTION_FOR_EJECTIONS") or {}
    position = raw.get("XZ_INIT_POSITION") or {}
    return {
        # 默认值写死为出厂设置：旧版文件缺项时与 DEFAULT_SETTINGS 保持一致。
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
