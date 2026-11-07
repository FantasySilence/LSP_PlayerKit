# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 平台层公共能力           #
# =================================== #
# 本文件职责：把平台层各模块汇总导出，让上层统一用 lspkit.platform.xxx 访问。
# 这里只有 re-export，不含实现；导入顺序也大致对应阅读顺序。

# ------ 对外导出的子模块 ------ #
# locator=决定数据写到哪  params=请求参数校验  registry=工具注册表
# schema=设置字段描述    storage=数据目录/配置包  store=配置读写与备份

from lspkit.platform import locator, params, registry, schema, storage, store

# 显式声明公开名字，避免 from lspkit.platform import * 时把内部符号带出去
__all__ = ["locator", "params", "registry", "schema", "storage", "store"]
