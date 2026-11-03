# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 边境炮黄金快照对比       #
# =================================== #

import json
from pathlib import Path

import pytest

from lspkit.tools.border.core.calculate import calculate
from lspkit.tools.border.core.decompose import decompose
from lspkit.tools.border.constants import DIRECTION_ROTATION

FIXTURES = Path(__file__).parent / "fixtures"


def _direction_origin(origin):
    # 旧版方向判断写死 (10000, 10000)
    return (DIRECTION_ROTATION["X"], DIRECTION_ROTATION["Z"])


def test_calculate_matches_legacy():
    cases = json.loads((FIXTURES / "border_calc.json").read_text(encoding="utf-8"))
    for case in cases:
        data = case["input"]
        origin = (data["origin"]["x"], data["origin"]["y"], data["origin"]["z"])
        rows = calculate(
            origin,
            (data["x"], data["y"], data["z"]),
            data["time"],
            _direction_origin(origin),
        )
        assert len(rows) == len(case["rows"])
        for got, exp in zip(rows, case["rows"]):
            assert [got["t1"], got["t2"], got["t3"]] == exp[:3]
            assert got["mx"] == pytest.approx(exp[3], rel=1e-12, abs=1e-9)
            assert got["my"] == pytest.approx(exp[4], rel=1e-12, abs=1e-9)
            assert got["mz"] == pytest.approx(exp[5], rel=1e-12, abs=1e-9)
            assert got["dirLabel"] == exp[6]


def test_decode_matches_legacy_text():
    cases = json.loads((FIXTURES / "border_decode.json").read_text(encoding="utf-8"))
    calc = json.loads((FIXTURES / "border_calc.json").read_text(encoding="utf-8"))

    for case in cases:
        x, y, z, t = case["case"]
        idx = case["index"]
        match = next(c for c in calc if c["input"]["x"] == x and c["input"]["z"] == z and c["input"]["time"] == t)
        row = match["rows"][idx]
        origin = (
            match["input"]["origin"]["x"],
            match["input"]["origin"]["y"],
            match["input"]["origin"]["z"],
        )
        result = decompose(
            [row[0], row[1], row[2]],
            {"x": row[3], "y": row[4], "z": row[5]},
            origin,
            row[6],
        )
        assert result["valid"] is True
        assert result["text"] == case["text"]
