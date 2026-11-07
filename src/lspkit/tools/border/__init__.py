# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 边境炮工具包             #
# =================================== #

# 边境炮子包的统一出口：把 manifest 里登记的 MANIFEST / HANDLERS / LEGACY 再导出一次，
# 启动时由 lspkit.platform.registry 按这三个对象注册 "border" 工具。

# ------ 包级导出 ------ #
from .manifest import HANDLERS, LEGACY, MANIFEST

__all__ = ["MANIFEST", "HANDLERS", "LEGACY"]
