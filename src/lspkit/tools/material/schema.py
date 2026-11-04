# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 材料换算设置 schema      #
# =================================== #

from lspkit.platform.schema import Field, Group, SettingsSchema

from .defaults import DEFAULT_SETTINGS as D

SCHEMA = SettingsSchema(
    version=3,
    groups=[
        Group(
            "basic",
            "material.settings.basic",
            [
                Field(
                    "stackSize",
                    "material.field.maxStack",
                    "enum",
                    D["stackSize"],
                    options=[
                        {"value": "64", "label": "material.stack.64"},
                        {"value": "16", "label": "material.stack.16"},
                        {"value": "1", "label": "material.stack.1"},
                    ],
                ),
                Field("shulkerSlots", "material.field.shulkerSlots", "int", D["shulkerSlots"], 1, 27, 1, unit="格/盒"),
            ],
        ),
        Group(
            "output",
            "material.settings.output",
            [
                Field(
                    "exportDir",
                    "material.field.exportDir",
                    "path",
                    D["exportDir"],
                    unit="留空 = data/output",
                ),
            ],
        ),
    ],
)
