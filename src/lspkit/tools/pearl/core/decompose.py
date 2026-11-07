# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: TNT 数量拆分             #
# =================================== #

# TNT 数量拆分：把蓝 / 红当量按「整组 unit(260) / 十位 / 个位」三档拆开，每档再用
# 5 位二进制（权重 16/8/4/2/1）展开，得到实际要摆放的各档数量与旧版文本。
from __future__ import annotations

from lspkit.errors import AppError

# 每一档按 5 位二进制展开，位权从高到低为 16 / 8 / 4 / 2 / 1（旧版阵列的 5 个格子）。
BIN_UNITS = (16, 8, 4, 2, 1)


# ------ 拆分算法 ------ #
def _one(number: int, unit: int) -> list[int]:
    """把单一颜色（蓝或红）的 TNT 总数拆成各档实际数量。

    参数:
        number: 该颜色的 TNT 总数，单位个，必须非负。
        unit: 一组当量的 TNT 数（settings.tntPerUnit，默认 260），单位个。

    返回:
        list[int]：按 (16, 8, 4, 2, 1) 展开、并乘上 (unit / 10 / 1) 进制后的各档数量；
        该档数字 ≤ 31 时元素之和等于 number，可直接逐项摆放。

    异常:
        AppError("NEGATIVE_TNT")：number < 0 时抛出，第三项带原值便于定位。

    说明:
        rest 的三项依次是「整组数 / 十位 / 个位」，对应旧界面竖排的三行二进制格子；
        每行再展开成 5 位（高位在前），与 BIN_UNITS 的顺序一一对应。
        每档只有 5 个位权，所以该档数字必须 ≤ 31（只有「整组数」会超：unit=260 时
        总数 ≥ 8320 即触发）。超出后高位被 5 位窗口截断：求和偏小（8320 只得 4160），
        若被截掉的那位恰为 1 还会因 bits 变长而 IndexError（9100 即抛）。
        默认 maxTnt=3640 碰不到这里；旧版是否有防护未考证，按原样保留、未加校验。
    """

    if number < 0:
        raise AppError("NEGATIVE_TNT", "TNT 数量不能为负数", str(number))
    # 高位 = 整组 unit 个的个数；后两位 = 十位、个位（旧界面的三行）。
    rest = [number // unit, number % unit // 10, number % unit % 10]
    # 三行各自的进制：整组按 unit、十位按 10、个位按 1。
    bases = (unit, 10, 1)
    parts: list[int] = []
    for row, value in enumerate(rest):
        # 每个数字展开成 5 位二进制（不足补 0，高位在前），再按位权折算成数量。
        bits = [int(b) for b in bin(int(value))[2:].zfill(5)]
        for col, bit in enumerate(bits):
            if bit:
                parts.append(bases[row] * BIN_UNITS[col])
    return parts


# ------ 文本拼装与对外入口 ------ #
def _text(number: int, parts: list[int]) -> str:
    """把拆分结果拼成旧版文本，例如 "913 = 520 + 260 + 80 + 40 + 10 + 2 + 1"。

    参数:
        number: 原始 TNT 总数，单位个。
        parts: _one 返回的各档数量，单位个。

    返回:
        文本串。末尾的 " + " 会被 text[:-2] 切掉，所以结果末尾仍保留一个空格；
        旧版快照依赖这一格，前端展示时不要 strip，否则文本对不上。
    """

    text = f"{number} = "
    for part in parts:
        text += f"{part} + "
    return text[:-2]


def decompose(blue: int, red: int, unit: int) -> dict:
    """拆分蓝 / 红两组当量，并生成对应的旧版文本。

    参数:
        blue: 蓝色 TNT 数量，单位个。
        red: 红色 TNT 数量，单位个。
        unit: 每组当量（settings.tntPerUnit，默认 260），单位个。

    返回:
        {"blue": [...], "red": [...], "blueText": "...", "redText": "..."}；
        blue/red 是各档数量（个），*Text 是旧版格式文本（见 _text）。

    异常:
        AppError("NEGATIVE_TNT")：任一颜色为负时，由 _one 抛出。
    """

    # 两种颜色用同一套拆法，只是总量不同；unit 决定「整组」这一档的进制。
    blue_parts = _one(int(blue), int(unit))
    red_parts = _one(int(red), int(unit))
    return {
        "blue": blue_parts,
        "red": red_parts,
        "blueText": _text(int(blue), blue_parts),
        "redText": _text(int(red), red_parts),
    }
