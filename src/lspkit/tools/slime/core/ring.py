# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-07                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 圆环权重表（纯函数）     #
# =================================== #
"""
权重表 w[i, j, sx, sz]：以挂在区块内的 (sx, sz) 为圆心时，
相对区块 (i-8, j-8) 落在圆环（内径 inner、外径 outer）内的方块数。

17×17 个相对区块、16×16 个块内偏移、每格最多 256 个方块，
用二维前缀和一次性算完，约 7.4 万个整数。

记法的由来：
- 挂机点（玩家脚下的方块）在区块内的偏移是 (sx, sz)，各取 0..15；
- 相对区块 (i, j) 从 -8 到 +8：外半径 128 格正好 8 个区块，
  再远的区块不可能落进环内，所以 17×17 就是全部需要的邻域；
- w 的第 0、1 维是区块偏移，第 2、3 维是块内偏移；
- 对固定的 (sx, sz) 把所有区块的 w 加起来，就是圆环面积（格²）。
  默认 24..128 时每个 (sx, sz) 都是 49,640 格²（见 ring_area）。

为什么要按块内偏移分开存：扫描阶段先用区块中心 (8, 8) 估分，精修阶段
（score.refine）再把 256 个块内偏移逐个代进去，选出真正的最优挂机点。
"""

from __future__ import annotations

import numpy as np

from ..constants import DEFAULT_RING_INNER, DEFAULT_RING_OUTER

HALF = 8  # 外径 128 格 = 8 区块
OFFSET = HALF * 16 + 15  # 最远的方块偏移（143）
SIZE = OFFSET * 2 + 1  # 287


# ------ 权重表构造 ------ #
def build_weights(
    inner: float = DEFAULT_RING_INNER,
    outer: float = DEFAULT_RING_OUTER,
) -> np.ndarray:
    """
    返回 (17, 17, 16, 16) 的 int32 权重表.

    方块坐标取整数格：inner² <= dx² + dz² < outer² 视为在环内。

    实现分三步：
    1. 在 287×287 的方块级平面上，用广播算出每个格点到圆心的距离平方 d2，
       inside = (inner² <= d2 < outer²) 就是环带掩码：内圆整体排除，
       外圆只到边界为止（边界本身不含）；
    2. 对 inside 做二维前缀和，之后任意 16×16 方块矩形内的环内格数都能
       用 4 次查表相减得到；
    3. 对 17×17 区块 × 16×16 块内偏移枚举矩形，一次填满整张表。

    参数单位：inner / outer 是格（方块）。两者都允许浮点：判定用的是整数
    格点的距离平方与 inner²/outer² 比较，所以非整数半径也能一致处理；
    inner 为负按 0 处理；outer <= 0 或 outer <= inner 时返回全零表，
    由调用方（actions._ring）判定为非法圆环。
    """

    weights = np.zeros((HALF * 2 + 1, HALF * 2 + 1, 16, 16), dtype=np.int32)
    inner = max(0.0, float(inner))
    outer = float(outer)
    if outer <= 0 or outer <= inner:
        return weights

    # 第 1 步：方块级环带掩码。坐标是「相对挂机点」的 dx / dz，范围 ±143 格，
    # 正好覆盖外半径 128 格可能触及的所有方块。
    coords = np.arange(-OFFSET, OFFSET + 1, dtype=np.float64)
    d2 = coords[:, None] ** 2 + coords[None, :] ** 2
    inside = (d2 >= inner * inner) & (d2 < outer * outer)

    # 第 2 步：二维前缀和。prefix[i+1, j+1] 表示 inside[0..i, 0..j] 的和，
    # 于是任意矩形 [r0, r1) × [c0, c1) 的环内格数为
    # P[r1][c1] - P[r0][c1] - P[r1][c0] + P[r0][c0]。
    prefix = np.zeros((SIZE + 1, SIZE + 1), dtype=np.int64)
    prefix[1:, 1:] = np.cumsum(np.cumsum(inside.astype(np.int64), axis=0), axis=1)

    # 第 3 步：枚举 (区块偏移 i, j) 与 (块内偏移 sx, sz)，共 17×17×16×16 项。
    # 这里用 4 个广播轴一次算出所有组合，避免 Python 四重循环。
    chunk = np.arange(-HALF, HALF + 1)
    sub = np.arange(16)
    i = chunk[:, None, None, None]
    j = chunk[None, :, None, None]
    sx = sub[None, None, :, None]
    sz = sub[None, None, None, :]

    # 矩形左上角在 prefix 索引里的位置：
    # 该区块覆盖的方块相对挂机点的 dx 从 16*i - sx 到 16*i - sx + 15，
    # 加上 OFFSET 即换算成 inside 的下标（inside 下标 0 对应 -OFFSET）。
    x0 = (16 * i - sx + OFFSET).astype(np.int64)
    z0 = (16 * j - sz + OFFSET).astype(np.int64)

    # 单格最多 256 个方块，权重最大 256，用 int32 足够
    weights[...] = (
        prefix[x0 + 16, z0 + 16]
        - prefix[x0, z0 + 16]
        - prefix[x0 + 16, z0]
        + prefix[x0, z0]
    ).astype(np.int32)
    return weights


# ------ 环面积 ------ #
def ring_area(weights: np.ndarray, sx: int = 8, sz: int = 8) -> int:
    """某个块内偏移对应的圆环面积（格²）.

    把该偏移下 17×17 个区块的权重全部相加即可。数值上等于满足
    inner² <= dx² + dz² < outer² 的整数格点数；默认 24..128 时是 49,640 格²，
    且对 256 个 (sx, sz) 都相同（外半径 128 格恰好被 ±8 区块完全覆盖，
    块内偏移只会平移取景窗口，不会切掉环带）。

    默认参数 (8, 8) 对应区块中心，也是扫描阶段估分用的偏移。
    """

    return int(weights[:, :, sx, sz].sum())
