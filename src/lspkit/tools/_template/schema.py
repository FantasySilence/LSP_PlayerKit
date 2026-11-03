# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 设置 schema              #
# =================================== #

from lspkit.platform.schema import Field, Group, SettingsSchema

from .defaults import DEFAULT_SETTINGS as D

SCHEMA = SettingsSchema(
    version=1,
    groups=[
        Group(
            "basic",
            "my-tool.settings.basic",
            [
                Field("someNumber", "my-tool.field.someNumber", "float", D["someNumber"], digits=4),
            ],
        ),
    ],
)
