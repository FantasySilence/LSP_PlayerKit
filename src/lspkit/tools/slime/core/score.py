# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-07                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 得分卷积与候选筛选       #
# =================================== #
"""
从区块位图到「挂机点得分」的中间层，包含四件事：

1. 互相关 correlate：把 17×17 的圆环权重核扫过位图，得到每个区块位置的
   得分，单位是「格²」，即该挂机点的环带里有多少格落在史莱姆区块内；
2. 候选挑选 tile_candidates：用 partial select 取一块得分图里的前若干名；
3. 非极大值抑制 suppress：按切比雪夫距离（区块）压掉挨得太近的结果，
   避免同一个刷怪场被报成好几个点；
4. 块内精修 refine：对给定区块枚举 16×16 个具体挂机点，挑出真正的最高分。

得分口径：score = Σ(权重 × 是否史莱姆区块)，权重是该区块内落在环带里的
格数，所以 score 的上限就是圆环面积 ring_area（默认 49,640 格²），
coverage = score / ring_area 就是环带被史莱姆区块覆盖的比例。
"""

from __future__ import annotations

import numpy as np

from ..constants import FFT_MIN_CELLS
from .mask import slime_mask

# 直接相关与 FFT 的切换阈值来自 constants.FFT_MIN_CELLS，
# 判定对象是「输出格数」而不是输入掩码大小（见 correlate）。


# ------ 卷积尺寸 ------ #
def _fast_len(size: int) -> int:
    """取不小于 size 的 2^a·3^b·5^c，FFT 用."""

    # 5-smooth 长度能让 numpy 的 FFT 只做小素数分解；best 先取「不小于
    # size 的 2 的幂」当上界，再往下找到最小的 5-smooth 长度，
    # 这样比硬补到 2 的幂更省内存。
    size = max(int(size), 1)
    best = 1 << (size - 1).bit_length()
    # 枚举 5^c 与 3^b（p35 = 3^b · 5^c），再补 2 的幂直到 >= size，
    # 过程中不断收紧上界 best，最后得到最小的 5-smooth 长度。
    p5 = 1
    while p5 < best:
        p35 = p5
        while p35 < best:
            value = p35
            while value < size:
                value *= 2
            if value < best:
                best = value
            p35 *= 3
        p5 *= 5
    return best


# ------ 直接相关 ------ #
def _correlate_direct(mask: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """逐点累加的有效互相关：out[z, x] = Σ mask[z+i, x+j] · kernel[i, j].

    复杂度是 O(kh·kw·H·W)（17×17 最多 289 次整图乘加），小图比 FFT 快；
    核里权重为 0 的位置直接跳过（圆环表里大量区块权重为 0）。
    用 float32 累加：得分最大 49,640，远小于 float32 的精确整数范围 2^24，
    所以不会丢精度。
    """

    # 有效（valid）卷积的输出尺寸：核不越界，因此比输入小 kh-1 / kw-1
    height = mask.shape[0] - kernel.shape[0] + 1
    width = mask.shape[1] - kernel.shape[1] + 1
    out = np.zeros((height, width), dtype=np.float32)
    if height <= 0 or width <= 0:
        return out
    source = mask.astype(np.float32, copy=False)
    temp = np.empty_like(out)
    # 对核的每个位置，把整幅 mask 平移后乘权重累加；temp 复用避免反复分配
    for i in range(kernel.shape[0]):
        for j in range(kernel.shape[1]):
            weight = float(kernel[i, j])
            if weight == 0.0:
                continue
            np.multiply(source[i:i + height, j:j + width], weight, out=temp)
            np.add(out, temp, out=out)
    return out


# ------ FFT 相关 ------ #
def _correlate_fft(mask: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """用 FFT 做同一件事：大图下把 289 次整图乘加换成一次 FFT 卷积.

    技巧：先把核左右上下翻转，卷积就变成互相关；valid 输出
    (z, x) 对应 conv 下标 (z + kh - 1, x + kw - 1)，所以取
    conv[kh-1 : kh-1+H, kw-1 : kw-1+W] 这一段，把两端核只部分重叠的区域丢掉，
    与 _correlate_direct 的 valid 结果对齐。
    中间用 float64 计算，最后四舍五入回整数再转 float32：权重与掩码都是
    整数、得分上限 49,640，浮点误差远小于 0.5，rint 能还原精确的整数值。
    """

    kh, kw = kernel.shape
    height = mask.shape[0] - kh + 1
    width = mask.shape[1] - kw + 1
    if height <= 0 or width <= 0:
        return np.zeros((max(height, 0), max(width, 0)), dtype=np.float32)

    # 补零到 5-smooth 长度，避免线性卷积的循环混叠
    n0 = _fast_len(mask.shape[0] + kh - 1)
    n1 = _fast_len(mask.shape[1] + kw - 1)

    source = mask.astype(np.float64)
    flipped = np.zeros((n0, n1), dtype=np.float64)
    flipped[:kh, :kw] = kernel[::-1, ::-1].astype(np.float64)

    # 卷积定理：空间域卷积 = 频域逐点相乘。rfft2 只存半谱，省一半内存。
    product = np.fft.rfft2(source, s=(n0, n1)) * np.fft.rfft2(flipped, s=(n0, n1))
    conv = np.fft.irfft2(product, s=(n0, n1))
    # 取 valid 区域：卷积中核完全落在原图内的那一段
    out = conv[kh - 1:kh - 1 + height, kw - 1:kw - 1 + width]
    return np.rint(out).astype(np.float32)


# ------ 统一入口 ------ #
def correlate(mask: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """
    有效互相关：out[z, x] = Σ mask[z+i, x+j] · kernel[i, j].

    mask 为带 halo 的区块位图，输出比 mask 四周各少 8 个区块。

    （更一般地说，四周各少 kh-1 / kw-1 个区块；本工具的核固定是 17×17，
    所以恰好是每边 8 个区块的 halo。）

    参数单位：mask 是区块位图，kernel 的形状是 (17, 17) 区块权重。
    切换策略见下方注释：输出格数 >= FFT_MIN_CELLS 时走 FFT，否则逐点累加。
    """

    if mask.size == 0 or kernel.size == 0:
        return np.zeros((0, 0), dtype=np.float32)
    if mask.dtype != bool:
        mask = mask.astype(bool)
    kernel = np.asarray(kernel)
    height = mask.shape[0] - kernel.shape[0] + 1
    width = mask.shape[1] - kernel.shape[1] + 1
    if height <= 0 or width <= 0:
        return np.zeros((max(height, 0), max(width, 0)), dtype=np.float32)
    # 阈值判定用的是输出格数（height × width）：
    # 小图直接相关的常数更小；输出达到 20 万格后 FFT 的 O(N log N) 胜出。
    if height * width >= FFT_MIN_CELLS:
        return _correlate_fft(mask, kernel)
    return _correlate_direct(mask, kernel)


# ------ 候选挑选 ------ #
def tile_candidates(
    scores: np.ndarray, cx0: int, cz0: int, limit: int
) -> list[tuple[float, int, int]]:
    """取一块得分图里最高的 limit 个区块（返回 (score, cx, cz)）."""

    # argpartition 是 O(n) 的 partial select，只需要前 limit 名、不需要全排序；
    # 因此返回的顺序是「未排序」的，真正的排序与 NMS 在 search._finalize 里做。
    if scores.size == 0 or limit <= 0:
        return []
    flat = scores.reshape(-1)
    count = min(limit, flat.size)
    if count < flat.size:
        index = np.argpartition(flat, -count)[-count:]
    else:
        index = np.arange(flat.size)
    # 一维下标按行优先展开还原成二维坐标：行号是相对 Z、列号是相对 X
    width = scores.shape[1]
    result = []
    for item in index:
        item = int(item)
        result.append((float(flat[item]), int(cx0) + item % width, int(cz0) + item // width))
    return result


# ------ 非极大值抑制 ------ #
def suppress(
    candidates: list[tuple[float, int, int]], radius: int
) -> list[tuple[float, int, int]]:
    """按得分从高到低做非极大值抑制（切比雪夫距离）."""

    # 先按得分降序，贪心地保留：只要新点与每个已保留点在 X 或 Z 任一方向上
    # 的距离大于 radius（即切比雪夫距离 > radius）就留下，
    # 等价于压掉以已保留点为中心、半径 radius 的方块邻域。
    ordered = sorted(candidates, key=lambda item: item[0], reverse=True)
    if radius <= 0:
        # radius = 0 表示不做抑制，只按得分排序
        return ordered
    kept: list[tuple[float, int, int]] = []
    for score, cx, cz in ordered:
        if all(abs(cx - kx) > radius or abs(cz - kz) > radius for _, kx, kz in kept):
            kept.append((score, cx, cz))
    return kept


# ------ 块内精修 ------ #
def refine(
    seed: int, cx: int, cz: int, weights: np.ndarray
) -> tuple[float, int, int]:
    """在指定区块里枚举 16×16 个挂机点，取该区块内最优的块坐标."""

    # 以 (cx, cz) 为中心取 17×17 区块位图：行 Z、列 X
    mask = slime_mask(seed, cx - 8, cz - 8, 17, 17)  # 行 Z、列 X
    # 按 (x, z) 展开成 289 维，与权重表的「行 = 相对区块 (i, j)」对齐。
    # mask.T 之后 [x, z] 的行优先展开顺序即 i*17 + j。
    flat = mask.T.reshape(-1).astype(np.float32)  # 按 (x, z) 展开
    # weights 展平成 (289, 256)：行是相对区块，列是块内偏移 (sx*16 + sz)
    table = weights.reshape(17 * 17, 16 * 16)
    # 一次矩阵乘算出全部 256 个块内偏移的得分
    scores = flat @ table
    best = int(np.argmax(scores))
    # 列号拆回 (sx, sz)，再换算成方块坐标：区块原点 + 块内偏移
    sx, sz = divmod(best, 16)
    return float(scores[best]), int(cx) * 16 + sx, int(cz) * 16 + sz
