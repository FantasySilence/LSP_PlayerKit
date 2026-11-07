# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 珍珠炮黄金快照对比       #
# =================================== #
# 测试层：pearl 工具的 core 纯函数（当量求解 / 轨迹递推 / 拆档）。
# 策略：golden 快照——逐用例对比旧项目 venv 生成的 JSON；
# tests/fixtures/ 的数值是旧实现输出，不要手改，core 改动后用旧项目重新生成再对比。

import json
from pathlib import Path

import numpy as np
import pytest

from lspkit.tools.pearl.core.calculate import calculate_eject, calculate_flat
from lspkit.tools.pearl.core.decompose import decompose
from lspkit.tools.pearl.core.trace import generate
from lspkit.tools.pearl.schema import SCHEMA

FIXTURES = Path(__file__).parent / "fixtures"
ORIGIN = (-31.9375, -8.0625)
# 快照来自旧项目 LSP_PearlCannonConfig 的 venv；炮口按 (x, z) 顺序写在这里。


def _rows(rows):
    """把结果行压成 [error, ticks, blue, red, total]，便于与快照逐列比较."""
    return [[r["error"], r["ticks"], r["blue"], r["red"], r["total"]] for r in rows]


def _compare(expected, actual):
    """逐行比较：ticks/blue/red/total 是离散值，必须完全相等；error 允许浮点容差.

    容差 1e-12（相对）用于吸收同一公式在 float64 下的末位差异；
    error 一旦有实质变化，说明求解或微调逻辑被改动了。
    """
    assert len(actual) == len(expected)
    for exp, got in zip(expected, actual):
        assert got[1:] == exp[1:]
        assert got[0] == pytest.approx(exp[0], rel=1e-12, abs=1e-12)


# 两个快照文件分别锁定 calculate_flat 与 calculate_eject，参数化避免写两份循环。
@pytest.mark.parametrize("name", ["pearl_flat.json", "pearl_eject.json"])
def test_calculate_matches_legacy(name):
    """验证平射/抛射求解逐用例复现旧版.

    输入：fixtures/pearl_flat.json 或 pearl_eject.json 的 target(x,z) 与 maxTnt；
          炮口固定为旧默认 (-31.9375, -8.0625)。
    期望：方向名完全一致；每一行的 ticks/blue/red/total 相同，error 在容差内。
    """
    settings = SCHEMA.defaults()
    cases = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    fn = calculate_flat if name == "pearl_flat.json" else calculate_eject
    # 文件名决定调用哪个求解函数：flat / eject 的微调窗口与排序规则不同。

    for case in cases:
        data = case["input"]
        direction, rows = fn(
            settings, data["x"], data["z"], ORIGIN[0], ORIGIN[1], data["maxTnt"]
        )
        assert direction == case["direction"]
        # 方向是离散判断，必须与旧版完全一致，不能只比误差。
        _compare(case["rows"], _rows(rows))


def test_trace_matches_legacy():
    """验证轨迹递推逐点复现旧版.

    输入：fixtures/pearl_trace.json 的 blue/red/direction/ticks（平射）。
    期望：点数一致；t 完全相同，x/y/z 在 1e-9 绝对/相对误差内。
    """
    settings = SCHEMA.defaults()
    cases = json.loads((FIXTURES / "pearl_trace.json").read_text(encoding="utf-8"))
    for case in cases:
        data = case["input"]
        # 递推用 np.float32 常量模拟旧版精度，1e-9 的容差足以抓住任何精度回退。
        points = generate(
            ORIGIN[0], ORIGIN[1], np.array([data["blue"], data["red"]]),
            data["direction"], data["ticks"], mode="flat", settings=settings,
        )
        expected = case["points"]
        assert len(points) == len(expected)
        for got, exp in zip(points, expected):
            assert got["t"] == exp[0]
            assert got["x"] == pytest.approx(exp[1], rel=1e-9, abs=1e-9)
            assert got["y"] == pytest.approx(exp[2], rel=1e-9, abs=1e-9)
            assert got["z"] == pytest.approx(exp[3], rel=1e-9, abs=1e-9)


def test_decode_matches_legacy():
    """验证 260/10/1 三档拆分的文本与旧版逐字一致.

    输入：fixtures/pearl_decode.json 的 blue/red，unit 取默认 tntPerUnit=260。
    期望：blueText / redText 与快照完全相同（注意旧文本末尾保留一个空格）。
    """
    settings = SCHEMA.defaults()
    cases = json.loads((FIXTURES / "pearl_decode.json").read_text(encoding="utf-8"))
    for case in cases:
        result = decompose(case["blue"], case["red"], settings["tntPerUnit"])
        # 文本末尾的空格是旧版 text[:-2] 留下的，不要在比较前 strip。
        assert result["blueText"] == case["blueText"]
        assert result["redText"] == case["redText"]
