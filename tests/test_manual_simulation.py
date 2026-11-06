# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 手动模拟 / 落点预报契约  #
# =================================== #

import numpy as np
import pytest

BORDER_ORIGIN = {"x": 9996.24, "y": 256.0, "z": 9999.24}
BORDER_TARGET = {"x": 0.0, "y": 128.0, "z": 0.0}


def test_pearl_simulate_reports_landing(api):
    result = api.tool_call(
        "pearl",
        "simulate",
        {"blue": 4, "red": 3393, "direction": "east", "ticks": 60},
    )
    assert result["ok"] is True, result
    data = result["data"]

    assert data["total"] == 3397
    assert data["direction"] == "east"
    assert len(data["points"]) == 61
    assert data["points"][0]["t"] == 0
    # 与 golden 轨迹逐点一致（同一套递推），落地发生在 y <= 0 的第一刻
    assert data["landing"]["tick"] == 53
    assert data["landing"]["y"] <= 0
    assert data["distance"] > 0
    assert data["simulatedTicks"] == 60


def test_pearl_simulate_can_stay_airborne(api):
    result = api.tool_call(
        "pearl",
        "simulate",
        {"blue": 20, "red": 33, "direction": "east", "ticks": 60},
    )
    data = result["data"]
    assert data["landing"] is None
    assert data["points"][-1]["y"] > 0


def test_pearl_simulate_eject_uses_target_height(api):
    result = api.tool_call(
        "pearl",
        "simulate",
        {"blue": 100, "red": 500, "direction": "east", "mode": "eject", "ticks": 400},
    )
    assert result["ok"] is True, result
    data = result["data"]
    # 抛射以 Y=128（EJECT_TARGET_Y）为落地高度
    assert data["groundY"] == 128
    assert data["landing"]["y"] <= 128


def test_pearl_simulate_rejects_bad_direction(api):
    result = api.tool_call(
        "pearl", "simulate", {"blue": 1, "red": 1, "direction": "up"}
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


def test_border_forecast_matches_decoded_row(api):
    calc = api.tool_call(
        "border",
        "calculate",
        {"origin": BORDER_ORIGIN, "target": BORDER_TARGET, "time": 400},
    )
    assert calc["ok"] is True, calc
    row = next(
        item
        for item in calc["data"]["rows"]
        if min(item["t1"], item["t2"], item["t3"]) >= 0
    )
    tnt = [row["t1"], row["t2"], row["t3"]]

    forecast = api.tool_call(
        "border",
        "forecast",
        {"tnt": tnt, "dirCode": row["dirCode"], "origin": BORDER_ORIGIN},
    )
    assert forecast["ok"] is True, forecast
    data = forecast["data"]
    assert data["valid"] is True
    assert data["direction"]
    assert data["motion"]["x"] == pytest.approx(row["mx"], rel=0, abs=1e-9)
    assert data["motion"]["y"] == pytest.approx(row["my"], rel=0, abs=1e-9)
    assert data["motion"]["z"] == pytest.approx(row["mz"], rel=0, abs=1e-9)

    decoded = api.tool_call(
        "border",
        "decode",
        {
            "tnt": tnt,
            "motion": {"x": row["mx"], "y": row["my"], "z": row["mz"]},
            "dirLabel": row["dirLabel"],
            "origin": BORDER_ORIGIN,
        },
    )["data"]
    assert data["landing"] == decoded["landing"]
    assert data["small"] == decoded["small"]
    assert data["big"] == decoded["big"]


def test_border_motion_from_code_covers_all_directions():
    from lspkit.tools.border.core.direction import motion_from_code
    from lspkit.tools.border.core.motion import load_motion

    # 八个方位各取一个代表性目标点（相对炮口）
    samples = [
        (10, 5), (10, 20), (-10, 20), (-10, 5),
        (-10, -5), (-10, -20), (10, -5), (10, -20),
    ]
    seen = set()
    for dx, dz in samples:
        motion, code = load_motion(dx, dz, 0.0, 0.0)
        seen.add(code)
        assert np.allclose(motion_from_code(code), motion), code
    assert len(seen) == 8


def test_border_forecast_reports_position_at_flight_time(api):
    calc = api.tool_call(
        "border",
        "calculate",
        {"origin": BORDER_ORIGIN, "target": BORDER_TARGET, "time": 400},
    )
    row = next(
        item
        for item in calc["data"]["rows"]
        if min(item["t1"], item["t2"], item["t3"]) >= 0
    )
    tnt = [row["t1"], row["t2"], row["t3"]]

    forecast = api.tool_call(
        "border",
        "forecast",
        {
            "tnt": tnt,
            "dirCode": row["dirCode"],
            "time": row["tick"],
            "origin": BORDER_ORIGIN,
        },
    )["data"]
    assert forecast["time"] == row["tick"]
    assert forecast["atTime"]["tick"] == row["tick"]
    assert forecast["landedBefore"] is False
    assert f"第 {row['tick']} gt 位置" in forecast["text"]

    # 不填飞行时间时只给落点
    plain = api.tool_call(
        "border",
        "forecast",
        {"tnt": tnt, "dirCode": row["dirCode"], "origin": BORDER_ORIGIN},
    )["data"]
    assert plain["atTime"] is None
    assert plain["landedBefore"] is False

    # 填一个远大于落地时刻的时间：已落地，不再给位置
    late = api.tool_call(
        "border",
        "forecast",
        {
            "tnt": tnt,
            "dirCode": row["dirCode"],
            "time": 100000,
            "origin": BORDER_ORIGIN,
        },
    )["data"]
    assert late["atTime"] is None
    assert late["landedBefore"] is True


def test_border_forecast_rejects_negative_tnt(api):
    result = api.tool_call(
        "border",
        "forecast",
        {"tnt": [10, -1, 0], "dirCode": "000", "origin": BORDER_ORIGIN},
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "NEGATIVE_TNT"


def test_border_forecast_rejects_bad_direction(api):
    result = api.tool_call(
        "border",
        "forecast",
        {"tnt": [1, 1, 1], "dirCode": "999", "origin": BORDER_ORIGIN},
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"
