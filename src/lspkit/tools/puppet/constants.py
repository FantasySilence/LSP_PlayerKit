# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 假人搬货工具常量         #
# =================================== #

# ------ 维度（写入 /execute in minecraft:<dim>） ------ #
DIMENSIONS = ("overworld", "the_nether", "the_end")

DIMENSION_LABELS = {
    "overworld": "puppet.dim.overworld",
    "the_nether": "puppet.dim.the_nether",
    "the_end": "puppet.dim.the_end",
}

# ------ 运输口径：一个假人最多带 36 盒，一批最多 24 人（= 864 盒） ------ #
DEFAULT_BOXES_PER_BOT = 36
DEFAULT_BOTS_PER_BATCH = 24
DEFAULT_NAME_TEMPLATE = "bot_{origin}_{dest}_{index}"

# ------ 数量上限：防止一次生成过多指令 ------ #
MAX_BOXES = 999_999
MAX_BOTS = 24 * 20
MAX_STATIONS = 200
MAX_ORDERS = 200
MAX_COMMANDS = 2000
MAX_IMPORT_BYTES = 200_000

# ------ 站点与假人名的字符规则（Minecraft 用户名 3–16 位） ------ #
PLAYER_NAME_MIN = 3
PLAYER_NAME_MAX = 16
PREFIX_MAX = 12
GROUP_MAX = 32
NOTE_MAX = 60

# ------ 运输动作 ------ #
OPERATIONS = ("spawn_at_origin", "spawn_at_dest")

# ------ 全部命令执行完后补发的一条聊天消息（英文，游戏内更直观） ------ #
FINAL_MESSAGE = "Operation completed successfully"
