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
"""

from __future__ import annotations

import numpy as np

from ..constants import DEFAULT_RING_INNER, DEFAULT_RING_OUTER

HALF = 8  # 外径 128 格 = 8 区块
OFFSET = HALF * 16 + 15  # 最远的方块偏移（143）
SIZE = OFFSET * 2 + 1  # 287


def build_weights(
    inner: float = DEFAULT_RING_INNER,
    outer: float = DEFAULT_RING_OUTER,
) -> np.ndarray:
    """
    返回 (17, 17, 16, 16) 的 int32 权重表.

    方块坐标取整数格：inner² <= dx² + dz² < outer² 视为在环内。
    """

    weights = np.zeros((HALF * 2 + 1, HALF * 2 + 1, 16, 16), dtype=np.int32)
    inner = max(0.0, float(inner))
    outer = float(outer)
    if outer <= 0 or outer <= inner:
        return weights

    coords = np.arange(-OFFSET, OFFSET + 1, dtype=np.float64)
    d2 = coords[:, None] ** 2 + coords[None, :] ** 2
    inside = (d2 >= inner * inner) & (d2 < outer * outer)

    prefix = np.zeros((SIZE + 1, SIZE + 1), dtype=np.int64)
    prefix[1:, 1:] = np.cumsum(np.cumsum(inside.astype(np.int64), axis=0), axis=1)

    chunk = np.arange(-HALF, HALF + 1)
    sub = np.arange(16)
    i = chunk[:, None, None, None]
    j = chunk[None, :, None, None]
    sx = sub[None, None, :, None]
    sz = sub[None, None, None, :]

    x0 = (16 * i - sx + OFFSET).astype(np.int64)
    z0 = (16 * j - sz + OFFSET).astype(np.int64)

    weights[...] = (
        prefix[x0 + 16, z0 + 16]
        - prefix[x0, z0 + 16]
        - prefix[x0 + 16, z0]
        + prefix[x0, z0]
    ).astype(np.int32)
    return weights


def ring_area(weights: np.ndarray, sx: int = 8, sz: int = 8) -> int:
    """某个块内偏移对应的圆环面积（格²）."""

    return int(weights[:, :, sx, sz].sum())
