# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 工具 manifest            #
# =================================== #

# manifest 是工具对平台的全部声明，前端据此渲染侧栏入口、动作按钮、结果表格，
# 平台据此建立设置界面。计算逻辑一律不写在这里。

from lspkit.platform.registry import ToolManifest

from .actions import my_action
from .legacy import convert
from .schema import SCHEMA

# ------ 工具声明 ------ #
# 复制后逐项替换：id（与 web/src/tools/<id>/ 目录名一致）、三语键、icon、order、
# version。actions 的 id 与 HANDLERS 的键一一对应；columns 的 key 对应动作返回值
# items[] 里的字段，type 取 string / int / float，浮点再加 digits 控制小数位。

MANIFEST = ToolManifest(
    id="my-tool",                    # 必须与 web/src/tools/<id>/ 目录名一致
    name_key="my-tool.name",
    description_key="my-tool.description",
    icon="spark",                    # 见 App.vue 的 ICONS
    order=50,
    version="0.1.0",
    schema=SCHEMA,
    actions=[{"id": "my_action", "labelKey": "my-tool.action.myAction"}],
    columns=[
        {"key": "value", "nameKey": "my-tool.col.value", "type": "float", "digits": 4},
    ],
)

# ------ 注册表对接 ------ #
# HANDLERS：动作 id → 处理函数；LEGACY：旧配置迁移函数
HANDLERS = {"my_action": my_action}

LEGACY = convert
