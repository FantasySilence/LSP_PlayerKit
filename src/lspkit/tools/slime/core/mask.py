# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-07                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 史莱姆区块位图（纯函数） #
# =================================== #
"""
逐位复刻 Java Edition 的史莱姆区块判定：

    int a = chunkX * chunkX * 0x4c1906;        // 32 位 int 溢出
    int b = chunkX * 0x5ac0db;                 // 32 位 int
    long d = (int) (chunkZ * chunkZ) * 0x4307a7L;  // z² 先按 int 溢出，再乘 long
    int e = chunkZ * 0x5f24f;                  // 32 位 int
    long s = seed + a + b + d + e;
    new Random(s ^ 0x3ad8025fL).nextInt(10) == 0

关键点：三个乘法是 32 位 int 溢出后再转 long，不是直接用 64 位相乘。
这一点用 Amidst 的 64×64 区块快照（seed 1）逐位核对过：
int32 语义 0 处不一致，64 位语义有 291 处不一致。
"""

from __future__ import annotations

import numpy as np

from ..constants import (
    MASK48,
    MASK64,
    RANDOM_ADD,
    RANDOM_MULT,
    REJECT_FROM,
    SEED_XOR,
    TERM_X1,
    TERM_X2,
    TERM_Z1,
    TERM_Z2,
)
from .seed import seed_bits

_MULT = np.uint64(RANDOM_MULT)
_ADD = np.uint64(RANDOM_ADD)
_MASK48 = np.uint64(MASK48)
_U17 = np.uint64(17)
_U10 = np.uint64(10)
_REJECT = np.uint64(REJECT_FROM)
_XOR = np.uint64(SEED_XOR)

_I_X2 = np.int32(TERM_X2)
_I_X1 = np.int32(TERM_X1)
_I_Z1 = np.int32(TERM_Z1)
_L_Z2 = np.int64(TERM_Z2)


def _int32_wrap(value: np.ndarray) -> np.ndarray:
    """Java int 乘法溢出：numpy int32 本身按 2^32 回绕，这里只做类型确认."""

    return np.asarray(value, dtype=np.int32)


def slime_flags(seed: int, xs, zs) -> np.ndarray:
    """
    判断任意区块坐标是否为史莱姆区块.

    xs / zs 可以是标量、1D 或可广播的 2D 数组；返回同形状的 bool 数组。
    """

    xi = np.asarray(xs, dtype=np.int64).astype(np.int32)
    zi = np.asarray(zs, dtype=np.int64).astype(np.int32)

    # 前三项按 Java int 计算（32 位溢出），d 先取 z² 的 int 值再乘 long
    part_x2 = _int32_wrap(_int32_wrap(xi * xi) * _I_X2)
    part_x1 = _int32_wrap(xi * _I_X1)
    part_z1 = _int32_wrap(zi * _I_Z1)
    part_z2 = _int32_wrap(zi * zi).astype(np.int64) * _L_Z2

    total = (
        np.uint64(seed_bits(seed))
        + part_x2.astype(np.uint64)
        + part_x1.astype(np.uint64)
        + part_z1.astype(np.uint64)
        + part_z2.astype(np.uint64)
    )
    value = total ^ _XOR

    state = (value ^ _MULT) & _MASK48
    state = (state * _MULT + _ADD) & _MASK48
    bits = state >> _U17

    rejected = bits >= _REJECT
    if rejected.any():
        state_flat = state.reshape(-1).copy()
        bits_flat = bits.reshape(-1).copy()
        index = np.flatnonzero(rejected.reshape(-1))
        while index.size:
            state_flat[index] = (state_flat[index] * _MULT + _ADD) & _MASK48
            bits_flat[index] = state_flat[index] >> _U17
            bad = bits_flat[index] >= _REJECT
            index = index[bad]
        bits = bits_flat.reshape(bits.shape)

    return (bits % _U10) == np.uint64(0)


def slime_mask(seed: int, cx: int, cz: int, width: int, height: int) -> np.ndarray:
    """
    生成矩形区块区域的位图，行是 Z、列是 X，形状 (height, width)。

    cx / cz 为左上角区块坐标（可为负）。
    """

    width = int(width)
    height = int(height)
    if width <= 0 or height <= 0:
        return np.zeros((max(height, 0), max(width, 0)), dtype=bool)

    xs = np.arange(int(cx), int(cx) + width, dtype=np.int64)
    zs = np.arange(int(cz), int(cz) + height, dtype=np.int64)
    return slime_flags(seed, xs[None, :], zs[:, None])
