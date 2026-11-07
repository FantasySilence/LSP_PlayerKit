# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-07                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 史莱姆区块查找器常量     #
# =================================== #
"""史莱姆区块查找器的常量表：只提供默认值与边界，不参与任何运算.

单位约定：
- 区块（chunk）：16×16 格；方块坐标与区块坐标换算为 chunk = floor(block / 16)；
- 格：一个方块占据的面积单位，圆环面积以「格²」计；
- 半径、距离默认以格为单位；以区块为单位的常量都在名字或注释里标明。
"""

# ------ 刷怪圆环（格）：24 格内不刷怪，128 格外消失 ------ #
# 内、外半径是「挂机点周围有效刷怪环带」的两端，单位是格（方块）。
# 默认 24..128 的环带面积是 49,640 格²，由 core/ring.py 的权重表求和得到。
DEFAULT_RING_INNER = 24
DEFAULT_RING_OUTER = 128

# ------ 服务器模拟距离（区块）；不足 8 时外圈不 tick ------ #
# 模拟距离以区块计（8 → 半径 8×16 = 128 格）。超出模拟范围的外圈区块
# 不参与 tick，所以 actions._ring() 会把外半径夹到 simDistance × 16 格。
DEFAULT_SIM_DISTANCE = 8

# ------ 结果与展示 ------ #
# topN：返回的结果条数；nmsChunks：结果之间的最小间距（区块，切比雪夫距离）。
# samples：采样模式的随机取点次数。
# perimeterChunks：空置域推荐边长（区块，21 → 21×21 区块），只供前端框选展示。
DEFAULT_TOP_N = 100
DEFAULT_NMS_CHUNKS = 8
DEFAULT_SAMPLES = 50_000
DEFAULT_PERIMETER_CHUNKS = 21

# ------ 计算规模上限 ------ #
# 0 表示不限制精确扫描范围；用户可在设置里填上限控制耗时
DEFAULT_EXACT_CHUNKS = 0
# 用户可填的精确扫描上限被夹取到 [256×256, 8192×8192] 个区块
MIN_EXACT_CHUNKS = 256 * 256
MAX_EXACT_CHUNKS = 8192 * 8192
# 地图接口一次最多请求的区块格数（1,048,576 = 1024×1024）
MAX_MAP_CELLS = 1024 * 1024
# 同步 find 的保护上限（后台 scan 不受此限）
MAX_SYNC_CHUNKS = 4 * 1024 * 1024
MAX_TOP_N = 500
MAX_SAMPLES = 500_000
# 精确扫描的分块边长（区块）：每块按 1024+8+8 的行列宽度做卷积
TILE_CHUNKS = 1024
# 卷积输出格数达到该值时改用 FFT，否则逐点累加（见 core/score.py）
FFT_MIN_CELLS = 200_000

# ------ 世界边界（Java 版可用范围） ------ #
# Java 版世界边界为 ±29,999,984 格，对应区块坐标约 ±1,874,999
WORLD_MIN = -29_999_984
WORLD_MAX = 29_999_984

# ------ 史莱姆区块种子公式常量（Java long 溢出，按 64 位回绕） ------ #
# 公式（chunkX / chunkZ 为区块坐标，Java 的 int 与 long 各有自己的溢出）：
#   seed + x*x*0x4c1906 + x*0x5ac0db + (int)(z*z)*0x4307a7L + z*0x5f24f
#   ^ 0x3ad8025f  ->  new Random(...).nextInt(10) == 0
# 下面的 0x4C1906/0x5AC0DB/0x4307A7/0x5F24F 就是公式里的四个系数，
# 0x3AD8025F 是参与异或的常量。
MASK64 = (1 << 64) - 1
MASK48 = (1 << 48) - 1
TERM_X2 = 0x4C1906
TERM_X1 = 0x5AC0DB
TERM_Z2 = 0x4307A7
TERM_Z1 = 0x5F24F
SEED_XOR = 0x3AD8025F
# java.util.Random 的 LCG 参数：state = (state * 0x5DEECE66D + 0xB) mod 2^48
RANDOM_MULT = 0x5DEECE66D
RANDOM_ADD = 0xB
# nextInt(10) 的拒绝阈值（bits >= 2^31 - 2^31 % 10）
# 2^31 = 2,147,483,648，模 10 余 8，故阈值是 2,147,483,640。
# bits 落在 [0, 2147483639] 时 bits % 10 均匀；再大就要重新抽一次。
REJECT_FROM = 2_147_483_640
