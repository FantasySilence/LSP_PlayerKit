# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 材料换算工具入口         #
# =================================== #

# ------ 对外导出 ------ #
# 工具包只向外暴露三样东西，由 tools/__init__.py 的 build_registry() 交给 Registry：
#   MANIFEST  工具元信息：id / 三语名称键 / 图标 / 动作 / 结果列 / 设置 schema
#   HANDLERS  动作 id → 处理函数，前端点「换算 / 装箱」时经 Registry.call 分发到这里
#   LEGACY    旧版配置迁移函数；本工具没有历史配置格式，原样返回
# 包内部分层：actions.py 负责请求校验，core/ 是纯计算，不依赖 webview 与存储。

from .manifest import HANDLERS, LEGACY, MANIFEST

__all__ = ["MANIFEST", "HANDLERS", "LEGACY"]
