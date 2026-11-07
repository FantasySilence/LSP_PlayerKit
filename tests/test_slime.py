# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-07                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 史莱姆区块查找器测试     #
# =================================== #

import base64

import numpy as np
import pytest

from lspkit.tools.slime.core.mask import slime_mask
from lspkit.tools.slime.core.ring import build_weights, ring_area
from lspkit.tools.slime.core.score import correlate, refine, suppress
from lspkit.tools.slime.core.search import _batch_scores, scan_exact, scan_sample
from lspkit.tools.slime.core.seed import java_string_hash, parse_seed

MASK48 = (1 << 48) - 1
MASK64 = (1 << 64) - 1


def java_next_int10(seed):
    """Java Random.nextInt(10) 的逐位参考实现（慢，但逻辑独立）."""

    state = (seed ^ 0x5DEECE66D) & MASK48
    while True:
        state = (state * 0x5DEECE66D + 0xB) & MASK48
        bits = state >> 17
        rest = bits % 10
        check = (bits - rest + 9) & 0xFFFFFFFF
        if check < 0x80000000:
            return rest


def _s32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value >= 0x80000000 else value


def reference_slime(seed, cx, cz):
    """Java int 溢出语义的逐位参考实现（慢，但逻辑独立）."""

    part_x2 = _s32(_s32(cx * cx) * 0x4C1906)
    part_x1 = _s32(cx * 0x5AC0DB)
    part_z1 = _s32(cz * 0x5F24F)
    part_z2 = _s32(cz * cz) * 0x4307A7
    value = (seed + part_x2 + part_x1 + part_z1 + part_z2) & MASK64
    return java_next_int10(value ^ 0x3AD8025F) == 0


# Amidst 的 64×64 区块快照（seed 1，坐标 -32..31，按 [x][z] 排列），
# 作为与第三方实现无关的黄金样本。
AMIDST_SEED1 = (
    "AEEhAEAAQIAJCgIAgFBAEAAAFAQgEiAAAAAACBCkAYEhhBAIAQABACgAIAQAQCAAAAgACAAAIADIAEECQMAJAAAQAABQIACAAAAAAAEACAAAAAAhCAAQAYEEcEAAAABAFIAgECEAAAAAQQIgAAAQEQGIAECgQABIARAAAAAAgAAACDAIAAEQAdAAgAAEIAAAAAGAADACAAABAAGAAQAACAAAYAAEACIEAAAgoABAAggBADAAAFIEgAgBAAkkAAABABIggAQAAJJAgDCAACAAhQAAgIAQAIQQAAAEAAAAAAAEQCAAQgEAACCAQAyAAAAaAFAAACpKJAQYQAEAAAMAAACRAAARCAQBAABAQAICAAKAUQABAABCBAVAgAAICIAIACAAgAIAJCoQAEAFJQgAIjAAAAgACAAIAAAYIAIAAAqGBAAAAAAAAAAACAAIRBAAAAAgAQCAAQAAJAYAAAIhaAAAIARAAQACgADBKYAEDBAAAAAABAEAoCRABCAAwEkQAANgAAAQCAICAAACAAAQAgCQCQgBAgUEAAAACACAEBECBAAIAAAAIACAAgCABQACBQAAAAOEAAABAAAogAQQAACIIgABCEQAAQIIAAGkIsIAAFJAACCAIwAgAAAAAAMAEBAAIAQBBEBAIKACAAAAAQBAIAgQgAEAQEAEAAAgAYA="
)


# =================================== #
# @Section: 种子与掩码                 #
# =================================== #
def test_parse_seed_numeric_and_text():
    assert parse_seed("0") == 0
    assert parse_seed("-1") == -1
    assert parse_seed("+12345") == 12345
    assert parse_seed("-9223372036854775808") == -(1 << 63)
    assert parse_seed("hello") == 99162322
    assert java_string_hash("hello") == 99162322
    with pytest.raises(ValueError):
        parse_seed("")
    with pytest.raises(ValueError):
        parse_seed("   ")


def test_mask_matches_reference():
    for seed in (0, 12345, -1, (1 << 40) + 7, -(1 << 63)):
        cx0, cz0, width, height = -13, -17, 23, 19
        mask = slime_mask(seed, cx0, cz0, width, height)
        for z in range(height):
            for x in range(width):
                assert bool(mask[z, x]) == reference_slime(seed, cx0 + x, cz0 + z)


def test_mask_matches_amidst_fixture():
    """Amidst 的 seed=1 快照（-32..31，[x][z] 排列）逐位一致."""

    raw = base64.b64decode(AMIDST_SEED1)
    grid = np.unpackbits(np.frombuffer(raw, dtype=np.uint8)).reshape(64, 64).astype(bool)
    ours = slime_mask(1, -32, -32, 64, 64).T
    assert np.array_equal(ours, grid)
    assert int(grid.sum()) == 430


# =================================== #
# @Section: 圆环与卷积                 #
# =================================== #
def test_ring_weights_cover_same_area():
    weights = build_weights(24, 128)
    area = ring_area(weights)
    coords = np.arange(-143, 144, dtype=np.float64)
    d2 = coords[:, None] ** 2 + coords[None, :] ** 2
    expected = int(((d2 >= 24 * 24) & (d2 < 128 * 128)).sum())
    assert area == expected
    # 挂机点在区块内任意偏移时，环面积都应相同
    assert (weights.sum(axis=(0, 1)) == area).all()


def test_weights_respect_inner_hole():
    weights = build_weights(24, 128)
    # 圆心所在区块整块都在 24 格禁刷区内
    assert int(weights[8, 8].max()) == 0


def test_correlate_matches_bruteforce():
    rng = np.random.default_rng(0)
    mask = rng.random((40, 37)) < 0.1
    kernel = rng.integers(0, 5, (17, 17)).astype(np.float32)
    out = correlate(mask, kernel)
    for z in range(out.shape[0]):
        for x in range(out.shape[1]):
            expected = float((mask[z:z + 17, x:x + 17] * kernel).sum())
            assert out[z, x] == pytest.approx(expected, abs=1e-6)


def test_correlate_fft_large_matches_bruteforce():
    rng = np.random.default_rng(1)
    mask = rng.random((700, 700)) < 0.1
    kernel = rng.integers(0, 3, (17, 17)).astype(np.float32)
    out = correlate(mask, kernel)
    assert out.shape == (684, 684)
    for z, x in [(0, 0), (100, 200), (500, 500), (683, 683)]:
        expected = float((mask[z:z + 17, x:x + 17] * kernel).sum())
        assert out[z, x] == pytest.approx(expected, abs=1e-4)


def test_refine_finds_best_offset_in_chunk():
    seed = 42
    weights = build_weights(24, 128)
    cx, cz = 10, -4
    mask = slime_mask(seed, cx - 8, cz - 8, 17, 17)
    scores = [
        float((mask.T * weights[:, :, sx, sz]).sum())
        for sx in range(16)
        for sz in range(16)
    ]
    score, x, z = refine(seed, cx, cz, weights)
    assert score == pytest.approx(max(scores))
    assert (x // 16, z // 16) == (cx, cz)


def test_suppress_keeps_separated_points():
    items = [(10.0, 0, 0), (9.0, 1, 1), (8.0, 100, 100), (7.0, 102, 102)]
    kept = suppress(items, 8)
    assert [(k[1], k[2]) for k in kept] == [(0, 0), (100, 100)]


# =================================== #
# @Section: 扫描                       #
# =================================== #
def test_exact_scan_matches_bruteforce():
    seed = 7
    cx0, cz0, width, height = -2, 1, 5, 4
    weights = build_weights(24, 128)
    results = scan_exact(seed, cx0, cz0, width, height, weights, top_n=5, nms_chunks=0)
    xs = np.arange(cx0 * 16, (cx0 + width) * 16)
    zs = np.arange(cz0 * 16, (cz0 + height) * 16)
    grid_x, grid_z = np.meshgrid(xs, zs)
    scores = _batch_scores(seed, grid_x.ravel(), grid_z.ravel(), weights)
    assert results[0]["score"] == pytest.approx(float(scores.max()), abs=1e-6)
    assert all(
        results[i]["score"] >= results[i + 1]["score"]
        for i in range(len(results) - 1)
    )


def test_sample_scan_returns_sorted_results():
    seed = 12345
    weights = build_weights(24, 128)
    rng = np.random.default_rng(3)
    data = scan_sample(
        seed, -40, -40, 80, 80, weights,
        samples=4000, top_n=10, nms_chunks=8, rng=rng,
    )
    assert data is not None
    results = data["results"]
    assert results, "采样应至少返回一个结果"
    assert all(
        results[i]["score"] >= results[i + 1]["score"]
        for i in range(len(results) - 1)
    )
    assert 0.0 <= data["percentile"] <= 1.0
    assert data["samples"] == 4000


# =================================== #
# @Section: API                        #
# =================================== #
def test_slime_registered(api):
    tool = api.app_state()["data"]["tools"]
    assert any(item["id"] == "slime" for item in tool)


def test_slime_find_via_api(api):
    result = api.tool_call(
        "slime",
        "find",
        {
            "seed": "0",
            "area": {"x0": -256, "z0": -256, "x1": 256, "z1": 256},
            "topN": 5,
        },
    )
    assert result["ok"] is True, result
    data = result["data"]
    assert data["seed"] == "0"
    assert len(data["results"]) == 5
    assert data["ring"]["inner"] == 24 and data["ring"]["outer"] == 128
    first = data["results"][0]
    assert {"rank", "x", "z", "chunkX", "chunkZ", "score", "coverage"} <= set(first)


def test_slime_scan_roundtrip(api):
    import time

    start = api.tool_call(
        "slime",
        "scan_start",
        {
            "seed": "0",
            "area": {"x0": -512, "z0": -512, "x1": 512, "z1": 512},
            "topN": 3,
        },
    )
    assert start["ok"] is True, start
    scan_id = start["data"]["scanId"]

    status = {}
    for _ in range(300):
        status = api.tool_call("slime", "scan_status", {"scanId": scan_id})["data"]
        if status["state"] != "running":
            break
        time.sleep(0.05)

    assert status["state"] == "done", status
    assert len(status["results"]) == 3
    assert status["progress"] == 1.0


def test_slime_map_bitset(api):
    data = api.tool_call(
        "slime", "map", {"seed": "0", "x0": -8, "z0": -8, "width": 32, "height": 16}
    )["data"]
    bits = base64.b64decode(data["bits"])
    assert len(bits) == (32 * 16 + 7) // 8
    assert data["x0"] == -8 and data["width"] == 32


def test_slime_seed_preview(api):
    data = api.tool_call("slime", "seed_preview", {"seed": "hello"})["data"]
    assert data["seed"] == "99162322"


def test_slime_text_seed_changes_result(api):
    a = api.tool_call(
        "slime", "find",
        {"seed": "0", "area": {"x0": 0, "z0": 0, "x1": 256, "z1": 256}, "topN": 1},
    )["data"]
    b = api.tool_call(
        "slime", "find",
        {"seed": "hello", "area": {"x0": 0, "z0": 0, "x1": 256, "z1": 256}, "topN": 1},
    )["data"]
    assert a["results"][0]["score"] != b["results"][0]["score"] or (
        a["results"][0]["x"], a["results"][0]["z"]
    ) != (b["results"][0]["x"], b["results"][0]["z"])

def test_exact_limit_setting_controls_mode():
    from lspkit.errors import AppError
    from lspkit.tools.slime.actions import _exact_limit, _mode
    from lspkit.tools.slime.constants import (
        DEFAULT_EXACT_CHUNKS,
        MAX_EXACT_CHUNKS,
        MIN_EXACT_CHUNKS,
    )

    settings = {"exactLimit": 100_000}
    assert _exact_limit(settings) == 100_000
    assert _mode({"mode": "auto"}, settings, 99_999) == "exact"
    assert _mode({"mode": "auto"}, settings, 100_001) == "sample"
    assert _mode({"mode": "sample"}, settings, 100_001) == "sample"
    with pytest.raises(AppError):
        _mode({"mode": "exact"}, settings, 100_001)

    assert _exact_limit({"exactLimit": 1}) == MIN_EXACT_CHUNKS
    assert _exact_limit({"exactLimit": 10**12}) == MAX_EXACT_CHUNKS
    assert _exact_limit({}) == DEFAULT_EXACT_CHUNKS
