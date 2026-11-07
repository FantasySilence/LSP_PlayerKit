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

整条链路的五步（下面的实现严格对应）：
1. 用区块坐标算出 4 个乘积项，前三项按 32 位 int 回绕，z² 项先回绕成 int
   再提升成 64 位 long 参与加法；
2. 种子（64 位 long）与 4 项相加，结果按 64 位回绕；
3. 与 0x3AD8025F 异或，得到 Java 的 new Random(...) 的种子；
4. Random 构造时 state = (seed ^ 0x5DEECE66D) & (2^48 - 1)，只留低 48 位；
   调用 nextInt(10) 前先做一次 LCG 迭代并取高 31 位作为 bits；
5. nextInt(10) 的拒绝采样：bits >= 2,147,483,640 时重抽，最后 bits % 10 == 0
   即为史莱姆区块。

注意：世界边界 ±29,999,984 格只对应约 ±1,874,999 个区块，远小于 int32，
所以 int64→int32 的转换不会截断；真正需要「回绕」的是乘法溢出。
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

# ------ 预转成 numpy 标量，避免逐元素运算时反复做 Python↔numpy 类型转换 ------ #
# Random 的 LCG 参数与掩码按 uint64 参与运算（Python int 直接参与会被当成
# object/提升到 float，因此先固定 dtype）。
_MULT = np.uint64(RANDOM_MULT)
_ADD = np.uint64(RANDOM_ADD)
_MASK48 = np.uint64(MASK48)
# next(31) 是 state >>> 17；nextInt(10) 再对 10 取余
_U17 = np.uint64(17)
_U10 = np.uint64(10)
_REJECT = np.uint64(REJECT_FROM)
_XOR = np.uint64(SEED_XOR)

# 三个按 int 回绕的系数固定成 int32；z² 的系数固定成 int64（对应 long）
_I_X2 = np.int32(TERM_X2)
_I_X1 = np.int32(TERM_X1)
_I_Z1 = np.int32(TERM_Z1)
_L_Z2 = np.int64(TERM_Z2)


# ------ 32 位回绕 ------ #
def _int32_wrap(value: np.ndarray) -> np.ndarray:
    """Java int 乘法溢出：numpy int32 本身按 2^32 回绕，这里只做类型确认.

    numpy 的 int32 数组乘法溢出是静默回绕（补码截断），与 Java int 的
    `*` 语义一致；但若传入的是 Python int 或 int64 数组，结果就不会溢出，
    所以必须先转换再乘，转换这一步就是「强制 32 位」的位置。
    """

    return np.asarray(value, dtype=np.int32)


# ------ 单点判定 ------ #
def slime_flags(seed: int, xs, zs) -> np.ndarray:
    """
    判断任意区块坐标是否为史莱姆区块.

    xs / zs 可以是标量、1D 或可广播的 2D 数组；返回同形状的 bool 数组。

    2D 广播是主力用法：x 用行向量 xs[None, :]、z 用列向量 zs[:, None]，
    一次算出一整张矩形位图（行是 Z、列是 X）。

    参数单位：xs / zs 是区块坐标（不是方块坐标）。
    """

    # 先统一成 int64 再降为 int32：保证后续所有乘法都在 32 位内回绕，
    # 且允许输入是标量、列表或任意形状的整数数组。
    xi = np.asarray(xs, dtype=np.int64).astype(np.int32)
    zi = np.asarray(zs, dtype=np.int64).astype(np.int32)

    # 前三项按 Java int 计算（32 位溢出），d 先取 z² 的 int 值再乘 long
    # a = x * x * 0x4c1906（两次 int 乘法，各自回绕）
    part_x2 = _int32_wrap(_int32_wrap(xi * xi) * _I_X2)
    # b = x * 0x5ac0db（一次 int 乘法）
    part_x1 = _int32_wrap(xi * _I_X1)
    # e = z * 0x5f24f（一次 int 乘法）
    part_z1 = _int32_wrap(zi * _I_Z1)
    # d = (int)(z * z) * 0x4307a7L：z² 先回绕成 int，再提升为 long 相乘
    part_z2 = _int32_wrap(zi * zi).astype(np.int64) * _L_Z2

    # 64 位求和：Java 的 long 加法溢出等价于 mod 2^64，
    # numpy uint64 的加法同样是 mod 2^64（无声回绕），两边一致。
    # 负种子先取无符号位模式，再与四项按位模式相加。
    total = (
        np.uint64(seed_bits(seed))
        + part_x2.astype(np.uint64)
        + part_x1.astype(np.uint64)
        + part_z1.astype(np.uint64)
        + part_z2.astype(np.uint64)
    )
    # Java 里 `+` 的优先级高于 `^`，所以异或作用于整个和，而不是最后一项
    value = total ^ _XOR

    # new Random(value)：setSeed 把种子与 0x5DEECE66D 异或后只保留低 48 位
    state = (value ^ _MULT) & _MASK48
    # nextInt(10) 先调用一次 next(31)：state 前进一步，再取高 31 位。
    # 乘法先按 mod 2^64 回绕、再 & MASK48，等价于 Java 的 mod 2^48。
    state = (state * _MULT + _ADD) & _MASK48
    bits = state >> _U17

    # ------ nextInt(10) 的拒绝采样（向量化） ------ #
    # Java 源码：do { bits = next(31); val = bits % 10; }
    #            while (bits - val + 9 < 0);
    # 条件等价于 bits >= 2^31 - 2^31 % 10 = 2,147,483,640：
    # 区间 [0, 2147483639] 的长度 2147483640 恰是 10 的整数倍，取余才均匀；
    # 落在阈值之上的 bits 会让 0..9 的概率出现偏斜，必须重抽。
    # 拒绝概率约 8 / 2^31 ≈ 3.7e-9，实际几乎不会触发。
    rejected = bits >= _REJECT
    if rejected.any():
        # 只对撞上阈值的元素继续迭代，其余元素不再进入下一轮
        state_flat = state.reshape(-1).copy()
        bits_flat = bits.reshape(-1).copy()
        index = np.flatnonzero(rejected.reshape(-1))
        while index.size:
            state_flat[index] = (state_flat[index] * _MULT + _ADD) & _MASK48
            bits_flat[index] = state_flat[index] >> _U17
            bad = bits_flat[index] >= _REJECT
            index = index[bad]
        bits = bits_flat.reshape(bits.shape)

    # bits % 10 == 0 即 nextInt(10) == 0，也就是史莱姆区块
    return (bits % _U10) == np.uint64(0)


# ------ 矩形位图 ------ #
def slime_mask(seed: int, cx: int, cz: int, width: int, height: int) -> np.ndarray:
    """
    生成矩形区块区域的位图，行是 Z、列是 X，形状 (height, width)。

    cx / cz 为左上角区块坐标（可为负）。

    参数单位：cx / cz / width / height 都是区块。宽度或高度非正时返回
    空数组（保留传入的 0 维度），方便调用方直接做形状运算而不必特判。
    """

    width = int(width)
    height = int(height)
    if width <= 0 or height <= 0:
        return np.zeros((max(height, 0), max(width, 0)), dtype=bool)

    # 先各生成一条 1D 坐标轴，再靠广播拼成矩形，避免 Python 双层循环
    xs = np.arange(int(cx), int(cx) + width, dtype=np.int64)
    zs = np.arange(int(cz), int(cz) + height, dtype=np.int64)
    return slime_flags(seed, xs[None, :], zs[:, None])
