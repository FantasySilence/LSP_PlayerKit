# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 边境炮设置 schema        #
# =================================== #

from lspkit.platform.schema import Field, Group, SettingsSchema

from .defaults import DEFAULT_SETTINGS as D

SCHEMA = SettingsSchema(
    version=2,
    groups=[
        Group(
            "origin",
            "border.settings.origin",
            [
                Field("originX", "border.field.originX", "float", D["originX"], digits=4),
                Field("originY", "border.field.originY", "float", D["originY"], digits=4),
                Field("originZ", "border.field.originZ", "float", D["originZ"], digits=4),
            ],
        ),
        Group(
            "target",
            "border.settings.target",
            [
                Field("targetX", "border.field.targetX", "float", D["targetX"], digits=4),
                Field("targetY", "border.field.targetY", "float", D["targetY"], digits=4),
                Field("targetZ", "border.field.targetZ", "float", D["targetZ"], digits=4),
                Field(
                    "flightTime", "border.field.flightTime", "int",
                    D["flightTime"], 1, 100000, 10, unit="gt",
                ),
            ],
        ),
        Group(
            "behavior",
            "border.settings.behavior",
            [
                Field(
                    "directionMode",
                    "border.field.directionMode",
                    "enum",
                    D["directionMode"],
                    options=[
                        {"value": "origin", "label": "border.option.directionOrigin"},
                        {"value": "fixed", "label": "border.option.directionFixed"},
                    ],
                ),
            ],
        ),
    ],
)
