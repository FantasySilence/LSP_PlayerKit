# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 假人搬货设置 schema      #
# =================================== #

from lspkit.platform.schema import Field, Group, SettingsSchema

from .defaults import DEFAULT_SETTINGS as D

SCHEMA = SettingsSchema(
    version=1,
    groups=[
        Group(
            "transport",
            "puppet.settings.transport",
            [
                Field(
                    "boxesPerBot",
                    "puppet.field.boxesPerBot",
                    "int",
                    D["boxesPerBot"],
                    1,
                    36,
                    1,
                    unit="puppet.unit.boxesPerBot",
                ),
                Field(
                    "botsPerBatch",
                    "puppet.field.botsPerBatch",
                    "int",
                    D["botsPerBatch"],
                    1,
                    64,
                    1,
                    unit="puppet.unit.botsPerBatch",
                ),
                Field(
                    "nameTemplate",
                    "puppet.field.nameTemplate",
                    "string",
                    D["nameTemplate"],
                    hint="puppet.hint.nameTemplate",
                ),
            ],
        ),
        Group(
            "execute",
            "puppet.settings.execute",
            [
                Field(
                    "allowExecute",
                    "puppet.field.allowExecute",
                    "bool",
                    D["allowExecute"],
                    hint="puppet.hint.allowExecute",
                ),
                Field(
                    "commandInterval",
                    "puppet.field.commandInterval",
                    "float",
                    D["commandInterval"],
                    0.2,
                    5,
                    0.1,
                    2,
                    unit="s",
                ),
                Field(
                    "startDelay",
                    "puppet.field.startDelay",
                    "int",
                    D["startDelay"],
                    0,
                    15,
                    1,
                    unit="s",
                ),
                Field(
                    "inputMode",
                    "puppet.field.inputMode",
                    "enum",
                    D["inputMode"],
                    options=[
                        {"value": "paste", "label": "puppet.inputMode.paste"},
                        {"value": "type", "label": "puppet.inputMode.type"},
                    ],
                ),
                Field(
                    "requireFocus",
                    "puppet.field.requireFocus",
                    "bool",
                    D["requireFocus"],
                ),
                Field(
                    "maxAttempts",
                    "puppet.field.maxAttempts",
                    "int",
                    D["maxAttempts"],
                    1,
                    5,
                    1,
                    unit="puppet.unit.times",
                ),
                Field(
                    "restoreClipboard",
                    "puppet.field.restoreClipboard",
                    "bool",
                    D["restoreClipboard"],
                ),
            ],
        ),
    ],
)
