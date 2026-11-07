# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 假人搬货设置 schema      #
# =================================== #

"""
假人搬货的设置项声明（给设置界面渲染 + 给后端校验用）.

Field 的位置参数依次是：键名、i18n 标签键、类型、默认值、最小值、最大值、
步进；个别类型再跟小数位数或 options。这里只声明，不做业务校验；
真正影响生成的边界（如每假人盒数参与 ceil 计算）在 core/plan.py。

两组：
- transport：运输口径，改它会直接改变假人数与批次；
- execute：真实输入的执行参数，真实发送在 platform/autoinput.py。
"""

from lspkit.platform.schema import Field, Group, SettingsSchema

# 默认值统一取自 defaults，避免两处写死不一致.
from .defaults import DEFAULT_SETTINGS as D

SCHEMA = SettingsSchema(
    version=1,
    groups=[
        Group(
            "transport",
            "puppet.settings.transport",
            [
                # 每假人盒数：默认 36（背包容量），范围 1–36；越小假人越多.
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
                # 每批人数：默认 24，范围 1–64；超过这个数就分批，批间等确认.
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
                # 名字模板：必须含 {index}，渲染结果需满足 3–16 位用户名限制.
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
                # 安全开关：关闭时 run_start 直接拒绝，前端也应隐藏执行按钮.
                Field(
                    "allowExecute",
                    "puppet.field.allowExecute",
                    "bool",
                    D["allowExecute"],
                    hint="puppet.hint.allowExecute",
                ),
                # 命令间隔（秒）：0.2–5，步进 0.1，保留 2 位小数；太小易被服务器拦.
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
                # 起始延迟（秒）：0–15，留给用户切窗口与松手.
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
                # 输入方式：paste 走剪贴板整条粘贴（快），type 逐字敲（稳）.
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
                # 要求游戏窗口在前台，避免命令被打到聊天框以外的地方.
                Field(
                    "requireFocus",
                    "puppet.field.requireFocus",
                    "bool",
                    D["requireFocus"],
                ),
                # 单条命令失败重试次数：1–5.
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
                # 用完剪贴板后还原原内容.
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
