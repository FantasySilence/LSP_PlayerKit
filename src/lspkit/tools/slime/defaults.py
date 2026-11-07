# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-07                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 史莱姆区块查找器默认设置 #
# =================================== #
"""史莱姆区块查找器的默认设置（前端未提供时由后端兜底）.

这里只是「出厂值」：schema.py 用它生成设置面板的初值，actions.py 用它
填充请求里缺失的字段。运行期以 ctx.settings("slime") 读到的用户设置为准。
"""

from .constants import DEFAULT_EXACT_CHUNKS, DEFAULT_PERIMETER_CHUNKS

DEFAULT_SETTINGS = {
    # 世界种子：一律用字符串保存，避免 JS Number 超过 2^53 丢精度
    "seed": "0",
    # 挂机点默认落在 (-32, -8) 格，对应区块 (-2, -1)
    "centerX": -32,
    "centerZ": -8,
    # 精确扫描的区块数上限；0 表示不限制（见 actions._exact_limit）
    "exactLimit": DEFAULT_EXACT_CHUNKS,
    # 空置域推荐边长，单位区块（默认 21×21，需覆盖刷怪圆环）
    "perimeterChunks": DEFAULT_PERIMETER_CHUNKS,
    # 刷怪环带的内、外半径，单位格
    "ringInner": 24,
    "ringOuter": 128,
    # 服务器模拟距离，单位区块（8 → 128 格）
    "simDistance": 8,
    # 返回结果条数
    "topN": 100,
    # 结果之间的最小间距，单位区块（0 表示不做非极大值抑制）
    "nmsChunks": 8,
    # 扫描模式：auto（超限自动转采样）/ exact（强制精确）/ sample（强制采样）
    "mode": "auto",
    # 采样模式的随机取点次数
    "samples": 50_000,
}
