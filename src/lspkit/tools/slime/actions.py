# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-07                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 史莱姆区块查找器动作      #
# =================================== #
"""
史莱姆区块查找器的动作层：校验前端参数、调用 core/ 里的纯计算、组织返回。

六个对外动作：
- find        ：同步查找，只用于小范围（受 MAX_SYNC_CHUNKS 与 exactLimit 双重限制）；
- scan_start  ：起一个后台线程做精确扫描或采样，立刻返回 scanId；
- scan_status ：轮询进度与结果，附带 elapsed / progress；
- scan_stop   ：置取消标志，后台线程在分块/分批之间退出并把状态标成 aborted；
- map         ：给前端地图用，返回位图 bits（可带 heat 热力图）；
- seed_preview：只解析种子、不计算，返回解析出的 long 与原始输入。

并发约定：
- _SCANS 保存所有扫描任务（scanId → {record, cancel}），读写都在 _LOCK 下；
- 后台线程只改 record 里的字段，scan_status 取快照时整体浅拷贝一层，
  避免一边序列化一边被写；
- 扫描任务是 daemon 线程，进程退出时不会阻塞。

单位约定：搜索范围、圆环半径用「格」（方块），区块数用「区块」，
时间用秒；返回里的 score 单位是格²（环带内落在史莱姆区块的面积）。
"""

from __future__ import annotations

import base64
import threading
import time
import uuid

import numpy as np

from lspkit.errors import AppError
from lspkit.platform import params

from .constants import (
    DEFAULT_EXACT_CHUNKS,
    DEFAULT_NMS_CHUNKS,
    DEFAULT_RING_INNER,
    DEFAULT_RING_OUTER,
    DEFAULT_SAMPLES,
    DEFAULT_SIM_DISTANCE,
    DEFAULT_TOP_N,
    MAX_EXACT_CHUNKS,
    MAX_MAP_CELLS,
    MAX_SAMPLES,
    MAX_SYNC_CHUNKS,
    MAX_TOP_N,
    MIN_EXACT_CHUNKS,
    TILE_CHUNKS,
    WORLD_MAX,
    WORLD_MIN,
)
from .core.mask import slime_flags, slime_mask
from .core.ring import build_weights, ring_area
from .core.score import correlate
from .core.search import scan_exact, scan_sample
from .core.seed import parse_seed

# 圆环权重表按 (inner, outer) 缓存：构表要算 287×287 前缀和，而同一组
# 参数在一次会话里会被反复用到（每次扫描、每次地图热力图都要）。
_WEIGHTS: dict[tuple[float, float], np.ndarray] = {}
# 扫描任务表：scanId → {"record": 进度与结果, "cancel": 取消事件}
_SCANS: dict[str, dict] = {}
# 保护 _SCANS 与其中 record 字段的互斥锁（后台线程与 status 轮询并发）
_LOCK = threading.Lock()
# 内存里最多保留多少个已结束的扫描记录（运行中的不受影响）
_MAX_KEEP_RUNS = 10


# =================================== #
# @Section: 参数校验                   #
# =================================== #
def _seed(payload: dict, settings: dict) -> int:
    """取种子：请求里的 seed 优先，缺省回落到设置里的默认值.

    前端一律传字符串，这里交给 core.seed.parse_seed 按 Java 规则解析
    （十进制 long 或 String.hashCode）。解析失败翻译成 INVALID_SEED，
    并把原始输入塞进 detail 方便前端提示。
    """

    raw = payload.get("seed")
    if raw is None or str(raw).strip() == "":
        raw = settings.get("seed", "0")
    try:
        return parse_seed(raw)
    except ValueError as exc:
        raise AppError("INVALID_SEED", str(exc), str(raw)) from None


def _weights(inner: float, outer: float) -> np.ndarray:
    """按 (inner, outer) 取圆环权重表，未命中就构造并缓存.

    键用 float 归一化，避免 24 与 24.0 被当成两个键。
    内外半径的组合在设置面板里有限，缓存不会无限增长。
    """

    key = (float(inner), float(outer))
    cached = _WEIGHTS.get(key)
    if cached is None:
        cached = build_weights(inner, outer)
        _WEIGHTS[key] = cached
    return cached


def _ring(payload: dict, settings: dict) -> tuple[int, int, np.ndarray]:
    """解析并校验圆环参数，返回 (内半径, 外半径, 权重表).

    校验顺序：
    1. 内半径 [0, 127]、外半径 [1, 128]，单位格；
    2. 外半径再被模拟距离夹住：模拟距离外的区块不 tick，环带再大也没意义，
       所以 outer = min(outer, simDistance × 16)；
    3. 夹完之后必须 outer > inner，否则环带为空；
    4. 权重表面积必须 > 0（理论上非空环一定 > 0，这里兜底）。
    """

    inner = params.integer(
        payload, "ringInner", default=settings.get("ringInner", DEFAULT_RING_INNER),
        minimum=0, maximum=127, label="圆环内半径",
    )
    outer = params.integer(
        payload, "ringOuter", default=settings.get("ringOuter", DEFAULT_RING_OUTER),
        minimum=1, maximum=128, label="圆环外半径",
    )
    sim = params.integer(
        payload, "simDistance",
        default=settings.get("simDistance", DEFAULT_SIM_DISTANCE),
        minimum=1, maximum=32, label="模拟距离",
    )
    # 模拟距离以区块计，乘 16 换算成方块半径后作为外半径的上界
    outer = min(outer, sim * 16)
    if outer <= inner:
        raise AppError(
            "INVALID_RING",
            "圆环为空：请增大外半径或减小模拟距离限制",
            f"inner={inner}, outer={outer}, sim={sim}",
        )
    weights = _weights(inner, outer)
    if ring_area(weights) <= 0:
        raise AppError("INVALID_RING", "圆环面积为 0，请检查内外半径")
    return inner, outer, weights


def _area(payload: dict) -> dict:
    """解析搜索范围（格），换算成区块网格，返回统一的 area 字典.

    处理细节：
    - 两个角点先排序，前端传反了也能用；
    - 边界必须在 Java 版世界范围内（±29,999,984 格）；
    - 区块索引用 floor(格 / 16)；右端减 1e-6 是为了把「恰好落在区块边界」
      的 x1 / z1 归到前一个区块（区间按左闭右开处理），这样
      x0=x1 这类退化范围会被判成空；
    - 返回 width / height 是区块数（不是格）。
    """

    area = payload.get("area")
    if not isinstance(area, dict):
        raise AppError("INVALID_PAYLOAD", "缺少搜索范围")
    x0 = params.number(area, "x0", label="范围 X1")
    z0 = params.number(area, "z0", label="范围 Z1")
    x1 = params.number(area, "x1", label="范围 X2")
    z1 = params.number(area, "z1", label="范围 Z2")
    # 角点排序：允许用户从任意方向拉框
    x0, x1 = sorted((float(x0), float(x1)))
    z0, z1 = sorted((float(z0), float(z1)))
    if x0 < WORLD_MIN or x1 > WORLD_MAX or z0 < WORLD_MIN or z1 > WORLD_MAX:
        raise AppError(
            "AREA_OUT_OF_WORLD",
            f"搜索范围超出世界边界（{WORLD_MIN} ~ {WORLD_MAX}）",
        )
    # 方块坐标 → 区块坐标；右端 -1e-6 让边界点留在左闭右开区间内
    cx0 = int(np.floor(x0 / 16.0))
    cx1 = int(np.floor((x1 - 1e-6) / 16.0))
    cz0 = int(np.floor(z0 / 16.0))
    cz1 = int(np.floor((z1 - 1e-6) / 16.0))
    if cx1 < cx0 or cz1 < cz0:
        raise AppError("INVALID_AREA", "搜索范围为空")
    return {
        "x0": x0, "z0": z0, "x1": x1, "z1": z1,
        "cx0": cx0, "cz0": cz0,
        "width": cx1 - cx0 + 1, "height": cz1 - cz0 + 1,
    }


def _exact_limit(settings: dict) -> int:
    """返回用户设置的精确扫描上限；0 表示不限制。"""

    # 非数字或类型不对时退回默认值（默认 0 = 不限制）
    try:
        value = int(settings.get("exactLimit", DEFAULT_EXACT_CHUNKS))
    except (TypeError, ValueError):
        value = DEFAULT_EXACT_CHUNKS
    # 负数按 0（不限制）处理；正数夹到 [MIN_EXACT_CHUNKS, MAX_EXACT_CHUNKS]
    if value <= 0:
        return 0
    return max(MIN_EXACT_CHUNKS, min(MAX_EXACT_CHUNKS, value))


def _mode(payload: dict, settings: dict, chunks: int) -> str:
    """决定本次扫描用 exact 还是 sample；返回最终生效的模式.

    auto 的规则：没有设置上限（limit == 0）时始终精确扫描；设了上限时，
    区块数不超上限就精确、超了就自动转采样。
    显式指定 exact 且超上限时报 AREA_TOO_LARGE，让用户自己决定放宽上限
    还是缩小范围——这里不静默降级，避免结果口径和用户预期不符。
    """

    mode = payload.get("mode") or settings.get("mode", "auto")
    if mode not in ("auto", "exact", "sample"):
        raise AppError("INVALID_INPUT", "mode 只能是 auto / exact / sample")
    limit = _exact_limit(settings)
    if mode == "auto":
        # 未设上限（0）时始终精确扫描；设了上限则超限自动转采样
        return "exact" if limit == 0 or chunks <= limit else "sample"
    if mode == "exact" and limit > 0 and chunks > limit:
        raise AppError(
            "AREA_TOO_LARGE",
            f"精确扫描上限为 {limit:,} 个区块，请改用采样、缩小范围或在设置里调大上限",
        )
    return mode


def _top_n(payload: dict, settings: dict) -> int:
    """返回结果条数，夹在 [1, MAX_TOP_N] 之间."""

    return params.integer(
        payload, "topN", default=settings.get("topN", DEFAULT_TOP_N),
        minimum=1, maximum=MAX_TOP_N, label="结果数量",
    )


def _nms(payload: dict, settings: dict) -> int:
    """结果之间的最小间距（区块）；0 表示不做非极大值抑制."""

    return params.integer(
        payload, "nmsChunks", default=settings.get("nmsChunks", DEFAULT_NMS_CHUNKS),
        minimum=0, maximum=32, label="结果间距",
    )


def _samples(payload: dict, settings: dict) -> int:
    """采样模式的随机取点次数，夹在 [1000, MAX_SAMPLES] 之间."""

    return params.integer(
        payload, "samples", default=settings.get("samples", DEFAULT_SAMPLES),
        minimum=1000, maximum=MAX_SAMPLES, label="采样次数",
    )


# =================================== #
# @Section: 同步查找（测试 / 小范围）  #
# =================================== #
def find_action(payload: dict, ctx) -> dict:
    """同步精确查找：一次调用算完并直接返回结果表.

    只适合小范围：区块数不能超过用户设置的 exactLimit（设了的话），
    未设上限时也不能超过 MAX_SYNC_CHUNKS，否则请改用 scan_start 后台跑，
    以免请求线程被长时间占住。
    """

    settings = ctx.settings("slime")
    seed = _seed(payload, settings)
    area = _area(payload)
    inner, outer, weights = _ring(payload, settings)
    top_n = _top_n(payload, settings)
    nms = _nms(payload, settings)
    chunks = area["width"] * area["height"]
    limit = _exact_limit(settings)
    # 有上限时以用户上限为准，否则用同步接口自己的保护上限
    if chunks > (limit if limit > 0 else MAX_SYNC_CHUNKS):
        raise AppError("AREA_TOO_LARGE", "同步查找范围过大，请改用 scan_start")

    started = time.time()
    results = scan_exact(
        seed, area["cx0"], area["cz0"], area["width"], area["height"],
        weights, top_n, nms,
    )
    total = ring_area(weights)
    return {
        "seed": str(seed),
        "ring": {"inner": inner, "outer": outer, "area": total},
        "area": {k: area[k] for k in ("x0", "z0", "x1", "z1")},
        "results": results or [],
        "stats": {
            "mode": "exact",
            "chunks": chunks,
            "elapsed": round(time.time() - started, 3),
        },
    }


# =================================== #
# @Section: 后台扫描                   #
# =================================== #
def scan_start(payload: dict, ctx) -> dict:
    """创建后台扫描任务并立即返回 scanId，进度由 scan_status 轮询.

    record 是前端看到的全部状态；total 的算法随模式不同：
    - exact：总区块数，进度按已扫区块计；
    - sample：采样次数，进度按已撒点数计。
    """

    settings = ctx.settings("slime")
    seed = _seed(payload, settings)
    area = _area(payload)
    inner, outer, weights = _ring(payload, settings)
    top_n = _top_n(payload, settings)
    nms = _nms(payload, settings)
    samples = _samples(payload, settings)
    chunks = area["width"] * area["height"]
    mode = _mode(payload, settings, chunks)

    scan_id = uuid.uuid4().hex[:8]
    cancel = threading.Event()
    record = {
        "id": scan_id,
        "state": "running",
        "mode": mode,
        "seed": str(seed),
        "ring": {"inner": inner, "outer": outer, "area": ring_area(weights)},
        "area": {k: area[k] for k in ("x0", "z0", "x1", "z1")},
        "done": 0,
        # 进度分母：精确模式按区块，采样模式按采样次数
        "total": chunks if mode == "exact" else samples,
        "best": 0.0,
        "results": [],
        "stats": {},
        "error": "",
        "startedAt": time.time(),
        "finishedAt": None,
    }
    # 登记任务并顺手清理过旧的已完成记录（都在锁内，避免与轮询并发）
    with _LOCK:
        _SCANS[scan_id] = {"record": record, "cancel": cancel}
        _prune_scans()

    # daemon 线程：不阻止进程退出；扫描耗时与请求线程解耦
    thread = threading.Thread(
        target=_worker,
        args=(scan_id, seed, area, weights, mode, top_n, nms, samples),
        name=f"slime-{scan_id}",
        daemon=True,
    )
    thread.start()
    return {
        "scanId": scan_id,
        "mode": mode,
        "ring": record["ring"],
        "total": record["total"],
    }


def scan_status(payload: dict, ctx) -> dict:
    """查询扫描进度；结束（done / aborted / error）后同时带回结果.

    返回前推算出两个派生字段：
    - elapsed：已耗时（秒），未完成时用当前时间减开始时间；
    - progress：0..1 的完成比例，total <= 0 时按 0 处理。
    """

    scan_id = payload.get("scanId")
    if not isinstance(scan_id, str) or not scan_id:
        raise AppError("INVALID_PAYLOAD", "缺少 scanId")
    # 在锁内做一层快照：后台线程可能正在追加 results / 更新 done，
    # 直接返回引用会让序列化读到写了一半的结构。
    with _LOCK:
        entry = _SCANS.get(scan_id)
        if entry is None:
            raise AppError("SCAN_NOT_FOUND", f"没有找到扫描任务：{scan_id}")
        record = entry["record"].copy()
        record["results"] = list(record["results"])
        record["ring"] = dict(record["ring"])
        record["area"] = dict(record["area"])
        record["stats"] = dict(record["stats"])
    record["elapsed"] = round(
        (record["finishedAt"] or time.time()) - record["startedAt"], 2
    )
    record["progress"] = (
        0.0 if record["total"] <= 0 else min(1.0, record["done"] / record["total"])
    )
    return record


def scan_stop(payload: dict, ctx) -> dict:
    """请求中止扫描：置取消事件，后台线程在两块/两批之间退出.

    这里不阻塞等线程结束，只保证「请求已被受理」；真正的状态变化
    （state 变成 aborted）要等下一次 scan_status 才看得到。
    """

    scan_id = payload.get("scanId")
    with _LOCK:
        entry = _SCANS.get(scan_id or "")
        if entry is None:
            raise AppError("SCAN_NOT_FOUND", "没有找到扫描任务")
        entry["cancel"].set()
    return {"scanId": scan_id, "stopping": True}


def _worker(scan_id, seed, area, weights, mode, top_n, nms, samples) -> None:
    """后台扫描线程主体：按模式调用 core.search，并把进度写回 record.

    线程不碰返回值，只改 record 字段，因此所有写操作都在 _LOCK 内完成；
    任何异常都收进 record["error"]（附带类型名），保证前端能拿到终态而不是
    一直转圈。
    """

    with _LOCK:
        entry = _SCANS.get(scan_id)
    if entry is None:
        return
    record = entry["record"]
    cancel = entry["cancel"]

    def progress(done, total, best):
        # 进度回调：由 core 在每块/每批结束时调用，写入共享 record
        with _LOCK:
            record["done"] = int(done)
            record["total"] = int(total)
            record["best"] = float(best)

    try:
        started = time.time()
        if mode == "exact":
            # 精确扫描把 cancel.is_set 作为取消函数传下去，返回 None 表示被中止
            results = scan_exact(
                seed, area["cx0"], area["cz0"], area["width"], area["height"],
                weights, top_n, nms, progress=progress, cancel=cancel.is_set,
            )
            if results is None:
                state = "aborted"
            else:
                state = "done"
            stats = {
                "mode": "exact",
                "chunks": area["width"] * area["height"],
                "tiles": _tiles(area["width"], area["height"]),
            }
        else:
            # 采样模式返回 dict（results / samples / percentile ...），
            # 取消时返回 None
            data = scan_sample(
                seed, area["cx0"], area["cz0"], area["width"], area["height"],
                weights, samples, top_n, nms, progress=progress,
                cancel=cancel.is_set,
            )
            if data is None:
                state = "aborted"
                results = []
            else:
                state = "done"
                results = data["results"]
                stats = {
                    "mode": "sample",
                    "samples": data["samples"],
                    "percentile": data["percentile"],
                }
        elapsed = round(time.time() - started, 2)
        # 终态统一写回：done 顶到 total，让进度条收到 100%（中止也如此）
        with _LOCK:
            record["results"] = list(results or [])
            record["stats"] = dict(stats)
            record["state"] = state
            record["finishedAt"] = time.time()
            record["done"] = record["total"]
            if results:
                # 结果已按得分降序，第一条就是本次找到的最优点
                record["best"] = float(results[0]["score"])
            record["elapsed"] = elapsed
    except Exception as exc:  # noqa: BLE001 - 后台线程兜底
        # 线程里抛异常不会传到请求方，只能落成 error 终态供前端展示
        with _LOCK:
            record["state"] = "error"
            record["error"] = f"{type(exc).__name__}: {exc}"
            record["finishedAt"] = time.time()


def _tiles(width: int, height: int) -> int:
    """精确扫描的分块数量：ceil(width / TILE_CHUNKS) × ceil(height / TILE_CHUNKS)."""

    return ((width + TILE_CHUNKS - 1) // TILE_CHUNKS) * (
        (height + TILE_CHUNKS - 1) // TILE_CHUNKS
    )


def _prune_scans() -> None:
    """只保留最近 _MAX_KEEP_RUNS 个已结束的扫描记录，防止内存无限增长.

    _SCANS 是普通 dict（保持插入顺序），finished 列表按插入顺序收集非
    running 的任务，所以切片前缀就是最旧的那些。调用方已持有 _LOCK。
    """

    finished = [
        key for key, entry in _SCANS.items()
        if entry["record"]["state"] != "running"
    ]
    for key in finished[: max(0, len(finished) - _MAX_KEEP_RUNS)]:
        _SCANS.pop(key, None)


# =================================== #
# @Section: 地图数据                   #
# =================================== #
def map_action(payload: dict, ctx) -> dict:
    """返回一块矩形区域的史莱姆区块位图，供前端画地图.

    坐标与单位：x0 / z0 是左上角区块坐标，width / height 是区块个数，
    两者相乘不能超过 MAX_MAP_CELLS。

    stride（区块步长）：每个像素代表 stride × stride 个区块，用来在范围
    很大时出一张概览图。stride = 1 时逐区块求值；stride > 1 时只在
    (x0 + k·stride, z0 + m·stride) 这个采样网格上求值。

    返回：
    - bits：位图按行优先（行 = Z、列 = X）打包后的 base64，每字节高位在前，
      最后一个字节不足 8 位时低位补 0（stride = 1 时 1 位 = 1 区块）；
    - heat：仅 stride = 1 且请求了 heat 时返回，每区块 1 字节的灰度热力，
      值 = 区块得分 / 环面积 × 255，做热力图用；
    - ring：heat 模式下带回环带信息。
    """

    settings = ctx.settings("slime")
    seed = _seed(payload, settings)
    cx0 = params.integer(payload, "x0", label="区块 X")
    cz0 = params.integer(payload, "z0", label="区块 Z")
    width = params.integer(payload, "width", minimum=1, maximum=2048, label="宽度")
    height = params.integer(payload, "height", minimum=1, maximum=2048, label="高度")
    if width * height > MAX_MAP_CELLS:
        raise AppError("MAP_TOO_LARGE", f"地图最多 {MAX_MAP_CELLS:,} 个区块")

    # stride：每个格子代表多少个区块（1 = 逐区块）。范围过大时用它缩成概览图
    stride = params.integer(
        payload, "stride", default=1, minimum=1, maximum=1_000_000, label="区块步长"
    )
    if stride == 1:
        # 逐区块：直接生成矩形位图，尺寸就是 (height, width)
        mask = slime_mask(seed, cx0, cz0, width, height)
    else:
        # 概览：在步长网格上取采样点，一格代表 stride×stride 个区块。
        # xs 做行向量、zs 做列向量，广播成 (height, width) 的采样位图。
        xs = cx0 + np.arange(width, dtype=np.int64) * stride
        zs = cz0 + np.arange(height, dtype=np.int64) * stride
        mask = slime_flags(seed, xs[None, :], zs[:, None])
    # 每字节 8 位、高位在前；axis=None 表示按行优先整片展开
    bits = np.packbits(mask.astype(np.uint8), axis=None)
    result = {
        "x0": int(cx0),
        "z0": int(cz0),
        "width": int(width),
        "height": int(height),
        "stride": int(stride),
        "bits": base64.b64encode(bits.tobytes()).decode("ascii"),
    }

    if payload.get("heat") and stride == 1:
        # 热力图只对逐区块模式提供：每区块一个分数，步长模式下没有对应关系。
        # 取 ±8 区块的 halo（与圆环外半径 8 区块一致），卷积后得到每区块得分，
        # 再按环面积归一化到 0..255，前端按灰度或色带渲染。
        inner, outer, weights = _ring(payload, settings)
        halo = slime_mask(seed, cx0 - 8, cz0 - 8, width + 16, height + 16)
        scores = correlate(halo, weights[:, :, 8, 8].astype(np.float32))
        total = max(ring_area(weights), 1)
        heat = np.clip(scores / float(total) * 255.0, 0, 255).astype(np.uint8)
        result["heat"] = base64.b64encode(heat.tobytes()).decode("ascii")
        result["ring"] = {"inner": inner, "outer": outer, "area": total}
    return result


def seed_preview(payload: dict, ctx) -> dict:
    """只解析种子并回显，不触发任何计算；用于确认字符串种子被解释成哪个 long.

    返回 seed 是解析后的十进制 long 字符串（世界种子），raw 是原始输入，
    调用方可以据此提示「字符串种子会被转成这个数字」。
    """

    settings = ctx.settings("slime")
    raw = payload.get("seed")
    if raw is None:
        raw = settings.get("seed", "0")
    try:
        value = parse_seed(raw)
    except ValueError as exc:
        raise AppError("INVALID_SEED", str(exc), str(raw)) from None
    return {"seed": str(value), "raw": str(raw)}
