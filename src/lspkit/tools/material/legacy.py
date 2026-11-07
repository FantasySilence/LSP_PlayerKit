# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 材料换算旧配置迁移       #
# =================================== #

# 每个工具都要有 legacy 入口：Registry.convert_legacy 在读取旧存档时调用它，
# 把历史版本的配置格式整理成当前 schema 能接受的样子。

from __future__ import annotations

# ------ 迁移入口 ------ #


def convert(raw: dict) -> dict:
    """
    材料换算没有历史配置格式，原样返回.

    返回值会被 SettingsSchema.validate 再校验一遍，因此这里不需要补默认值；
    将来若要改字段名或枚举取值，应在这一步做键名映射，而不是在读取处加分支。
    """

    return raw
