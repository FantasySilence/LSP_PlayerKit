# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-07                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 史莱姆区块查找器测试     #
# =================================== #
# 测试层：slime 工具的 core（种子/掩码/圆环/卷积/扫描）与 Api 动作。
# 策略：三层对照——Java 语义的逐位参考实现、Amidst 快照黄金校验、暴力枚举对照；
# API 层用临时数据目录验证注册、同步查找、后台扫描与地图位图。

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
# Java Random 的内部状态是 48 位；long 运算按 64 位回绕，两个掩码分别对应这两处。


def java_next_int10(seed):
    """Java Random.nextInt(10) 的逐位参考实现（慢，但逻辑独立）.

    用 LCG 推进 48 位状态，取高 31 位；若落在拒绝区间就重抽，
    直到 bits % 10 均匀。返回 0..9。
    """

    state = (seed ^ 0x5DEECE66D) & MASK48
    while True:
        state = (state * 0x5DEECE66D + 0xB) & MASK48
        bits = state >> 17
        rest = bits % 10
        check = (bits - rest + 9) & 0xFFFFFFFF
        if check < 0x80000000:
            return rest


def _s32(value: int) -> int:
    """把 Python 整数折成 Java int（32 位有符号）的溢出语义."""
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value >= 0x80000000 else value


def reference_slime(seed, cx, cz):
    """slime 区块公式的独立参考实现（逐位模拟 Java int/long 溢出）.

    与 core/mask.py 的实现不共享代码；用它逐格校验 slime_mask，
    可避免「两边错得一样」的假通过。
    """

    part_x2 = _s32(_s32(cx * cx) * 0x4C1906)
    part_x1 = _s32(cx * 0x5AC0DB)
    part_z1 = _s32(cz * 0x5F24F)
    part_z2 = _s32(cz * cz) * 0x4307A7
    value = (seed + part_x2 + part_x1 + part_z1 + part_z2) & MASK64
    return java_next_int10(value ^ 0x3AD8025F) == 0


# Amidst 的 64×64 区块快照（seed 1，坐标 -32..31，按 [x][z] 排列），
# 作为与第三方实现无关的黄金样本。
# base64 解出的是 64×64 位图（512 字节），坐标 -32..31；430 是快照里史莱姆区块的数量。
# 这是第三方实现（Amidst）给出的黄金样本，只用于校验，不要手改。
AMIDST_SEED1 = (
    "AEEhAEAAQIAJCgIAgFBAEAAAFAQgEiAAAAAACBCkAYEhhBAIAQABACgAIAQAQCAAAAgACAAAIADIAEECQMAJAAAQAABQIACAAAAAAAEACAAAAAAhCAAQAYEEcEAAAABAFIAgECEAAAAAQQIgAAAQEQGIAECgQABIARAAAAAAgAAACDAIAAEQAdAAgAAEIAAAAAGAADACAAABAAGAAQAACAAAYAAEACIEAAAgoABAAggBADAAAFIEgAgBAAkkAAABABIggAQAAJJAgDCAACAAhQAAgIAQAIQQAAAEAAAAAAAEQCAAQgEAACCAQAyAAAAaAFAAACpKJAQYQAEAAAMAAACRAAARCAQBAABAQAICAAKAUQABAABCBAVAgAAICIAIACAAgAIAJCoQAEAFJQgAIjAAAAgACAAIAAAYIAIAAAqGBAAAAAAAAAAACAAIRBAAAAAgAQCAAQAAJAYAAAIhaAAAIARAAQACgADBKYAEDBAAAAAABAEAoCRABCAAwEkQAANgAAAQCAICAAACAAAQAgCQCQgBAgUEAAAACACAEBECBAAIAAAAIACAAgCABQACBQAAAAOEAAABAAAogAQQAACIIgABCEQAAQIIAAGkIsIAAFJAACCAIwAgAAAAAAMAEBAAIAQBBEBAIKACAAAAAQBAIAgQgAEAQEAEAAAgAYA="
)


# =================================== #
# @Section: 种子与掩码                 #
# =================================== #
def test_parse_seed_numeric_and_text():
    """验证种子解析：十进制 long 与 Java String.hashCode.

    输入："0"/"-1"/"+12345"/Long.MIN_VALUE 与文本 "hello"；空串与空白。
    期望：数字原样；"hello" -> 99162322；空输入抛 ValueError。
    """
    assert parse_seed("0") == 0
    assert parse_seed("-1") == -1
    assert parse_seed("+12345") == 12345
    assert parse_seed("-9223372036854775808") == -(1 << 63)
    assert parse_seed("hello") == 99162322
    # 99162322 是 Java "hello".hashCode() 的结果，不是随手取的常数。
    assert java_string_hash("hello") == 99162322
    with pytest.raises(ValueError):
        parse_seed("")
    with pytest.raises(ValueError):
        parse_seed("   ")


def test_mask_matches_reference():
    """验证 slime_mask 与逐位参考实现完全一致.

    输入：种子 0/12345/-1/2^40+7/Long.MIN_VALUE，区块范围 -13..9 × -17..1。
    期望：mask[z,x] 与 reference_slime(seed, cx0+x, cz0+z) 逐格相等。
    """
    for seed in (0, 12345, -1, (1 << 40) + 7, -(1 << 63)):
        cx0, cz0, width, height = -13, -17, 23, 19
        mask = slime_mask(seed, cx0, cz0, width, height)
        for z in range(height):
            for x in range(width):
                assert bool(mask[z, x]) == reference_slime(seed, cx0 + x, cz0 + z)


def test_mask_matches_amidst_fixture():
    """验证 seed=1 的 64×64 位图与 Amidst 快照逐位一致.

    输入：AMIDST_SEED1 解出的 64×64 位图（坐标 -32..31，[x][z] 排列）。
    期望：slime_mask(1,-32,-32,64,64) 转置后与快照完全相同，且史莱姆区块数为 430。
    """
    # 先按 [x][z] 解包成 64×64；slime_mask 返回 [z][x]，转置后再比。

    raw = base64.b64decode(AMIDST_SEED1)
    grid = np.unpackbits(np.frombuffer(raw, dtype=np.uint8)).reshape(64, 64).astype(bool)
    ours = slime_mask(1, -32, -32, 64, 64).T
    assert np.array_equal(ours, grid)
    # 430 是 Amidst 快照中史莱姆区块的数量，写死用来发现「整体位图翻转」这类错误。
    assert int(grid.sum()) == 430


# =================================== #
# @Section: 圆环与卷积                 #
# =================================== #
def test_ring_weights_cover_same_area():
    """验证圆环权重表的面积与逐格枚举一致，且与块内偏移无关.

    输入：默认内径 24、外径 128；枚举 -143..143 的方块平面。
    期望：ring_area 等于满足 24²<=d²<128² 的整数格点数；
          256 个块内偏移的权重和都相同。
    """
    weights = build_weights(24, 128)
    area = ring_area(weights)
    coords = np.arange(-143, 144, dtype=np.float64)
    # 默认 24..128 的环面积是 49,640 格²；这里不写死号码，而是按同一判定逐格数出来。
    d2 = coords[:, None] ** 2 + coords[None, :] ** 2
    expected = int(((d2 >= 24 * 24) & (d2 < 128 * 128)).sum())
    assert area == expected
    # 挂机点在区块内任意偏移时，环面积都应相同
    # 外径 128 格正好被 ±8 区块覆盖，平移块内偏移只会移动取景窗口，不会切掉环带。
    assert (weights.sum(axis=(0, 1)) == area).all()


def test_weights_respect_inner_hole():
    """验证圆心所在区块完全落在内圈禁刷区，权重为 0.

    输入：build_weights(24,128) 的 [8,8]（相对区块 0,0、块内偏移中心）。
    期望：该区块 16×16 个权重全为 0（最远格点距圆心约 11.3 < 24）。
    """
    weights = build_weights(24, 128)
    # 圆心所在区块整块都在 24 格禁刷区内
    assert int(weights[8, 8].max()) == 0


def test_correlate_matches_bruteforce():
    """验证小图走直接相关时与暴力累加一致.

    输入：40×37 随机布尔掩码、17×17 随机整数核。
    期望：每个输出格都等于对应 17×17 窗口与核的加权和（1e-6 容差）。
    """
    rng = np.random.default_rng(0)
    mask = rng.random((40, 37)) < 0.1
    kernel = rng.integers(0, 5, (17, 17)).astype(np.float32)
    # 输出 24×21=504 格 < FFT_MIN_CELLS(20 万)，因此走 _correlate_direct。
    out = correlate(mask, kernel)
    for z in range(out.shape[0]):
        for x in range(out.shape[1]):
            expected = float((mask[z:z + 17, x:x + 17] * kernel).sum())
            assert out[z, x] == pytest.approx(expected, abs=1e-6)


def test_correlate_fft_large_matches_bruteforce():
    """验证大图走 FFT 时仍与暴力累加一致.

    输入：700×700 随机掩码、17×17 随机核。
    期望：输出 684×684；抽查四角与中部共 4 格，误差 <1e-4。
    """
    rng = np.random.default_rng(1)
    mask = rng.random((700, 700)) < 0.1
    kernel = rng.integers(0, 3, (17, 17)).astype(np.float32)
    # 684² ≈ 468k >= 20 万，触发 _correlate_fft；1e-4 容差吸收 FFT 的浮点误差。
    out = correlate(mask, kernel)
    assert out.shape == (684, 684)
    for z, x in [(0, 0), (100, 200), (500, 500), (683, 683)]:
        expected = float((mask[z:z + 17, x:x + 17] * kernel).sum())
        assert out[z, x] == pytest.approx(expected, abs=1e-4)


def test_refine_finds_best_offset_in_chunk():
    """验证块内精修枚举 16×16 个挂机点并返回最高分.

    输入：seed=42、区块 (10,-4)、默认圆环权重。
    期望：返回分数等于暴力枚举 256 个块内偏移的最大值；方块坐标落在该区块内。
    """
    seed = 42
    weights = build_weights(24, 128)
    cx, cz = 10, -4
    mask = slime_mask(seed, cx - 8, cz - 8, 17, 17)
    # scores 按 (sx, sz) 行优先展开；refine 内部用同一顺序，所以可以直接比最大值。
    scores = [
        float((mask.T * weights[:, :, sx, sz]).sum())
        for sx in range(16)
        for sz in range(16)
    ]
    score, x, z = refine(seed, cx, cz, weights)
    assert score == pytest.approx(max(scores))
    assert (x // 16, z // 16) == (cx, cz)


def test_suppress_keeps_separated_points():
    """验证非极大值抑制按切比雪夫距离保留分散点.

    输入：四个候选 (10,0,0)/(9,1,1)/(8,100,100)/(7,102,102)，半径 8。
    期望：保留 (0,0) 与 (100,100) 两个簇的代表，后两个因距离 <=8 被压掉。
    """
    items = [(10.0, 0, 0), (9.0, 1, 1), (8.0, 100, 100), (7.0, 102, 102)]
    kept = suppress(items, 8)
    assert [(k[1], k[2]) for k in kept] == [(0, 0), (100, 100)]


# =================================== #
# @Section: 扫描                       #
# =================================== #
def test_exact_scan_matches_bruteforce():
    """验证精确扫描的 Top-1 分数等于全区域暴力最大得分.

    输入：seed=7、区块范围 (-2,1) 起 5×4、top_n=5、nms=0（不做抑制）。
    期望：results[0].score 等于所有方块坐标 _batch_scores 的最大值；结果按分数降序。
    """
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
    """验证采样扫描返回降序结果与统计字段.

    输入：seed=12345、80×80 区块、samples=4000、top_n=10、nms=8、固定 rng。
    期望：结果非空且按分数降序；percentile 在 0..1；samples 回显 4000。
    """
    seed = 12345
    weights = build_weights(24, 128)
    rng = np.random.default_rng(3)
    # 采样是近似算法，只保证「预算内找到的最好点」，不保证全局最优。
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
    """验证 slime 已注册进工具清单.

    输入：app_state() 的 tools。
    期望：存在 id="slime" 的条目。
    """
    tool = api.app_state()["data"]["tools"]
    assert any(item["id"] == "slime" for item in tool)


def test_slime_find_via_api(api):
    """验证同步 find 的返回结构.

    输入：seed="0"、范围 -256..256、topN=5。
    期望：5 条结果；环带 24/128；每条含 rank/x/z/chunkX/chunkZ/score/coverage。
    """
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
    """验证后台精确扫描的启动、轮询与结果.

    输入：seed="0"、范围 -512..512（64×64 区块）、topN=3。
    期望：状态最终 done，结果 3 条，progress=1.0。
    """
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
        # 300 × 50ms = 15s 轮询预算；64×64 区块的精确扫描远小于这个时间。
        status = api.tool_call("slime", "scan_status", {"scanId": scan_id})["data"]
        if status["state"] != "running":
            break
        time.sleep(0.05)

    assert status["state"] == "done", status
    assert len(status["results"]) == 3
    assert status["progress"] == 1.0


def test_slime_map_bitset(api):
    """验证地图位图的字节长度与范围回显.

    输入：32×16 区块的地图请求。
    期望：bits 长度 = ceil(32*16/8)=64 字节；x0/width 原样返回。
    """
    data = api.tool_call(
        "slime", "map", {"seed": "0", "x0": -8, "z0": -8, "width": 32, "height": 16}
    )["data"]
    bits = base64.b64decode(data["bits"])
    assert len(bits) == (32 * 16 + 7) // 8
    assert data["x0"] == -8 and data["width"] == 32


def test_slime_map_stride(api):
    """验证 stride > 1 时的采样网格与位图尺寸.

    输入：seed="0"、64×64 格的地图请求、stride=8。
    期望：返回 stride=8，width/height 仍是 64；解包后的位图与按 8 区块步长
          采样的 slime_flags 逐点一致。
    """
    # stride=8 表示每个像素代表 8×8 区块；返回的 width/height 是格子数，不是区块数。

    from lspkit.tools.slime.core.mask import slime_flags

    data = api.tool_call(
        "slime",
        "map",
        {"seed": "0", "x0": -512, "z0": -512, "width": 64, "height": 64, "stride": 8},
    )["data"]
    assert data["stride"] == 8
    assert data["width"] == 64 and data["height"] == 64
    mask = np.unpackbits(np.frombuffer(base64.b64decode(data["bits"]), dtype=np.uint8))
    mask = mask[: 64 * 64].reshape(64, 64).astype(bool)
    xs = np.arange(-512, -512 + 64 * 8, 8, dtype=np.int64)
    # 采样网格：每格取 (x0 + k*stride, z0 + m*stride)，与 actions.map 的实现一致。
    expected = slime_flags(0, xs[None, :], xs[:, None])
    assert np.array_equal(mask, expected)


def test_slime_seed_preview(api):
    """验证文本种子预览返回 Java hashCode.

    输入：seed="hello"。
    期望：seed="99162322"（与 parse_seed 的结果一致）。
    """
    data = api.tool_call("slime", "seed_preview", {"seed": "hello"})["data"]
    assert data["seed"] == "99162322"


def test_slime_text_seed_changes_result(api):
    """验证文本种子确实参与计算，而不是被忽略.

    输入：seed="0" 与 "hello"，同一范围各取 top1。
    期望：两次的最高分或坐标至少有一项不同（不锁定具体值）。
    """
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
    """验证 exactLimit 的夹取与 auto/exact/sample 模式选择.

    输入：exactLimit=100000、1、10^12、缺省/0；区块数 99999/100001/10^12。
    期望：上限夹到 [65536, 67108864]；auto 未设上限始终 exact，设了上限则超限转 sample；
          显式 exact 超限抛 AppError；0/缺省表示不限制。
    """
    from lspkit.errors import AppError
    from lspkit.tools.slime.actions import _exact_limit, _mode
    from lspkit.tools.slime.constants import (
        DEFAULT_EXACT_CHUNKS,
        MAX_EXACT_CHUNKS,
        MIN_EXACT_CHUNKS,
    )

    settings = {"exactLimit": 100_000}
    # 65536 = 256×256，67108864 = 8192×8192，是用户可填上下限。
    assert _exact_limit(settings) == 100_000
    assert _mode({"mode": "auto"}, settings, 99_999) == "exact"
    assert _mode({"mode": "auto"}, settings, 100_001) == "sample"
    assert _mode({"mode": "sample"}, settings, 100_001) == "sample"
    with pytest.raises(AppError):
        _mode({"mode": "exact"}, settings, 100_001)

    assert _exact_limit({"exactLimit": 1}) == MIN_EXACT_CHUNKS
    assert _exact_limit({"exactLimit": 10**12}) == MAX_EXACT_CHUNKS
    assert _exact_limit({}) == DEFAULT_EXACT_CHUNKS == 0
    assert _exact_limit({"exactLimit": 0}) == 0

    # 默认不限制：超大范围也走精确扫描；显式 exact 同样允许
    assert _mode({"mode": "auto"}, {}, 10**12) == "exact"
    assert _mode({"mode": "exact"}, {}, 10**12) == "exact"
