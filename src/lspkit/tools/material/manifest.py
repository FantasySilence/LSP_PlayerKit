# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 材料换算 manifest        #
# =================================== #

from lspkit.platform.registry import ToolManifest

from .actions import convert_action, pack_action
from .legacy import convert
from .schema import SCHEMA

MANIFEST = ToolManifest(
    id="material",
    name_key="material.name",
    description_key="material.description",
    icon="box",
    order=30,
    version="1.1.4",
    schema=SCHEMA,
    actions=[
        {"id": "convert", "labelKey": "material.action.convert"},
        {"id": "pack", "labelKey": "material.action.pack"},
    ],
    columns=[
        {"key": "name", "nameKey": "material.col.name", "type": "string"},
        {"key": "stack", "nameKey": "material.col.stack", "type": "int"},
        {"key": "count", "nameKey": "material.col.count", "type": "int"},
        {"key": "shulkers", "nameKey": "material.col.shulkers", "type": "int"},
        {"key": "stacks", "nameKey": "material.col.stacks", "type": "int"},
        {"key": "items", "nameKey": "material.col.items", "type": "int"},
    ],
)

HANDLERS = {"convert": convert_action, "pack": pack_action}

LEGACY = convert
