# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 边境炮 manifest          #
# =================================== #

from lspkit.platform.registry import ToolManifest

from .actions import calculate_action, decode_action
from .legacy import convert
from .schema import SCHEMA

MANIFEST = ToolManifest(
    id="border",
    name_key="border.name",
    description_key="border.description",
    icon="border",
    order=20,
    version="1.1.1",
    schema=SCHEMA,
    actions=[
        {"id": "calculate", "labelKey": "border.action.calculate"},
        {"id": "decode", "labelKey": "border.action.decode"},
    ],
    columns=[
        {"key": "t1", "nameKey": "border.col.tnt1", "type": "int"},
        {"key": "t2", "nameKey": "border.col.tnt2", "type": "int"},
        {"key": "t3", "nameKey": "border.col.tnt3", "type": "int"},
        {"key": "dirText", "nameKey": "border.col.direction", "type": "string"},
    ],
)

HANDLERS = {"calculate": calculate_action, "decode": decode_action}

LEGACY = convert
