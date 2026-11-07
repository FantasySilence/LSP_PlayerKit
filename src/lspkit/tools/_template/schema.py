# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 设置 schema              #
# =================================== #
# schema 描述「用户可以调哪些设置」：分组（Group）→ 字段（Field）。
# 平台据此生成设置面板，Context.settings(tool_id) 按同一份字段列表读出并强制类型。
# 字段参数顺序：key、label(i18n key)、type、default、min、max、step、unit，
# 其余（digits / options / hint）用关键字传参。type 取 int / float / bool / enum /
# string / path；改字段结构时把 version 递增，旧配置由 legacy.py 迁移。

from lspkit.platform.schema import Field, Group, SettingsSchema

from .defaults import DEFAULT_SETTINGS as D

# ------ 设置定义 ------ #

SCHEMA = SettingsSchema(
    version=1,
    groups=[
        Group(
            "basic",
            "my-tool.settings.basic",
            [
                # 示例字段：浮点，digits 控制界面显示的小数位；
                # 默认值从 defaults.py 取，不要在这里写死第二份
                Field("someNumber", "my-tool.field.someNumber", "float", D["someNumber"], digits=4),
            ],
        ),
    ],
)
