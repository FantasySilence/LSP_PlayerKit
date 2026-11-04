# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 珍珠炮 manifest          #
# =================================== #

from lspkit.platform.registry import ToolManifest

from .actions import calculate_action, decode_action, trace_action
from .legacy import convert
from .schema import SCHEMA

MANIFEST = ToolManifest(
    id="pearl",
    name_key="pearl.name",
    description_key="pearl.description",
    icon="pearl",
    order=10,
    version="1.1.1",
    schema=SCHEMA,
    actions=[
        {"id": "calculate", "labelKey": "pearl.action.calculate"},
        {"id": "decode", "labelKey": "pearl.action.decode"},
        {"id": "trace", "labelKey": "pearl.action.trace"},
    ],
    columns=[
        {"key": "error", "nameKey": "pearl.col.error", "type": "float", "digits": 6},
        {"key": "ticks", "nameKey": "pearl.col.ticks", "type": "int"},
        {"key": "blue", "nameKey": "pearl.col.blue", "type": "int"},
        {"key": "red", "nameKey": "pearl.col.red", "type": "int"},
        {"key": "total", "nameKey": "pearl.col.total", "type": "int"},
    ],
)

HANDLERS = {
    "calculate": calculate_action,
    "decode": decode_action,
    "trace": trace_action,
}

LEGACY = convert
