# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 材料换算 manifest        #
# =================================== #

# manifest 是工具对平台的全部声明：前端据此渲染侧栏入口、动作按钮、结果表格，
# 平台据此创建设置界面并校验设置。本文件不含计算逻辑。

from lspkit.platform.registry import ToolManifest

from .actions import convert_action, pack_action
from .legacy import convert
from .schema import SCHEMA

# ------ 工具声明 ------ #
# id 必须与 web/src/tools/<id>/ 目录名一致，否则前端找不到页面与 i18n；
# order 决定侧栏顺序（越小越靠前），version 显示在工具页脚。

MANIFEST = ToolManifest(
    id="material",
    name_key="material.name",
    description_key="material.description",
    icon="box",
    order=30,
    version="1.1.5",
    schema=SCHEMA,
    # 动作按钮：id 与 HANDLERS 的键一一对应，labelKey 在三语 json 里翻译
    actions=[
        {"id": "convert", "labelKey": "material.action.convert"},
        {"id": "pack", "labelKey": "material.action.pack"},
    ],
    # 结果表格列：key 对应动作返回 items[] 里的字段，type 决定对齐与格式化
    # stack 为堆叠数（个/组），count 为需求数量（个），shulkers/stacks/items 为换算结果
    columns=[
        {"key": "name", "nameKey": "material.col.name", "type": "string"},
        {"key": "stack", "nameKey": "material.col.stack", "type": "int"},
        {"key": "count", "nameKey": "material.col.count", "type": "int"},
        {"key": "shulkers", "nameKey": "material.col.shulkers", "type": "int"},
        {"key": "stacks", "nameKey": "material.col.stacks", "type": "int"},
        {"key": "items", "nameKey": "material.col.items", "type": "int"},
    ],
)

# ------ 注册表对接 ------ #
# HANDLERS：动作 id → 处理函数，Registry.call 按前端传来的 action 查表
HANDLERS = {"convert": convert_action, "pack": pack_action}

# LEGACY：旧配置迁移函数，见 legacy.py
LEGACY = convert
