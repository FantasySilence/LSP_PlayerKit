# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: TNT 数量拆分             #
# =================================== #

from __future__ import annotations

from lspkit.errors import AppError

BIN_UNITS = (16, 8, 4, 2, 1)


def _one(number: int, unit: int) -> list[int]:
    if number < 0:
        raise AppError("NEGATIVE_TNT", "TNT 数量不能为负数", str(number))
    rest = [number // unit, number % unit // 10, number % unit % 10]
    bases = (unit, 10, 1)
    parts: list[int] = []
    for row, value in enumerate(rest):
        bits = [int(b) for b in bin(int(value))[2:].zfill(5)]
        for col, bit in enumerate(bits):
            if bit:
                parts.append(bases[row] * BIN_UNITS[col])
    return parts


def _text(number: int, parts: list[int]) -> str:
    text = f"{number} = "
    for part in parts:
        text += f"{part} + "
    return text[:-2]


def decompose(blue: int, red: int, unit: int) -> dict:
    blue_parts = _one(int(blue), int(unit))
    red_parts = _one(int(red), int(unit))
    return {
        "blue": blue_parts,
        "red": red_parts,
        "blueText": _text(int(blue), blue_parts),
        "redText": _text(int(red), red_parts),
    }
