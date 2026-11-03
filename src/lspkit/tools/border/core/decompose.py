# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 边境炮 TNT 配置解码      #
# =================================== #

from __future__ import annotations

import numpy as np

from ..constants import (
    BIG_UNITS,
    BIN_UNITS,
    DIRECTION_CODE_TABLE,
    SMALL_UNITS,
)
from .landing import predict


def _bits_matrix(rest: np.ndarray, base: int) -> np.ndarray:
    matrix = np.zeros((3, 5))
    for i in range(3):
        value = int(rest[i])
        matrix[i] = np.array(list(map(int, bin(value)[2:].zfill(5))))
    return matrix * np.array(BIN_UNITS) * base


def _parts(tnt: np.ndarray, units: tuple[int, ...], values: list[np.ndarray]) -> dict[int, list[str]]:
    matrix = np.zeros((3, 5 * len(units)))
    for i, unit in enumerate(units):
        matrix[:, 5 * i: 5 * (i + 1)] = _bits_matrix(values[i], unit)

    result: dict[int, list[str]] = {}
    for row in range(matrix.shape[0]):
        total = int(sum(matrix[row]))
        text = f"{total} = "
        for col in range(matrix.shape[1]):
            if matrix[row, col] != 0:
                text += f"{int(matrix[row, col])} + "
        result[row] = text[:-2]
    return result


def decompose(
    tnt: list[int],
    motion: dict,
    origin: tuple[float, float, float],
    dir_label: str,
) -> dict:
    numbers = np.array([int(v) for v in tnt])
    if numbers.min() < 0:
        return {
            "valid": False,
            "reason": "该组配置包含负数 TNT，无法生成阵列（旧版同样无法解码）",
        }

    small_values = [
        (numbers % 780) // 260,
        (numbers % 780) % 260 // 10,
        (numbers % 780) % 260 % 10,
    ]
    charges = numbers // 780
    big_values = [
        charges // 1000,
        charges % 1000 // 100,
        charges % 1000 % 100 // 10,
        charges % 1000 % 100 % 10,
    ]

    small = _parts(numbers, SMALL_UNITS, small_values)
    big = _parts(numbers, BIG_UNITS, big_values)
    landing = predict(motion["x"], motion["y"], motion["z"], origin)

    lines = ["3个TNT对应的配置信息为："]
    for index in range(3):
        lines.append("-" * 50)
        lines.append(f"第{index + 1}个TNT的配置信息：")
        lines.append(f"小头(满当量蓄力后剩余的TNT)：{small[index]}")
        lines.append(f"大头(以780满当量蓄力的次数)：{big[index]}")
    lines.append("-" * 50)
    lines.append(f"边境炮方向：{DIRECTION_CODE_TABLE.get(dir_label, dir_label)}")
    lines.append("-" * 50)
    lines.append(f"x动量：{motion['x']:.6f}")
    lines.append(f"y动量：{motion['y']:.6f}")
    lines.append(f"z动量：{motion['z']:.6f}")
    lines.append("-" * 50)
    lines.append(f"珍珠预计落点x坐标：{landing['x']:f}")
    lines.append(f"珍珠预计落点z坐标：{landing['z']:f}")

    return {
        "valid": True,
        "small": small,
        "big": big,
        "landing": landing,
        "dirCode": DIRECTION_CODE_TABLE.get(dir_label, dir_label),
        "text": "\n".join(lines) + "\n",
    }
