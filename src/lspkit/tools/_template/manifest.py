# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 工具 manifest            #
# =================================== #

from lspkit.platform.registry import ToolManifest

from .actions import my_action
from .legacy import convert
from .schema import SCHEMA

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

HANDLERS = {"my_action": my_action}

LEGACY = convert
