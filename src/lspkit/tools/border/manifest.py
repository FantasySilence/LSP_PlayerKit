# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 边境炮 manifest          #
# =================================== #

# 边境炮的静态清单：id、i18n key、图标、侧边栏排序、版本、设置 schema、动作按钮与
# 结果表格列；同时把「动作名 → 处理函数」和旧配置迁移函数绑定好，交给平台注册表。
from lspkit.platform.registry import ToolManifest

from .actions import calculate_action, decode_action, forecast_action
from .legacy import convert
from .schema import SCHEMA

# ------ 清单与处理器注册 ------ #
MANIFEST = ToolManifest(
    id="border",
    name_key="border.name",
    description_key="border.description",
    icon="border",
    # 侧边栏排序值，比珍珠炮（10）靠后。
    order=20,
    version="1.1.5",
    schema=SCHEMA,
    # 界面上只显示 calculate / decode；forecast 只能通过 api.tool_call 直接指定 action。
    actions=[
        {"id": "calculate", "labelKey": "border.action.calculate"},
        {"id": "decode", "labelKey": "border.action.decode"},
    ],
    # 结果表格列：三个 TNT 当量（个）与方向名（中文方位）。
    columns=[
        {"key": "t1", "nameKey": "border.col.tnt1", "type": "int"},
        {"key": "t2", "nameKey": "border.col.tnt2", "type": "int"},
        {"key": "t3", "nameKey": "border.col.tnt3", "type": "int"},
        {"key": "dirText", "nameKey": "border.col.direction", "type": "string"},
    ],
)

# 动作名 → 处理函数：平台按此分发 api.tool_call 的 action 参数。
HANDLERS = {
    "calculate": calculate_action,
    "decode": decode_action,
    "forecast": forecast_action,
}

# 导入旧配置时调用的迁移函数。
LEGACY = convert
