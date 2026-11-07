# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 新工具脚手架             #
# =================================== #
# 复制本目录为 tools/<your-id>/ 后按 TODO 修改。
# 不要直接注册 _template 本身。

# ------ 目录约定 ------ #
# 一个工具由下面几层组成，复制后逐项替换即可（括号内为是否必留）：
#   __init__.py   只做导出（必留）：把 MANIFEST / HANDLERS / LEGACY 交给注册表
#   manifest.py   工具声明（必留）：id、三语名称键、图标、顺序、动作、结果列、schema
#   actions.py    动作处理（必留）：参数校验 + 调用 core，出错抛 AppError
#   schema.py     设置字段（必留）：决定设置面板长什么样、有哪些可调项
#   defaults.py   出厂默认值（建议）：schema 里 default 的唯一来源
#   legacy.py     旧配置迁移（必留）：没有历史格式时原样返回
#   constants.py  工具常量（可选）：阈值、正则等纯数据
#   core/         纯计算（可选）：不依赖 webview / 文件 / 存储，便于单独测试
# 复制完成后还要做三件事：
#   1. 在 tools/__init__.py 的 build_registry() 里 import 并 register 本工具；
#   2. 在 web/src/tools/<your-id>/ 建前端页面，目录名必须与 manifest 的 id 一致；
#   3. 在该目录的 i18n/zh_CN.json、zh_TW.json、en.json 里补齐 manifest 用到的键，
#      以及 constants.py 等杂项中出现的所有 name_key / labelKey。
# 本文件保持只做导出，不要在这里写逻辑，避免循环 import。
