# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-07                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 得分卷积与候选筛选       #
# =================================== #

from __future__ import annotations

import numpy as np

from ..constants import FFT_MIN_CELLS
from .mask import slime_mask


def _fast_len(size: int) -> int:
    """取不小于 size 的 2^a·3^b·5^c，FFT 用."""

    size = max(int(size), 1)
    best = 1 << (size - 1).bit_length()
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


def _correlate_direct(mask: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    height = mask.shape[0] - kernel.shape[0] + 1
    width = mask.shape[1] - kernel.shape[1] + 1
    out = np.zeros((height, width), dtype=np.float32)
    if height <= 0 or width <= 0:
        return out
    source = mask.astype(np.float32, copy=False)
    temp = np.empty_like(out)
    for i in range(kernel.shape[0]):
        for j in range(kernel.shape[1]):
            weight = float(kernel[i, j])
            if weight == 0.0:
                continue
            np.multiply(source[i:i + height, j:j + width], weight, out=temp)
            np.add(out, temp, out=out)
    return out


def _correlate_fft(mask: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    kh, kw = kernel.shape
    height = mask.shape[0] - kh + 1
    width = mask.shape[1] - kw + 1
    if height <= 0 or width <= 0:
        return np.zeros((max(height, 0), max(width, 0)), dtype=np.float32)

    n0 = _fast_len(mask.shape[0] + kh - 1)
    n1 = _fast_len(mask.shape[1] + kw - 1)

    source = mask.astype(np.float64)
    flipped = np.zeros((n0, n1), dtype=np.float64)
    flipped[:kh, :kw] = kernel[::-1, ::-1].astype(np.float64)

    product = np.fft.rfft2(source, s=(n0, n1)) * np.fft.rfft2(flipped, s=(n0, n1))
    conv = np.fft.irfft2(product, s=(n0, n1))
    out = conv[kh - 1:kh - 1 + height, kw - 1:kw - 1 + width]
    return np.rint(out).astype(np.float32)


def correlate(mask: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """
    有效互相关：out[z, x] = Σ mask[z+i, x+j] · kernel[i, j].

    mask 为带 halo 的区块位图，输出比 mask 四周各少 8 个区块。
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
    if height * width >= FFT_MIN_CELLS:
        return _correlate_fft(mask, kernel)
    return _correlate_direct(mask, kernel)


def tile_candidates(
    scores: np.ndarray, cx0: int, cz0: int, limit: int
) -> list[tuple[float, int, int]]:
    """取一块得分图里最高的 limit 个区块（返回 (score, cx, cz)）."""

    if scores.size == 0 or limit <= 0:
        return []
    flat = scores.reshape(-1)
    count = min(limit, flat.size)
    if count < flat.size:
        index = np.argpartition(flat, -count)[-count:]
    else:
        index = np.arange(flat.size)
    width = scores.shape[1]
    result = []
    for item in index:
        item = int(item)
        result.append((float(flat[item]), int(cx0) + item % width, int(cz0) + item // width))
    return result


def suppress(
    candidates: list[tuple[float, int, int]], radius: int
) -> list[tuple[float, int, int]]:
    """按得分从高到低做非极大值抑制（切比雪夫距离）."""

    ordered = sorted(candidates, key=lambda item: item[0], reverse=True)
    if radius <= 0:
        return ordered
    kept: list[tuple[float, int, int]] = []
    for score, cx, cz in ordered:
        if all(abs(cx - kx) > radius or abs(cz - kz) > radius for _, kx, kz in kept):
            kept.append((score, cx, cz))
    return kept


def refine(
    seed: int, cx: int, cz: int, weights: np.ndarray
) -> tuple[float, int, int]:
    """在指定区块里枚举 16×16 个挂机点，取该区块内最优的块坐标."""

    mask = slime_mask(seed, cx - 8, cz - 8, 17, 17)  # 行 Z、列 X
    flat = mask.T.reshape(-1).astype(np.float32)  # 按 (x, z) 展开
    table = weights.reshape(17 * 17, 16 * 16)
    scores = flat @ table
    best = int(np.argmax(scores))
    sx, sz = divmod(best, 16)
    return float(scores[best]), int(cx) * 16 + sx, int(cz) * 16 + sz
