# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 旧配置迁移               #
# =================================== #
# 没有历史格式时直接返回原对象即可。
# Registry.convert_legacy 在读取旧存档时调用本函数，返回值随后会过一遍
# SettingsSchema.validate（补默认值 + 强制类型），因此这里不必补默认值。

from __future__ import annotations

# ------ 迁移入口 ------ #


def convert(raw: dict) -> dict:
    """
    旧版设置 → 当前 schema 能接受的设置，原样返回表示无需迁移.

    若新版本改了字段名 / 枚举取值，就在这里做键名映射与取值转换，
    并保持幂等（对已经是新格式的配置再调用一次也不出错）。
    """

    return raw
