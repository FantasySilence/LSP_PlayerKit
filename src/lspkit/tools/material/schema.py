# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 材料换算设置 schema      #
# =================================== #

# schema 描述「用户可以调哪些设置」：分组 → 字段。平台据此生成设置面板，
# Context.settings("material") 按同样的字段列表读出并强制类型，缺项用默认值补齐。

from lspkit.platform.schema import Field, Group, SettingsSchema

from .defaults import DEFAULT_SETTINGS as D

# ------ 设置定义 ------ #
# version 是设置格式版本，改动字段结构时递增（目前 schema 与 defaults 都是 3）。
# Field 参数顺序：key、label(i18n key)、type、default、min、max、step、unit……

SCHEMA = SettingsSchema(
    version=3,
    groups=[
        Group(
            "basic",
            "material.settings.basic",
            [
                # 全局最大堆叠数（个/组），枚举值以字符串保存，避免前端数字比较踩坑；
                # 单种材料还可以在请求的 stacks 字段里单独覆盖（64 / 16 / 1）
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
                # 每盒格数（格/盒）：1–27，步长 1，默认为原版潜影盒的 27 格
                Field("shulkerSlots", "material.field.shulkerSlots", "int", D["shulkerSlots"], 1, 27, 1, unit="unit.slotsPerBox"),
            ],
        ),
        Group(
            "output",
            "material.settings.output",
            [
                # 导出目录（绝对路径），空串表示未选择；unit 为界面上的单位/提示文案
                Field(
                    "exportDir",
                    "material.field.exportDir",
                    "path",
                    D["exportDir"],
                    unit="unit.exportHint",
                ),
            ],
        ),
    ],
)
