# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 手动模拟 / 落点预报契约  #
# =================================== #
# 测试层：pearl.simulate 与 border.forecast 的动作契约。
# 策略：通过 Api 走真实参数校验 + core 递推，重点验证落地判定、方向覆盖、
# 预报与解码使用同一行动量；少量固定数值来自递推结果（不是随机）。

import numpy as np
import pytest

BORDER_ORIGIN = {"x": 9996.24, "y": 256.0, "z": 9999.24}
BORDER_TARGET = {"x": 0.0, "y": 128.0, "z": 0.0}
# 边境炮旧版默认炮口与靶点：Y=256 是同层炮口，目标 Y=128 是常见靶层。
# 这两组常量也被 test_bridge 的边境炮用例复用。


def test_pearl_simulate_reports_landing(api):
    """验证手动模拟会给出完整点列与落地信息.

    输入：blue=4、red=3393、direction=east、ticks=60（平射）。
    期望：total=3397，61 个点（含 t=0），落地发生在第 53 gt，且落点 Y<=0。
    """
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
    # 点数为 ticks + 1：t=0 是出膛点，之后每个 gt 一个点。
    assert data["points"][0]["t"] == 0
    # 与 golden 轨迹逐点一致（同一套递推），落地发生在 y <= 0 的第一刻
    # 53 是该组当量首次 y<=0 的 gt；数值变化说明递推或常量被改动。
    assert data["landing"]["tick"] == 53
    assert data["landing"]["y"] <= 0
    assert data["distance"] > 0
    assert data["simulatedTicks"] == 60


def test_pearl_simulate_can_stay_airborne(api):
    """验证未落地时 landing 为 None.

    输入：blue=20、red=33、east、ticks=60。
    期望：60gt 内始终在空中（landing=None，最后一点 y>0）。
    """
    result = api.tool_call(
        "pearl",
        "simulate",
        {"blue": 20, "red": 33, "direction": "east", "ticks": 60},
    )
    data = result["data"]
    assert data["landing"] is None
    assert data["points"][-1]["y"] > 0


def test_pearl_simulate_eject_uses_target_height(api):
    """验证抛射模式默认以 Y=128 为落地高度.

    输入：blue=100、red=500、east、mode=eject、ticks=400。
    期望：groundY=128，landing 的 y<=128（而不是平射的 0）。
    """
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
    """验证非法方向被参数层拒绝.

    输入：direction="up"（只允许 east/west/north/south）。
    期望：ok=False，INVALID_INPUT。
    """
    result = api.tool_call(
        "pearl", "simulate", {"blue": 1, "red": 1, "direction": "up"}
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


def test_border_forecast_matches_decoded_row(api):
    """验证手动预报与 calculate 结果行使用同一套动量/拆档.

    输入：边境炮默认炮口/目标、time=400，取第一行 t1/t2/t3 均非负的候选。
    期望：forecast 的 motion 与行内 mx/my/mz 一致，landing/small/big 与 decode 相同。
    """
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
    # 早期 tick 可能解出负当量；这里取第一个三颗都非负、可实际摆放的行。
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
    # 预报直接用该行的 dirCode 取矩阵，再乘三元当量，结果应与行内动量一致。
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
    """验证八个方向码都能还原出与 load_motion 相同的动量矩阵.

    输入：相对炮口的八个象限代表点（±10, ±5/20）。
    期望：每个点得到的 code 唯一，且 motion_from_code(code) 与 load_motion 的矩阵相等。
    """
    from lspkit.tools.border.core.direction import motion_from_code
    from lspkit.tools.border.core.motion import load_motion

    # 八个方位各取一个代表性目标点（相对炮口）
    samples = [
        (10, 5), (10, 20), (-10, 20), (-10, 5),
        (-10, -5), (-10, -20), (10, -5), (10, -20),
    ]
    # 每个象限取两个点，确保八种方向码各出现一次。
    seen = set()
    for dx, dz in samples:
        motion, code = load_motion(dx, dz, 0.0, 0.0)
        seen.add(code)
        assert np.allclose(motion_from_code(code), motion), code
    # 方向判定与按码取矩阵是两条路径，这里要求它们逐元素一致。
    assert len(seen) == 8


def test_border_forecast_reports_position_at_flight_time(api):
    """验证 forecast 的 atTime / landedBefore 语义.

    输入：同一行三颗 TNT，分别不填 time、填 row["tick"]、填 100000。
    期望：不填只给落点；填飞行时刻给出该 gt 位置；填超大值则已落地、不再给位置。
    """
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
    # time 取该行自己的 tick，因此位置一定存在（轨迹至少到落地那一 gt）。
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
    # 不填 time 时只做落点预报，atTime 固定为 None。
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
    # 100000gt 远大于落地时刻，position_at 越界 -> atTime=None 且 landedBefore=True。
    assert late["atTime"] is None
    assert late["landedBefore"] is True


def test_border_forecast_rejects_negative_tnt(api):
    """验证手动预报拒绝负 TNT.

    输入：tnt=[10, -1, 0]。
    期望：ok=False，NEGATIVE_TNT。
    """
    result = api.tool_call(
        "border",
        "forecast",
        {"tnt": [10, -1, 0], "dirCode": "000", "origin": BORDER_ORIGIN},
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "NEGATIVE_TNT"


def test_border_forecast_rejects_bad_direction(api):
    """验证未知方向码被参数层拒绝.

    输入：dirCode="999"（只允许 DIRECTION_POINTS 的八个码）。
    期望：ok=False，INVALID_INPUT。
    """
    result = api.tool_call(
        "border",
        "forecast",
        {"tnt": [1, 1, 1], "dirCode": "999", "origin": BORDER_ORIGIN},
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"
