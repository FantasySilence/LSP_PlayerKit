# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 边境炮黄金快照对比       #
# =================================== #
# 测试层：border 工具的 core 纯函数（三元求解 / 解码）。
# 策略：golden 快照——逐用例对比旧项目 venv 生成的 JSON；
# tests/fixtures/ 里的数值由旧实现产出，不要手改，core 改动后应重跑旧项目再生成。

import json
from pathlib import Path

import pytest

from lspkit.tools.border.core.calculate import calculate
from lspkit.tools.border.core.decompose import decompose
from lspkit.tools.border.constants import DIRECTION_ROTATION

FIXTURES = Path(__file__).parent / "fixtures"
# 快照来自旧项目 LSP_BorderCannonConfig 的 .venv，坐标/动量/方向名都是旧版输出。


def _direction_origin(origin):
    """返回旧版固定的方向参考点 (10000, 10000).

    旧版把炮口写死在这个点；这里只取 DIRECTION_ROTATION 的 X / Z，
    用来复现旧快照的方向判定。入参 origin 目前未参与计算，仅保留函数签名。
    """
    # 旧版方向判断写死 (10000, 10000)
    return (DIRECTION_ROTATION["X"], DIRECTION_ROTATION["Z"])


def test_calculate_matches_legacy():
    """验证三元求解逐用例复现旧版结果.

    输入：fixtures/border_calc.json 的 origin/target/time；方向参考点用旧版固定 (10000,10000)。
    期望：行数一致，t1/t2/t3 与 dirLabel 完全相同，mx/my/mz 在 1e-12 相对误差内。
    """
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
        # 行数必须与旧快照一致；行数变化说明搜索窗口或奇异解的跳过行为变了。
        for got, exp in zip(rows, case["rows"]):
            # 三元当量与方向名是离散值，必须逐项完全相等。
            assert [got["t1"], got["t2"], got["t3"]] == exp[:3]
            assert got["mx"] == pytest.approx(exp[3], rel=1e-12, abs=1e-9)
            # 动量是浮点复算结果，容差只用来吸收同一公式不同运算顺序的末位差异。
            assert got["my"] == pytest.approx(exp[4], rel=1e-12, abs=1e-9)
            assert got["mz"] == pytest.approx(exp[5], rel=1e-12, abs=1e-9)
            assert got["dirLabel"] == exp[6]


def test_decode_matches_legacy_text():
    """验证解码文本与旧版逐字一致.

    输入：fixtures/border_decode.json 的 (x,y,z,time,index) 指向 border_calc 的某一行。
    期望：valid=True，且 text 与旧快照完全相同（含固定前缀、分隔线和末尾换行）。
    """
    cases = json.loads((FIXTURES / "border_decode.json").read_text(encoding="utf-8"))
    calc = json.loads((FIXTURES / "border_calc.json").read_text(encoding="utf-8"))

    for case in cases:
        x, y, z, t = case["case"]
        idx = case["index"]
        match = next(c for c in calc if c["input"]["x"] == x and c["input"]["z"] == z and c["input"]["time"] == t)
        # 用坐标 + 时间回查对应的求解用例，再按 index 取同一行，避免在快照里重复存动量。
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
        # 文本包含「3个TNT对应的配置信息为：」等固定文案与 50 个「-」，必须逐字一致。
        assert result["valid"] is True
        assert result["text"] == case["text"]
