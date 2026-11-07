# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 旧版边境炮配置迁移       #
# =================================== #

# 旧版边境炮配置迁移：把 Tkinter 版 JSON 的 default_* 键改名成新的驼峰结构；
# 文件里没有 default_x_init 时视为已是新格式，原样返回，避免重复迁移。
from __future__ import annotations


# ------ 旧键名翻译 ------ #
def convert(raw: dict) -> dict:
    """把旧版边境炮配置转换成新版设置结构。

    参数:
        raw: 旧版 JSON 的根字典；也可能已经是新格式。

    返回:
        新格式设置字典（坐标与目标单位方块，flightTime 单位 gt）；
        若 raw 里没有 default_x_init（旧版指纹），直接原样返回。

    说明:
        所有取值都带默认值兜底，并且显式 float / int 转型，避免旧文件里
        存成字符串或带小数的整数把后续 schema 校验搞崩。
    """

    # 旧版键名统一以 default_ 开头，缺这个键就认为配置已是新格式。
    if "default_x_init" not in raw:
        return raw
    return {
        "originX": float(raw.get("default_x_init", 9996.24)),
        "originY": float(raw.get("default_y_init", 256)),
        "originZ": float(raw.get("default_z_init", 9999.24)),
        "targetX": float(raw.get("default_x_target", 0)),
        "targetY": float(raw.get("default_y_target", 128)),
        "targetZ": float(raw.get("default_z_target", 0)),
        # 旧文件可能写成 1200.0，先转 float 再取整，保证迁移后是 int。
        "flightTime": int(float(raw.get("default_flying_time", 1200))),
        # 旧版方向判断写死炮口，迁移时保留原行为
        "directionMode": "fixed",
    }
