# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 珍珠炮设置 schema        #
# =================================== #

# 珍珠炮设置面板的字段描述：分组、类型、默认值、上下限、步进、小数位与单位；
# 平台按这份 schema 渲染表单、校验取值并生成默认设置，version 供旧配置迁移判断。
from lspkit.platform.schema import Field, Group, SettingsSchema

from .defaults import DEFAULT_SETTINGS as D

# ------ 分组：基础 / 平射 / 抛射 ------ #
# Field 的定位参数顺序固定为 (key, label, type, default, min, max, step, digits, unit)：
# min / max / step 用于输入防呆，digits 只影响界面显示的小数位，不改存储精度。
SCHEMA = SettingsSchema(
    version=3,
    groups=[
        # 基础组：搜索上限、每组当量、炮口/目标坐标、发射模式与抛射开关。
        Group(
            "basic",
            "pearl.settings.basic",
            [
                Field("maxTnt", "pearl.field.maxTnt", "int", D["maxTnt"], 1, 100000, 10, unit="unit.pcs"),
                Field("tntPerUnit", "pearl.field.tntPerUnit", "int", D["tntPerUnit"], 1, 4096, 10, unit="unit.perArray"),
                Field("originX", "pearl.field.originX", "float", D["originX"], digits=4),
                Field("originZ", "pearl.field.originZ", "float", D["originZ"], digits=4),
                Field("targetX", "pearl.field.targetX", "float", D["targetX"], digits=4),
                Field("targetZ", "pearl.field.targetZ", "float", D["targetZ"], digits=4),
                Field(
                    "fireMode",
                    "pearl.field.mode",
                    "enum",
                    D["fireMode"],
                    options=[
                        {"value": "flat", "label": "pearl.mode.flat"},
                        {"value": "eject", "label": "pearl.mode.eject"},
                    ],
                ),
                Field("ejectionAvailable", "pearl.field.ejectionAvailable", "bool", D["ejectionAvailable"]),
            ],
        ),
        # 平射组：四项弹道参数；动量给到 10 位小数，避免显示取整后复算漂移。
        Group(
            "flat",
            "pearl.settings.flat",
            [
                Field("flat.xzMotion", "pearl.field.flat.xzMotion", "float", D["flat"]["xzMotion"], digits=10),
                Field("flat.yMotion", "pearl.field.flat.yMotion", "float", D["flat"]["yMotion"], digits=10),
                Field("flat.yInitMotion", "pearl.field.flat.yInitMotion", "float", D["flat"]["yInitMotion"], digits=10),
                Field("flat.yInitPosition", "pearl.field.flat.yInitPosition", "float", D["flat"]["yInitPosition"], digits=4),
            ],
        ),
        # 抛射组：字段含义同平射，数值对应抛射弹道（Y 动量为正、向上抛）。
        Group(
            "eject",
            "pearl.settings.eject",
            [
                Field("eject.xzMotion", "pearl.field.eject.xzMotion", "float", D["eject"]["xzMotion"], digits=10),
                Field("eject.yMotion", "pearl.field.eject.yMotion", "float", D["eject"]["yMotion"], digits=10),
                Field("eject.yInitMotion", "pearl.field.eject.yInitMotion", "float", D["eject"]["yInitMotion"], digits=10),
                Field("eject.yInitPosition", "pearl.field.eject.yInitPosition", "float", D["eject"]["yInitPosition"], digits=4),
            ],
        ),
    ],
)
