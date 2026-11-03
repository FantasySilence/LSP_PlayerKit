# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 珍珠炮 TNT 当量计算      #
# =================================== #
# 算法逐行对齐旧版 LSP_PearlCannonConfig，保留其取整、枚举顺序与排序行为。

from __future__ import annotations

import numpy as np

from ..constants import (
    DAMPING,
    EJECT_TARGET_Y,
    EJECT_TUNING,
    EJECT_Y_WINDOW,
    FLAT_TUNING,
    MAX_TICKS,
)
from .direction import Directions
from .tuning import generate_combinations


def _round_ints(values) -> list[int]:
    return [int(round(float(v))) for v in values]


def _row(tick: int, error: float, blue: int, red: int) -> dict:
    return {
        "error": float(error),
        "ticks": int(tick),
        "blue": int(blue),
        "red": int(red),
        "total": int(blue) + int(red),
    }


def calculate_flat(
    settings: dict,
    target_x: float,
    target_z: float,
    origin_x: float,
    origin_z: float,
    max_tnt: int,
) -> tuple[str, list[dict]]:
    direction, matrix = Directions.judge(target_x, target_z, origin_x, origin_z)
    xz_motion = settings["flat"]["xzMotion"]

    preliminary: dict[int, list[int]] = {}
    for tick in range(1, MAX_TICKS + 1):
        b = np.array(
            [
                (target_x - origin_x) / (100 * (1 - DAMPING**tick)),
                (target_z - origin_z) / (100 * (1 - DAMPING**tick)),
            ]
        )
        try:
            solution = np.linalg.solve(xz_motion * matrix, b)
        except np.linalg.LinAlgError:
            continue
        x = _round_ints(solution)
        if 0 <= x[0] <= max_tnt and 0 <= x[1] <= max_tnt:
            preliminary[tick] = x

    final: dict[int, list] = {}
    for tick, base in preliminary.items():
        combos = generate_combinations(np.array(base), FLAT_TUNING)
        best = None
        for combo in combos:
            motion = xz_motion * matrix.dot(combo)
            xt = origin_x + 100 * motion[0] * (1 - DAMPING**tick)
            zt = origin_z + 100 * motion[1] * (1 - DAMPING**tick)
            error = float(np.sqrt((xt - target_x) ** 2 + (zt - target_z) ** 2))
            if best is None or error < best[0]:
                best = (error, combo)
        if best is not None:
            final[tick] = [best[0], best[1]]

    rows = [
        _row(tick, value[0], value[1][0], value[1][1])
        for tick, value in final.items()
    ]
    return direction, rows


def calculate_eject(
    settings: dict,
    target_x: float,
    target_z: float,
    origin_x: float,
    origin_z: float,
    max_tnt: int,
) -> tuple[str, list[dict]]:
    direction, matrix = Directions.judge(target_x, target_z, origin_x, origin_z)
    cfg = settings["eject"]
    y0 = cfg["yInitPosition"]

    preliminary: dict[int, list[int]] = {}
    for tick in range(1, MAX_TICKS + 1):
        factor = 100 * (1 - DAMPING**tick)
        px = (target_x - origin_x) / factor
        py = (EJECT_TARGET_Y - y0 + 3 * tick) / factor - 3
        pz = (target_z - origin_z) / factor

        p_xz = matrix.dot(np.array([px, pz]))
        coefs = np.array([[1, 1], p_xz])
        consts = np.array([(py - cfg["yInitMotion"]) / cfg["yMotion"], 0])
        try:
            solution = np.linalg.solve(coefs, consts)
        except np.linalg.LinAlgError:
            continue
        x = _round_ints(solution)
        if 0 <= x[0] <= max_tnt and 0 <= x[1] <= max_tnt:
            preliminary[tick] = x

    final: dict[int, list] = {}
    for tick, base in preliminary.items():
        combos = generate_combinations(np.array(base), EJECT_TUNING)
        best = None
        for combo in combos:
            motion = cfg["xzMotion"] * matrix.dot(combo)
            y_motion = cfg["yMotion"] * sum(combo) + cfg["yInitMotion"]
            xt = origin_x + 100 * motion[0] * (1 - DAMPING**tick)
            yt = y0 + 100 * (y_motion + 3) * (1 - DAMPING**tick) - 3 * tick
            zt = origin_z + 100 * motion[1] * (1 - DAMPING**tick)
            if not (EJECT_Y_WINDOW[0] <= yt <= EJECT_Y_WINDOW[1]):
                continue
            error = float(np.sqrt((xt - target_x) ** 2 + (zt - target_z) ** 2))
            if best is None or error < best[0]:
                best = (error, combo)
        if best is not None:
            final[tick] = [best[0], best[1]]

    rows = [
        _row(tick, value[0], value[1][0], value[1][1])
        for tick, value in final.items()
    ]
    rows.sort(key=lambda row: row["error"])
    return direction, rows


def calculate(
    settings: dict,
    target_x: float,
    target_z: float,
    origin_x: float,
    origin_z: float,
    max_tnt: int,
    mode: str,
) -> tuple[str, list[dict]]:
    if mode == "eject":
        return calculate_eject(settings, target_x, target_z, origin_x, origin_z, max_tnt)
    return calculate_flat(settings, target_x, target_z, origin_x, origin_z, max_tnt)
