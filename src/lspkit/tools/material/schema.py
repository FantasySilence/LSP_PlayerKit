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
    version=1,
    groups=[
        Group(
            "basic",
            "material.settings.basic",
            [
                Field("stackSize", "material.field.stackSize", "int", D["stackSize"], 1, 64, 1, unit="个/格"),
                Field("shulkerSlots", "material.field.shulkerSlots", "int", D["shulkerSlots"], 1, 27, 1, unit="格/盒"),
            ],
        ),
    ],
)
