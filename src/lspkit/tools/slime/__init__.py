# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-07                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 史莱姆区块查找器入口      #
# =================================== #
"""史莱姆区块查找器包：对外只暴露三样东西.

- MANIFEST：工具元数据（id、图标、schema、列定义、动作 label key）；
- HANDLERS：动作 id → 处理函数，平台按 id 分发请求；
- LEGACY：旧版兼容入口，本工具没有，为 None。
"""

from .manifest import HANDLERS, LEGACY, MANIFEST

__all__ = ["MANIFEST", "HANDLERS", "LEGACY"]
