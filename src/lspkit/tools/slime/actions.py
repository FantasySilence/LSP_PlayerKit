# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-07                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 史莱姆区块查找器动作      #
# =================================== #

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
    MAX_TOP_N,
    MIN_EXACT_CHUNKS,
    TILE_CHUNKS,
    WORLD_MAX,
    WORLD_MIN,
)
from .core.mask import slime_mask
from .core.ring import build_weights, ring_area
from .core.score import correlate
from .core.search import scan_exact, scan_sample
from .core.seed import parse_seed

_WEIGHTS: dict[tuple[float, float], np.ndarray] = {}
_SCANS: dict[str, dict] = {}
_LOCK = threading.Lock()
_MAX_KEEP_RUNS = 10


# =================================== #
# @Section: 参数校验                   #
# =================================== #
def _seed(payload: dict, settings: dict) -> int:
    raw = payload.get("seed")
    if raw is None or str(raw).strip() == "":
        raw = settings.get("seed", "0")
    try:
        return parse_seed(raw)
    except ValueError as exc:
        raise AppError("INVALID_SEED", str(exc), str(raw)) from None


def _weights(inner: float, outer: float) -> np.ndarray:
    key = (float(inner), float(outer))
    cached = _WEIGHTS.get(key)
    if cached is None:
        cached = build_weights(inner, outer)
        _WEIGHTS[key] = cached
    return cached


def _ring(payload: dict, settings: dict) -> tuple[int, int, np.ndarray]:
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
    area = payload.get("area")
    if not isinstance(area, dict):
        raise AppError("INVALID_PAYLOAD", "缺少搜索范围")
    x0 = params.number(area, "x0", label="范围 X1")
    z0 = params.number(area, "z0", label="范围 Z1")
    x1 = params.number(area, "x1", label="范围 X2")
    z1 = params.number(area, "z1", label="范围 Z2")
    x0, x1 = sorted((float(x0), float(x1)))
    z0, z1 = sorted((float(z0), float(z1)))
    if x0 < WORLD_MIN or x1 > WORLD_MAX or z0 < WORLD_MIN or z1 > WORLD_MAX:
        raise AppError(
            "AREA_OUT_OF_WORLD",
            f"搜索范围超出世界边界（{WORLD_MIN} ~ {WORLD_MAX}）",
        )
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
    try:
        value = int(settings.get("exactLimit", DEFAULT_EXACT_CHUNKS))
    except (TypeError, ValueError):
        value = DEFAULT_EXACT_CHUNKS
    return max(MIN_EXACT_CHUNKS, min(MAX_EXACT_CHUNKS, value))


def _mode(payload: dict, settings: dict, chunks: int) -> str:
    mode = payload.get("mode") or settings.get("mode", "auto")
    if mode not in ("auto", "exact", "sample"):
        raise AppError("INVALID_INPUT", "mode 只能是 auto / exact / sample")
    limit = _exact_limit(settings)
    if mode == "auto":
        return "exact" if chunks <= limit else "sample"
    if mode == "exact" and chunks > limit:
        raise AppError(
            "AREA_TOO_LARGE",
            f"精确扫描上限为 {limit:,} 个区块，请改用采样、缩小范围或在设置里调大上限",
        )
    return mode


def _top_n(payload: dict, settings: dict) -> int:
    return params.integer(
        payload, "topN", default=settings.get("topN", DEFAULT_TOP_N),
        minimum=1, maximum=MAX_TOP_N, label="结果数量",
    )


def _nms(payload: dict, settings: dict) -> int:
    return params.integer(
        payload, "nmsChunks", default=settings.get("nmsChunks", DEFAULT_NMS_CHUNKS),
        minimum=0, maximum=32, label="结果间距",
    )


def _samples(payload: dict, settings: dict) -> int:
    return params.integer(
        payload, "samples", default=settings.get("samples", DEFAULT_SAMPLES),
        minimum=1000, maximum=MAX_SAMPLES, label="采样次数",
    )


# =================================== #
# @Section: 同步查找（测试 / 小范围）  #
# =================================== #
def find_action(payload: dict, ctx) -> dict:
    settings = ctx.settings("slime")
    seed = _seed(payload, settings)
    area = _area(payload)
    inner, outer, weights = _ring(payload, settings)
    top_n = _top_n(payload, settings)
    nms = _nms(payload, settings)
    chunks = area["width"] * area["height"]
    if chunks > _exact_limit(settings):
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
        "total": chunks if mode == "exact" else samples,
        "best": 0.0,
        "results": [],
        "stats": {},
        "error": "",
        "startedAt": time.time(),
        "finishedAt": None,
    }
    with _LOCK:
        _SCANS[scan_id] = {"record": record, "cancel": cancel}
        _prune_scans()

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
    scan_id = payload.get("scanId")
    if not isinstance(scan_id, str) or not scan_id:
        raise AppError("INVALID_PAYLOAD", "缺少 scanId")
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
    scan_id = payload.get("scanId")
    with _LOCK:
        entry = _SCANS.get(scan_id or "")
        if entry is None:
            raise AppError("SCAN_NOT_FOUND", "没有找到扫描任务")
        entry["cancel"].set()
    return {"scanId": scan_id, "stopping": True}


def _worker(scan_id, seed, area, weights, mode, top_n, nms, samples) -> None:
    with _LOCK:
        entry = _SCANS.get(scan_id)
    if entry is None:
        return
    record = entry["record"]
    cancel = entry["cancel"]

    def progress(done, total, best):
        with _LOCK:
            record["done"] = int(done)
            record["total"] = int(total)
            record["best"] = float(best)

    try:
        started = time.time()
        if mode == "exact":
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
        with _LOCK:
            record["results"] = list(results or [])
            record["stats"] = dict(stats)
            record["state"] = state
            record["finishedAt"] = time.time()
            record["done"] = record["total"]
            if results:
                record["best"] = float(results[0]["score"])
            record["elapsed"] = elapsed
    except Exception as exc:  # noqa: BLE001 - 后台线程兜底
        with _LOCK:
            record["state"] = "error"
            record["error"] = f"{type(exc).__name__}: {exc}"
            record["finishedAt"] = time.time()


def _tiles(width: int, height: int) -> int:
    return ((width + TILE_CHUNKS - 1) // TILE_CHUNKS) * (
        (height + TILE_CHUNKS - 1) // TILE_CHUNKS
    )


def _prune_scans() -> None:
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
    settings = ctx.settings("slime")
    seed = _seed(payload, settings)
    cx0 = params.integer(payload, "x0", label="区块 X")
    cz0 = params.integer(payload, "z0", label="区块 Z")
    width = params.integer(payload, "width", minimum=1, maximum=2048, label="宽度")
    height = params.integer(payload, "height", minimum=1, maximum=2048, label="高度")
    if width * height > MAX_MAP_CELLS:
        raise AppError("MAP_TOO_LARGE", f"地图最多 {MAX_MAP_CELLS:,} 个区块")

    mask = slime_mask(seed, cx0, cz0, width, height)
    bits = np.packbits(mask.astype(np.uint8), axis=None)
    result = {
        "x0": int(cx0),
        "z0": int(cz0),
        "width": int(width),
        "height": int(height),
        "bits": base64.b64encode(bits.tobytes()).decode("ascii"),
    }

    if payload.get("heat"):
        inner, outer, weights = _ring(payload, settings)
        halo = slime_mask(seed, cx0 - 8, cz0 - 8, width + 16, height + 16)
        scores = correlate(halo, weights[:, :, 8, 8].astype(np.float32))
        total = max(ring_area(weights), 1)
        heat = np.clip(scores / float(total) * 255.0, 0, 255).astype(np.uint8)
        result["heat"] = base64.b64encode(heat.tobytes()).decode("ascii")
        result["ring"] = {"inner": inner, "outer": outer, "area": total}
    return result


def seed_preview(payload: dict, ctx) -> dict:
    settings = ctx.settings("slime")
    raw = payload.get("seed")
    if raw is None:
        raw = settings.get("seed", "0")
    try:
        value = parse_seed(raw)
    except ValueError as exc:
        raise AppError("INVALID_SEED", str(exc), str(raw)) from None
    return {"seed": str(value), "raw": str(raw)}
