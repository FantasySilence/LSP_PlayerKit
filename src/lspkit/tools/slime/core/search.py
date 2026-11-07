# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-07                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 精确扫描与采样搜索       #
# =================================== #

from __future__ import annotations

import numpy as np

from ..constants import TILE_CHUNKS
from .mask import slime_flags, slime_mask
from .ring import ring_area
from .score import correlate, refine, suppress, tile_candidates

_OFFSETS = np.arange(-8, 9)
_DELTAS = np.array(
    [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)],
    dtype=np.int64,
)


# =================================== #
# @Section: 结果组装                   #
# =================================== #
def _make_result(score: float, x: int, z: int, total: float, rank: int) -> dict:
    coverage = 0.0 if total <= 0 else float(score) / float(total)
    return {
        "rank": int(rank),
        "x": int(x),
        "z": int(z),
        "chunkX": int(x) // 16,
        "chunkZ": int(z) // 16,
        "score": float(score),
        "coverage": round(coverage, 6),
    }


def _finalize(
    seed: int,
    chunks: list[tuple[float, int, int]],
    weights: np.ndarray,
    top_n: int,
    nms_chunks: int,
) -> list[dict]:
    kept = suppress(chunks, nms_chunks)
    refined = []
    for _, cx, cz in kept[: max(top_n * 8, top_n + 32)][:512]:
        score, x, z = refine(seed, cx, cz, weights)
        refined.append((score, x, z, cx, cz))
    refined.sort(key=lambda item: item[0], reverse=True)

    final: list[tuple[float, int, int, int, int]] = []
    for item in refined:
        _, _, _, cx, cz = item
        if nms_chunks > 0 and any(
            abs(cx - other[3]) <= nms_chunks and abs(cz - other[4]) <= nms_chunks
            for other in final
        ):
            continue
        final.append(item)
        if len(final) >= top_n:
            break

    total = float(ring_area(weights))
    return [
        _make_result(score, x, z, total, rank)
        for rank, (score, x, z, _, _) in enumerate(final, 1)
    ]


# =================================== #
# @Section: 精确扫描                   #
# =================================== #
def scan_exact(
    seed: int,
    cx0: int,
    cz0: int,
    width: int,
    height: int,
    weights: np.ndarray,
    top_n: int,
    nms_chunks: int,
    progress=None,
    cancel=None,
    tile: int = TILE_CHUNKS,
) -> list[dict] | None:
    """
    逐块扫描区域内所有区块，返回全局 Top-N.

    progress(done_chunks, total_chunks, best_score)；cancel() 返回 True 时中止并返回 None。
    """

    kernel = weights[:, :, 8, 8].astype(np.float32)
    total = width * height
    done = 0
    pool: list[tuple[float, int, int]] = []

    for tz in range(0, height, tile):
        block_h = min(tile, height - tz)
        for tx in range(0, width, tile):
            if cancel is not None and cancel():
                return None
            block_w = min(tile, width - tx)
            mask = slime_mask(
                seed, cx0 + tx - 8, cz0 + tz - 8, block_w + 16, block_h + 16
            )
            scores = correlate(mask, kernel)
            raw_limit = min(4096, max(256, top_n * 8))
            raw = tile_candidates(scores, cx0 + tx, cz0 + tz, raw_limit)
            if nms_chunks > 0 and raw:
                raw = suppress(raw, nms_chunks)[:256]
            pool.extend(raw)
            done += block_w * block_h
            if progress is not None:
                best = pool[-1][0] if pool else 0.0
                progress(done, total, best)

    if not pool:
        return []
    return _finalize(seed, pool, weights, top_n, nms_chunks)


# =================================== #
# @Section: 采样搜索                   #
# =================================== #
def _center_scores(
    seed: int, chunks: np.ndarray, kernel: np.ndarray
) -> np.ndarray:
    """一批区块中心的得分（向量化）."""

    cx = chunks[:, 0][:, None, None]
    cz = chunks[:, 1][:, None, None]
    cxs = cx + _OFFSETS[None, :, None]
    czs = cz + _OFFSETS[None, None, :]
    flags = slime_flags(seed, cxs, czs)
    return (flags * kernel[None, :, :]).sum(axis=(1, 2))


def _batch_scores(
    seed: int,
    xs: np.ndarray,
    zs: np.ndarray,
    weights: np.ndarray,
) -> np.ndarray:
    """任意块坐标（含块内偏移）的精确得分."""

    chunk_x = xs // 16
    chunk_z = zs // 16
    sub_x = xs % 16
    sub_z = zs % 16
    cxs = chunk_x[:, None, None] + _OFFSETS[None, :, None]
    czs = chunk_z[:, None, None] + _OFFSETS[None, None, :]
    flags = slime_flags(seed, cxs, czs)
    table = np.moveaxis(weights[:, :, sub_x, sub_z], -1, 0)
    return (flags * table).sum(axis=(1, 2))


def _hill_climb(
    seed: int,
    chunks: np.ndarray,
    kernel: np.ndarray,
    cx0: int,
    cz0: int,
    width: int,
    height: int,
    steps: int = 8,
) -> tuple[np.ndarray, np.ndarray]:
    if chunks.size == 0:
        return chunks, np.zeros(0)
    current = chunks.astype(np.int64).copy()
    current_score = _center_scores(seed, current, kernel)
    rows = np.arange(len(current))
    for _ in range(max(steps, 1)):
        candidate = current[:, None, :] + _DELTAS[None, :, :]
        candidate[:, :, 0] = np.clip(candidate[:, :, 0], cx0, cx0 + width - 1)
        candidate[:, :, 1] = np.clip(candidate[:, :, 1], cz0, cz0 + height - 1)
        flat = candidate.reshape(-1, 2)
        scores = _center_scores(seed, flat, kernel).reshape(len(current), -1)
        best_index = scores.argmax(axis=1)
        best_score = scores[rows, best_index]
        improved = best_score > current_score + 1e-9
        if not improved.any():
            break
        moved = candidate[rows, best_index]
        current = np.where(improved[:, None], moved, current)
        current_score = np.where(improved, best_score, current_score)
    return current, current_score


def scan_sample(
    seed: int,
    cx0: int,
    cz0: int,
    width: int,
    height: int,
    weights: np.ndarray,
    samples: int,
    top_n: int,
    nms_chunks: int,
    rng: np.random.Generator | None = None,
    progress=None,
    cancel=None,
) -> dict | None:
    """
    大范围采样：随机取点 + 局部爬山 + 块内精修.

    返回 {results, samples, percentile, bestScore, scannedChunks}；
    结果是“预算内找到的最好点”，不保证全图全局最优。
    """

    rng = rng or np.random.default_rng(20261107)
    bx0 = int(cx0) * 16
    bx1 = int(cx0 + width) * 16
    bz0 = int(cz0) * 16
    bz1 = int(cz0 + height) * 16
    kernel = weights[:, :, 8, 8].astype(np.float32)

    batch = 2000
    pool: list[tuple[float, int, int]] = []
    all_scores: list[np.ndarray] = []
    done = 0

    for start in range(0, samples, batch):
        if cancel is not None and cancel():
            return None
        count = min(batch, samples - start)
        xs = rng.integers(bx0, bx1, count, dtype=np.int64)
        zs = rng.integers(bz0, bz1, count, dtype=np.int64)
        scores = _batch_scores(seed, xs, zs, weights)
        all_scores.append(scores)
        keep = min(count, 32)
        index = np.argpartition(scores, -keep)[-keep:]
        for item in index:
            pool.append(
                (
                    float(scores[item]),
                    int(xs[item] // 16),
                    int(zs[item] // 16),
                )
            )
        done += count
        if progress is not None:
            progress(done, samples, max(pool)[0] if pool else 0.0)

    pool.sort(key=lambda item: item[0], reverse=True)
    picked = suppress(pool, max(1, nms_chunks))[:200]
    if not picked:
        return {
            "results": [],
            "samples": 0,
            "percentile": 0.0,
            "bestScore": 0.0,
            "scannedChunks": 0,
        }

    positions = np.array([(cx, cz) for _, cx, cz in picked], dtype=np.int64)
    climbed, _ = _hill_climb(seed, positions, kernel, cx0, cz0, width, height)

    unique: list[tuple[int, int]] = []
    seen = set()
    for cx, cz in climbed.tolist():
        key = (int(cx), int(cz))
        if key not in seen:
            seen.add(key)
            unique.append(key)

    total = float(ring_area(weights))
    refined = []
    for cx, cz in unique[: max(top_n * 3, top_n + 16)]:
        score, x, z = refine(seed, cx, cz, weights)
        refined.append((score, x, z, cx, cz))
    refined.sort(key=lambda item: item[0], reverse=True)

    final = []
    for item in refined:
        _, _, _, cx, cz = item
        if nms_chunks > 0 and any(
            abs(cx - other[3]) <= nms_chunks and abs(cz - other[4]) <= nms_chunks
            for other in final
        ):
            continue
        final.append(item)
        if len(final) >= top_n:
            break

    results = [
        _make_result(score, x, z, total, rank)
        for rank, (score, x, z, _, _) in enumerate(final, 1)
    ]
    best = results[0]["score"] if results else 0.0
    merged = np.concatenate(all_scores) if all_scores else np.zeros(0)
    percentile = float((merged < best).mean()) if merged.size else 0.0
    return {
        "results": results,
        "samples": int(merged.size),
        "percentile": round(percentile, 6),
        "bestScore": float(best),
        "scannedChunks": 0,
    }
