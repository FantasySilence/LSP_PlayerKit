# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-07                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 精确扫描与采样搜索       #
# =================================== #
"""
两种找「好挂机点」的策略：

- scan_exact：把搜索区域切成分块，逐块做完整的互相关，拿到全图精确的
  Top-N。区域再大结果也不会漏，代价是 O(区块数) 的卷积，只适合中小范围。
- scan_sample：大范围随机取点 + 局部爬山，再用块内精修收敛。速度快得多，
  但只保证「预算内找到的最好点」，不保证全局最优。

两者共用同一套收尾流程：候选点先按区块做一次 NMS，再逐点做 16×16 精修，
最后再按区块做一次 NMS 并取前 top_n 条。

坐标与方向约定：位图与得分图的行是 Z、列是 X；对外结果统一给出方块
坐标 (x, z) 和区块坐标 (chunkX, chunkZ)，换算用 Python 的 // 与 %
（对负数向下取整，正好等于 floor(方块 / 16)）。
"""

from __future__ import annotations

import numpy as np

from ..constants import TILE_CHUNKS
from .mask import slime_flags, slime_mask
from .ring import ring_area
from .score import correlate, refine, suppress, tile_candidates

# 邻域偏移：-8..+8 共 17 个相对区块，正好覆盖外半径 128 格（8 区块）
_OFFSETS = np.arange(-8, 9)
# 爬山用的 3×3 邻域（含原地不动），第 0 个 (0, 0) 让当前点也参与比较
_DELTAS = np.array(
    [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)],
    dtype=np.int64,
)


# =================================== #
# @Section: 结果组装                   #
# =================================== #
def _make_result(score: float, x: int, z: int, total: float, rank: int) -> dict:
    """把内部候选 (score, 方块 x, 方块 z) 组装成对外的结果行.

    坐标换算：
    - chunkX = x // 16、chunkZ = z // 16，等价于 floor(方块 / 16)；
      Python 的 // 对负数是向下取整，所以负数坐标也不会偏一格。
    - score 单位是格²（环带内落在史莱姆区块的方块数），total 是环面积，
      coverage = score / total 即环带被覆盖的比例，四舍五入到 6 位小数。
    """

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
    """精确扫描的收尾：区块级 NMS → 逐点精修 → 再 NMS → 取前 top_n 条.

    为什么要做两次 NMS：
    1. 精修前按区块压一遍，避免把几十个候选都花在同一个刷怪点周围；
    2. 精修会把挂机点挪到区块内的最优方块，可能挪进相邻区块，
       所以排序后还要按区块再压一遍，保证最终结果两两间距足够。
    """

    # 第一轮：按区块坐标压掉过密的候选（切比雪夫距离 <= nms_chunks 的全部丢弃）
    kept = suppress(chunks, nms_chunks)
    refined = []
    # 精修很贵（每个点一次 17×17 掩码 + 256 点矩阵乘），所以限制数量：
    # 最多精修 max(top_n × 8, top_n + 32) 个候选，并硬性截到 512 个。
    for _, cx, cz in kept[: max(top_n * 8, top_n + 32)][:512]:
        score, x, z = refine(seed, cx, cz, weights)
        refined.append((score, x, z, cx, cz))
    # 按精修后的真实得分重排，原来的区块级估值只用来挑候选
    refined.sort(key=lambda item: item[0], reverse=True)

    # 第二轮：精修后可能跨区块，再按区块压一遍，凑满 top_n 就停
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

    # 环面积对 256 个块内偏移都相同，所以 coverage 可以直接用 (8, 8) 的值
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

    分块策略（tile = 1024 区块）：
    - 每块实际算 (block_w + 16) × (block_h + 16) 的位图，四周各带 8 区块
      halo，这样 correlate 的 valid 输出正好是 block_h × block_w；
    - 块与块之间的 halo 会重复计算，但换来「每块独立、可随时取消」；
      总区块数按 block_w × block_h 累计，不含 halo。
    参数单位：cx0 / cz0 是左上角区块坐标，width / height 是区块数，
    tile 是分块边长（区块）。
    """

    # 扫描阶段统一用区块中心 (8, 8) 的核估分；(17, 17) 的窗口对应 ±8 区块
    kernel = weights[:, :, 8, 8].astype(np.float32)
    total = width * height
    done = 0
    pool: list[tuple[float, int, int]] = []

    for tz in range(0, height, tile):
        block_h = min(tile, height - tz)
        for tx in range(0, width, tile):
            # 每个分块开始前检查一次取消标志，粒度是「一块」，
            # 也就是中止延迟最多一个分块的计算时间
            if cancel is not None and cancel():
                return None
            block_w = min(tile, width - tx)
            # 左上角各退 8 个区块作为 halo，尺寸相应 +16
            mask = slime_mask(
                seed, cx0 + tx - 8, cz0 + tz - 8, block_w + 16, block_h + 16
            )
            scores = correlate(mask, kernel)
            # 每块保留的原始候选数：至少 256，随 top_n 放大，封顶 4096，
            # 避免小 top_n 时漏掉「块内并列、精修后才胜出」的点。
            raw_limit = min(4096, max(256, top_n * 8))
            raw = tile_candidates(scores, cx0 + tx, cz0 + tz, raw_limit)
            # 块内先压一遍，块内过密的候选不必带进全局池
            if nms_chunks > 0 and raw:
                raw = suppress(raw, nms_chunks)[:256]
            pool.extend(raw)
            done += block_w * block_h
            if progress is not None:
                # 这里的 best 只是最近一次追加的候选分数，用作进度条上界提示，
                # 不是全局最大值（全局排序在 _finalize 里做）。
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
    """一批区块中心的得分（向量化）.

    chunks 形状 (n, 2)，每行是 (chunkX, chunkZ)；返回 (n,) 的得分。
    这里假设挂机点在该区块中心，即用 (8, 8) 偏移的核，所以是「估分」，
    真正的最优块内偏移由 refine 决定。

    做法：把每个区块扩成 17×17 的邻域（_OFFSETS 广播），一次算 n 张位图，
    再与 17×17 的核逐元素相乘求和。
    """

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
    """任意块坐标（含块内偏移）的精确得分.

    xs / zs 是方块坐标（不是区块坐标），形状 (n,)；返回 (n,) 的得分。
    与 _center_scores 的区别：这里按每个点自己的块内偏移取权重表，
    所以得到的是精确得分，可以直接用来比较不同块内位置。

    步骤：
    1. 方块坐标拆成 区块坐标（// 16）与块内偏移（% 16）；
    2. 每个点扩成 17×17 区块邻域，算史莱姆位图；
    3. 从 (17, 17, 16, 16) 的权重表里按每个点的 (sub_x, sub_z) 取切片，
       得到 (n, 17, 17)，与位图逐元素相乘求和。
    """

    chunk_x = xs // 16
    chunk_z = zs // 16
    sub_x = xs % 16
    sub_z = zs % 16
    cxs = chunk_x[:, None, None] + _OFFSETS[None, :, None]
    czs = chunk_z[:, None, None] + _OFFSETS[None, None, :]
    flags = slime_flags(seed, cxs, czs)
    # weights[:, :, sub_x, sub_z] 的形状是 (17, 17, n)，把批量轴挪到最前
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
    """对一批起点做区块级爬山，返回收敛后的区块坐标与得分.

    每一轮在 3×3 邻域（含原地）里选得分最高的位置；只有严格变好才移动，
    一旦所有起点都不再变好就提前结束。坐标被夹在搜索区域内，不会爬出去。
    步长是 1 个区块，8 轮最多移动 8 个区块——足够跳出随机取点的颗粒度，
    更细的块内最优交给 refine。
    """

    if chunks.size == 0:
        return chunks, np.zeros(0)
    current = chunks.astype(np.int64).copy()
    # 用区块中心估分作为起点分数
    current_score = _center_scores(seed, current, kernel)
    rows = np.arange(len(current))
    for _ in range(max(steps, 1)):
        # (n, 1, 2) + (1, 9, 2) → (n, 9, 2)：每个起点的 9 个邻居
        candidate = current[:, None, :] + _DELTAS[None, :, :]
        candidate[:, :, 0] = np.clip(candidate[:, :, 0], cx0, cx0 + width - 1)
        candidate[:, :, 1] = np.clip(candidate[:, :, 1], cz0, cz0 + height - 1)
        flat = candidate.reshape(-1, 2)
        scores = _center_scores(seed, flat, kernel).reshape(len(current), -1)
        best_index = scores.argmax(axis=1)
        best_score = scores[rows, best_index]
        # 1e-9 容差：得分是整数，浮点相等时不该算「变好」
        improved = best_score > current_score + 1e-9
        if not improved.any():
            break
        moved = candidate[rows, best_index]
        # 只让真正变好的起点移动，其余保持原地
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

    流程（每批 2000 点，逐批累加）：
    1. 在搜索区域对应的方块范围里均匀撒点，算精确得分；
    2. 每批留前 32 名，攒成一个候选池；
    3. 池子排序、按区块 NMS 压到 200 个，作为爬山起点；
    4. 区块级爬山收敛后再去重，逐点做 16×16 精修；
    5. 按精修得分重排、再做一次区块 NMS，取前 top_n。

    参数单位：cx0 / cz0 / width / height 是区块，samples 是取点次数；
    rng 传入时用于复现实验，默认用固定种子 20261107，保证同参数结果一致。
    """

    rng = rng or np.random.default_rng(20261107)
    # 区块范围换算成方块范围（右端开区间），随机数直接撒在方块坐标上
    bx0 = int(cx0) * 16
    bx1 = int(cx0 + width) * 16
    bz0 = int(cz0) * 16
    bz1 = int(cz0 + height) * 16
    kernel = weights[:, :, 8, 8].astype(np.float32)

    batch = 2000
    pool: list[tuple[float, int, int]] = []
    # 保留所有采样得分，只用来事后算 percentile（最优解超过多少比例的随机点）
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
        # 每批只留前 32 名（argpartition 为 O(n)，不排序），
        # 候选池按「每批 32 个」增长，远小于 samples 本身，
        # 这样后续 NMS 不会被采样数直接拖垮。
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
            # pool 里是 (score, cx, cz) 元组，max 会先比 score，即当前最好分数
            progress(done, samples, max(pool)[0] if pool else 0.0)

    # 候选池整体排序后，按区块压到 200 个爬山起点。
    # 半径至少取 1：多起点收敛到同一区块没有意义，先粗去重。
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

    # 以被选中的区块为起点做爬山；返回的分数这里用不到（后面会精修重算）
    positions = np.array([(cx, cz) for _, cx, cz in picked], dtype=np.int64)
    climbed, _ = _hill_climb(seed, positions, kernel, cx0, cz0, width, height)

    # 不同起点可能爬进同一个区块，收敛后要去重，避免重复精修
    unique: list[tuple[int, int]] = []
    seen = set()
    for cx, cz in climbed.tolist():
        key = (int(cx), int(cz))
        if key not in seen:
            seen.add(key)
            unique.append(key)

    total = float(ring_area(weights))
    refined = []
    # 精修上限与 _finalize 同一思路：给 top_n 留 3 倍余量，另加常数项，
    # 因为精修会改变名次，只精修前 top_n 个可能漏掉好点。
    for cx, cz in unique[: max(top_n * 3, top_n + 16)]:
        score, x, z = refine(seed, cx, cz, weights)
        refined.append((score, x, z, cx, cz))
    refined.sort(key=lambda item: item[0], reverse=True)

    # 精修后按区块再压一遍，凑满 top_n 就停
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
    # percentile：所有采样点里得分严格低于最终最优值的比例，
    # 用来告诉用户「这个结果比多少随机点更好」。
    merged = np.concatenate(all_scores) if all_scores else np.zeros(0)
    percentile = float((merged < best).mean()) if merged.size else 0.0
    return {
        "results": results,
        "samples": int(merged.size),
        "percentile": round(percentile, 6),
        "bestScore": float(best),
        # 采样模式不统计「扫描过多少区块」，该字段固定为 0
        "scannedChunks": 0,
    }
