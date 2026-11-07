# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 假人搬货工具常量         #
# =================================== #

"""
假人搬货工具的只读常量表。

本模块只放口径与上限，不放任何逻辑，改动会同时影响三处：
- 计划生成：core/plan.py 用盒数、批次、名字长度来算命令；
- 默认设置：defaults.py 引用同名常量作为出厂值；
- 设置校验：schema.py 的取值范围与这里保持一致。
改数值前请先确认后端校验与前端提示都已覆盖。
"""

# ------ 维度（写入 /execute in minecraft:<dim>） ------ #
# 命令里写成 /execute in minecraft:overworld 这种形式，此处只存不带命名空间的后半段.
DIMENSIONS = ("overworld", "the_nether", "the_end")

# 维度 → i18n key 的映射；只给前端下拉框取显示名用，值不是给人看的文案.
DIMENSION_LABELS = {
    "overworld": "puppet.dim.overworld",
    "the_nether": "puppet.dim.the_nether",
    "the_end": "puppet.dim.the_end",
}

# ------ 运输口径：一个假人最多带 36 盒，一批最多 24 人（= 864 盒） ------ #
# 盒数 → 人数：bots = ceil(盒数 / boxesPerBot)。36 是单次搬运背包容量.
DEFAULT_BOXES_PER_BOT = 36
# 人数 → 批次：每批 24 人，超过就分批，批与批之间等用户确认.
DEFAULT_BOTS_PER_BATCH = 24
# 假人名模板：{origin}/{dest} 取站点前缀，{index} 从 1 开始的序号.
# 渲染结果必须是 3–16 位字母 / 数字 / 下划线，见 core/naming.py.
DEFAULT_NAME_TEMPLATE = "bot_{origin}_{dest}_{index}"

# ------ 数量上限：防止一次生成过多指令 ------ #
# 单张运单最多多少盒；再大请拆单，避免一次生成几千条命令把游戏卡住.
MAX_BOXES = 999_999
# 单张运单最多多少假人：24 人/批 × 20 批 = 480 人.
MAX_BOTS = 24 * 20
# 站点表最多多少条，超了 import / upsert 会报错.
MAX_STATIONS = 200
# 台账最多保留多少条运单，最早的会被挤掉.
MAX_ORDERS = 200
# 一次执行最多多少条命令（超过要分批或拆单）.
MAX_COMMANDS = 2000
# 一次导入的文本最多多少字节，防止粘贴超大文件卡死.
MAX_IMPORT_BYTES = 200_000

# ------ 站点与假人名的字符规则（Minecraft 用户名 3–16 位） ------ #
# Minecraft 客户端对用户名的硬限制：少于 3 位或多于 16 位都进不了服务器.
PLAYER_NAME_MIN = 3
PLAYER_NAME_MAX = 16
# 站点前缀会拼进假人名，所以必须短；最多 12 位，给 bot_ / _index 留余量.
PREFIX_MAX = 12
# 分组 tag（如「工业区」）最多 32 字，且不允许空白，见 core/stations.py 的 GROUP_RE.
GROUP_MAX = 32
# 站点备注只做展示，超过 60 字直接截断，不报错.
NOTE_MAX = 60

# ------ 运输动作 ------ #
# spawn_at_origin：假人在始发站生成；spawn_at_dest：在目的站生成（反向搬运）.
OPERATIONS = ("spawn_at_origin", "spawn_at_dest")

# ------ 全部命令执行完后补发的一条聊天消息（英文，游戏内更直观） ------ #
FINAL_MESSAGE = "Operation completed successfully"
