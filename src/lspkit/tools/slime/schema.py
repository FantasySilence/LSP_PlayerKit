# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-07                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 史莱姆区块查找器 schema   #
# =================================== #
"""
史莱姆区块查找器的设置 schema：声明设置面板有哪些字段、取值范围与单位。

Field 的位置参数依次是：key、i18n label、类型、默认值、最小值、最大值、步长；
unit 只用于界面标注，hint 是字段下方的提示文案，两者都不参与计算。
校验规则由 platform.schema 统一执行：缺项补默认值，越界或类型不对直接报错。

本工具只有一个分组 query（查询参数），与 defaults.py 的 DEFAULT_SETTINGS
一一对应——这里的默认值全部取自 D，改默认值只需改 constants/defaults。
"""

from lspkit.platform.schema import Field, Group, SettingsSchema

from .constants import MAX_EXACT_CHUNKS
from .defaults import DEFAULT_SETTINGS as D

SCHEMA = SettingsSchema(
    # schema 结构版本号：字段增删或语义变化时递增
    version=2,
    groups=[
        Group(
            "query",
            "slime.settings.query",
            [
                # 种子：字符串保存，避免 JS Number 超过 2^53 丢精度；
                # 支持十进制 long，其余输入按 Java String.hashCode 解析
                Field("seed", "slime.field.seed", "string", D["seed"]),
                # 挂机点中心 X（格），步长 16 格 = 1 区块
                Field(
                    "centerX", "slime.field.centerX", "int",
                    D["centerX"], -30_000_000, 30_000_000, 16,
                    unit="slime.unit.block",
                ),
                # 挂机点中心 Z（格），步长 16 格 = 1 区块
                Field(
                    "centerZ", "slime.field.centerZ", "int",
                    D["centerZ"], -30_000_000, 30_000_000, 16,
                    unit="slime.unit.block",
                ),
                # 圆环内半径（格）：内圈不刷怪，上限 127 保证外半径还能更大
                Field(
                    "ringInner", "slime.field.ringInner", "int",
                    D["ringInner"], 0, 127, 1, unit="slime.unit.block",
                ),
                # 圆环外半径（格）：上限 128 = 8 区块，正好对应 halo 的 17×17 区块
                Field(
                    "ringOuter", "slime.field.ringOuter", "int",
                    D["ringOuter"], 1, 128, 1, unit="slime.unit.block",
                ),
                # 服务器模拟距离（区块）：外半径会被夹到 simDistance × 16 格
                Field(
                    "simDistance", "slime.field.simDistance", "int",
                    D["simDistance"], 1, 32, 1, unit="slime.unit.chunk",
                ),
                # 返回结果条数；上限与 MAX_TOP_N 保持一致
                Field(
                    "topN", "slime.field.topN", "int",
                    D["topN"], 1, 500, 1,
                ),
                # 结果之间的最小间距（区块），0 = 不做非极大值抑制
                Field(
                    "nmsChunks", "slime.field.nms", "int",
                    D["nmsChunks"], 0, 32, 1, unit="slime.unit.chunk",
                ),
                # 扫描模式：auto 超限自动转采样；exact 超限报错；sample 强制采样
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
                # 精确扫描的区块数上限；0 = 不限制（见 actions._exact_limit）。
                # 用户可在这里把上限调大，避免大范围时只能走采样。
                Field(
                    "exactLimit", "slime.field.exactLimit", "int",
                    D["exactLimit"], 0, MAX_EXACT_CHUNKS,
                    1, unit="slime.unit.chunk",
                    hint="slime.hint.exactLimitSetting",
                ),
                # 空置域推荐边长（区块）：前端按它框出能覆盖圆环的空置域，
                # 默认 21×21 区块；太小时前端会提示盖不住圆环
                Field(
                    "perimeterChunks", "slime.field.perimeter", "int",
                    D["perimeterChunks"], 3, 65, 2,
                    unit="slime.unit.chunk", hint="slime.hint.perimeter",
                ),
                # 采样次数：越大越可能找到好点，耗时线性增长
                Field(
                    "samples", "slime.field.samples", "int",
                    D["samples"], 1000, 500_000, 1000,
                ),
            ],
        ),
    ],
)
