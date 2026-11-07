# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 边境炮设置 schema        #
# =================================== #

# 边境炮设置面板的字段描述：分组、类型、默认值、上下限、步进、小数位与单位；
# 平台按这份 schema 渲染表单、校验取值并生成默认设置，version 供旧配置迁移判断。
from lspkit.platform.schema import Field, Group, SettingsSchema

from .defaults import DEFAULT_SETTINGS as D

# ------ 分组：炮口 / 目标 / 行为 ------ #
# Field 的定位参数顺序固定为 (key, label, type, default, min, max, step, digits, unit)：
# min / max / step 用于输入防呆，digits 只影响界面显示的小数位，不改存储精度。
SCHEMA = SettingsSchema(
    version=2,
    groups=[
        # 炮口组：方向判定与落点计算都以它为原点（directionMode=fixed 时除外）。
        Group(
            "origin",
            "border.settings.origin",
            [
                Field("originX", "border.field.originX", "float", D["originX"], digits=4),
                Field("originY", "border.field.originY", "float", D["originY"], digits=4),
                Field("originZ", "border.field.originZ", "float", D["originZ"], digits=4),
            ],
        ),
        # 目标组：目标坐标与预计飞行时间；flightTime 是候选行的起点（单位 gt）。
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
        # 行为组：方向参考点选择（origin 用炮口，fixed 用旧版写死的 (10000, 10000)）。
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
