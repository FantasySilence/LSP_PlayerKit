# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-07                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 史莱姆区块查找器常量     #
# =================================== #

# ------ 刷怪圆环（格）：24 格内不刷怪，128 格外消失 ------ #
DEFAULT_RING_INNER = 24
DEFAULT_RING_OUTER = 128

# ------ 服务器模拟距离（区块）；不足 8 时外圈不 tick ------ #
DEFAULT_SIM_DISTANCE = 8

# ------ 结果与展示 ------ #
DEFAULT_TOP_N = 100
DEFAULT_NMS_CHUNKS = 8
DEFAULT_SAMPLES = 50_000
DEFAULT_PERIMETER_CHUNKS = 21

# ------ 计算规模上限 ------ #
DEFAULT_EXACT_CHUNKS = 4096 * 4096
MIN_EXACT_CHUNKS = 256 * 256
MAX_EXACT_CHUNKS = 8192 * 8192
MAX_MAP_CELLS = 1024 * 1024
MAX_TOP_N = 500
MAX_SAMPLES = 500_000
TILE_CHUNKS = 1024
FFT_MIN_CELLS = 200_000

# ------ 世界边界（Java 版可用范围） ------ #
WORLD_MIN = -29_999_984
WORLD_MAX = 29_999_984

# ------ 史莱姆区块种子公式常量（Java long 溢出，按 64 位回绕） ------ #
MASK64 = (1 << 64) - 1
MASK48 = (1 << 48) - 1
TERM_X2 = 0x4C1906
TERM_X1 = 0x5AC0DB
TERM_Z2 = 0x4307A7
TERM_Z1 = 0x5F24F
SEED_XOR = 0x3AD8025F
RANDOM_MULT = 0x5DEECE66D
RANDOM_ADD = 0xB
# nextInt(10) 的拒绝阈值（bits >= 2^31 - 2^31 % 10）
REJECT_FROM = 2_147_483_640
