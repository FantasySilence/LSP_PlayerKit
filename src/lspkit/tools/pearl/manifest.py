# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 珍珠炮 manifest          #
# =================================== #

# 珍珠炮的静态清单：id、i18n key、图标、侧边栏排序、版本、设置 schema、动作按钮与
# 结果表格列；同时把「动作名 → 处理函数」和旧配置迁移函数绑定好，交给平台注册表。
from lspkit.platform.registry import ToolManifest

from .actions import calculate_action, decode_action, simulate_action, trace_action
from .legacy import convert
from .schema import SCHEMA

# ------ 清单与处理器注册 ------ #
MANIFEST = ToolManifest(
    id="pearl",
    name_key="pearl.name",
    description_key="pearl.description",
    icon="pearl",
    # 侧边栏排序值，越小越靠前（边境炮 border 为 20）。
    order=10,
    version="1.1.5",
    schema=SCHEMA,
    # 界面上显示的动作按钮；simulate 不在其中，只能通过 api.tool_call 直接指定 action。
    actions=[
        {"id": "calculate", "labelKey": "pearl.action.calculate"},
        {"id": "decode", "labelKey": "pearl.action.decode"},
        {"id": "trace", "labelKey": "pearl.action.trace"},
    ],
    # 结果表格列：error 为落点偏差（方块，6 位小数），其余为数量（个）与时间（gt）。
    columns=[
        {"key": "error", "nameKey": "pearl.col.error", "type": "float", "digits": 6},
        {"key": "ticks", "nameKey": "pearl.col.ticks", "type": "int"},
        {"key": "blue", "nameKey": "pearl.col.blue", "type": "int"},
        {"key": "red", "nameKey": "pearl.col.red", "type": "int"},
        {"key": "total", "nameKey": "pearl.col.total", "type": "int"},
    ],
)

# 动作名 → 处理函数：平台按此分发 api.tool_call 的 action 参数。
HANDLERS = {
    "calculate": calculate_action,
    "decode": decode_action,
    "trace": trace_action,
    "simulate": simulate_action,
}

# 导入旧配置时调用的迁移函数。
LEGACY = convert
