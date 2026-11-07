# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-07                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 史莱姆区块查找器 schema   #
# =================================== #

from lspkit.platform.schema import Field, Group, SettingsSchema

from .constants import MAX_EXACT_CHUNKS, MIN_EXACT_CHUNKS
from .defaults import DEFAULT_SETTINGS as D

SCHEMA = SettingsSchema(
    version=2,
    groups=[
        Group(
            "query",
            "slime.settings.query",
            [
                Field("seed", "slime.field.seed", "string", D["seed"]),
                Field(
                    "centerX", "slime.field.centerX", "int",
                    D["centerX"], -30_000_000, 30_000_000, 16,
                    unit="slime.unit.block",
                ),
                Field(
                    "centerZ", "slime.field.centerZ", "int",
                    D["centerZ"], -30_000_000, 30_000_000, 16,
                    unit="slime.unit.block",
                ),
                Field(
                    "ringInner", "slime.field.ringInner", "int",
                    D["ringInner"], 0, 127, 1, unit="slime.unit.block",
                ),
                Field(
                    "ringOuter", "slime.field.ringOuter", "int",
                    D["ringOuter"], 1, 128, 1, unit="slime.unit.block",
                ),
                Field(
                    "simDistance", "slime.field.simDistance", "int",
                    D["simDistance"], 1, 32, 1, unit="slime.unit.chunk",
                ),
                Field(
                    "topN", "slime.field.topN", "int",
                    D["topN"], 1, 500, 1,
                ),
                Field(
                    "nmsChunks", "slime.field.nms", "int",
                    D["nmsChunks"], 0, 32, 1, unit="slime.unit.chunk",
                ),
                Field(
                    "mode",
                    "slime.field.mode",
                    "enum",
                    D["mode"],
                    options=[
                        {"value": "auto", "label": "slime.mode.auto"},
                        {"value": "exact", "label": "slime.mode.exact"},
                        {"value": "sample", "label": "slime.mode.sample"},
                    ],
                ),
                Field(
                    "exactLimit", "slime.field.exactLimit", "int",
                    D["exactLimit"], MIN_EXACT_CHUNKS, MAX_EXACT_CHUNKS,
                    1_048_576, unit="slime.unit.chunk",
                    hint="slime.hint.exactLimitSetting",
                ),
                Field(
                    "perimeterChunks", "slime.field.perimeter", "int",
                    D["perimeterChunks"], 3, 65, 2,
                    unit="slime.unit.chunk", hint="slime.hint.perimeter",
                ),
                Field(
                    "samples", "slime.field.samples", "int",
                    D["samples"], 1000, 500_000, 1000,
                ),
            ],
        ),
    ],
)
