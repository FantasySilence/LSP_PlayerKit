# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 珍珠炮黄金快照对比       #
# =================================== #

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


def _rows(rows):
    return [[r["error"], r["ticks"], r["blue"], r["red"], r["total"]] for r in rows]


def _compare(expected, actual):
    assert len(actual) == len(expected)
    for exp, got in zip(expected, actual):
        assert got[1:] == exp[1:]
        assert got[0] == pytest.approx(exp[0], rel=1e-12, abs=1e-12)


@pytest.mark.parametrize("name", ["pearl_flat.json", "pearl_eject.json"])
def test_calculate_matches_legacy(name):
    settings = SCHEMA.defaults()
    cases = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    fn = calculate_flat if name == "pearl_flat.json" else calculate_eject

    for case in cases:
        data = case["input"]
        direction, rows = fn(
            settings, data["x"], data["z"], ORIGIN[0], ORIGIN[1], data["maxTnt"]
        )
        assert direction == case["direction"]
        _compare(case["rows"], _rows(rows))


def test_trace_matches_legacy():
    settings = SCHEMA.defaults()
    cases = json.loads((FIXTURES / "pearl_trace.json").read_text(encoding="utf-8"))
    for case in cases:
        data = case["input"]
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
    settings = SCHEMA.defaults()
    cases = json.loads((FIXTURES / "pearl_decode.json").read_text(encoding="utf-8"))
    for case in cases:
        result = decompose(case["blue"], case["red"], settings["tntPerUnit"])
        assert result["blueText"] == case["blueText"]
        assert result["redText"] == case["redText"]
