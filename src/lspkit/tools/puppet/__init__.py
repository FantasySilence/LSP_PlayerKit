# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 假人搬货工具入口         #
# =================================== #

"""
假人搬货工具的包入口。

工具注册表 import 本包后，读取 MANIFEST（元信息）、HANDLERS（动作函数表）
与 LEGACY（旧设置迁移钩子），不需要再碰内部模块。
"""

from .manifest import HANDLERS, LEGACY, MANIFEST

__all__ = ["MANIFEST", "HANDLERS", "LEGACY"]
