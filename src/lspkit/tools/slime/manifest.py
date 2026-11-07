# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-07                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 史莱姆区块查找器 manifest #
# =================================== #
"""
工具注册信息：平台靠 MANIFEST 发现工具、靠 HANDLERS 分发动作。

字段含义：
- id / name_key / description_key：工具标识与 i18n 键；
- icon / order / version：图标名、在工具箱里的排序号、版本号；
- schema：设置面板的字段声明（见 schema.py）；
- actions：暴露给前端按钮栏的动作（id + labelKey），只列主动作，
  scan_status / scan_stop / map / seed_preview 由调用方在流程里按需调用；
- columns：结果表格的列定义，type 决定前端渲染方式，digits 是小数位数。

HANDLERS 的键必须与前端发来的 action 名一致；LEGACY 是旧版兼容入口，
本工具没有历史接口，所以是 None。
"""

from lspkit.platform.registry import ToolManifest

from .actions import (
    find_action,
    map_action,
    scan_start,
    scan_status,
    scan_stop,
    seed_preview,
)
from .schema import SCHEMA

MANIFEST = ToolManifest(
    id="slime",
    name_key="slime.name",
    description_key="slime.description",
    icon="slime",
    order=50,
    version="1.0.0",
    schema=SCHEMA,
    actions=[
        # 按钮栏只放两个主动作：同步小范围查找、后台扫描
        {"id": "find", "labelKey": "slime.action.find"},
        {"id": "scan_start", "labelKey": "slime.action.scan"},
    ],
    columns=[
        # 结果表列：名次、方块坐标、得分（格²）与覆盖率
        {"key": "rank", "nameKey": "slime.col.rank", "type": "int"},
        {"key": "x", "nameKey": "slime.col.x", "type": "int"},
        {"key": "z", "nameKey": "slime.col.z", "type": "int"},
        {"key": "score", "nameKey": "slime.col.score", "type": "int"},
        {"key": "coverage", "nameKey": "slime.col.coverage", "type": "float", "digits": 3},
    ],
)

# 动作 id → 处理函数：键名与前端请求里的 action 字段一一对应
HANDLERS = {
    "find": find_action,
    "scan_start": scan_start,
    "scan_status": scan_status,
    "scan_stop": scan_stop,
    "map": map_action,
    "seed_preview": seed_preview,
}

# 旧版兼容入口：本工具没有历史接口
LEGACY = None
