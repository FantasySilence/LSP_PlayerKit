# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 边境炮 TNT 配置解码      #
# =================================== #

# 边境炮 TNT 配置解码：把三颗 TNT 的当量拆成「小头（余量）+ 大头（满当量次数）」，
# 并拼出旧版那份多行中文报告（含方向、动量与预计落点）。
from __future__ import annotations

import numpy as np

from ..constants import (
    BIG_UNITS,
    BIN_UNITS,
    DIRECTION_CODE_TABLE,
    SMALL_UNITS,
)
from .landing import predict


# ------ 二进制展开 ------ #
def _bits_matrix(rest: np.ndarray, base: int) -> np.ndarray:
    """把一组十进制数字按 5 位二进制展开成 3x5 的数量矩阵。

    参数:
        rest: 形状 (3,) 的整数数组，每颗 TNT 在该进制位上的数字（0..31）。
        base: 该位数字的进制权重（如 260、10、1），单位个。

    返回:
        形状 (3, 5) 的浮点矩阵：行是第 i 颗 TNT，列对应 16 / 8 / 4 / 2 / 1 五个档位；
        元素 = 该位是否置 1 * 位权 * base，即这一档实际要放的 TNT 数。

    说明:
        5 位只覆盖 0..31；某档数字超过 31 时高位会被截断甚至越界（例如大头首位
        charges // 1000 > 31，约当量 ≥ 2496 万），这是本次复刻保留的旧边界，未加校验。
    """

    matrix = np.zeros((3, 5))
    for i in range(3):
        value = int(rest[i])
        # bin()[2:] 去掉 "0b" 前缀，zfill(5) 补足 5 位（高位在前）。
        matrix[i] = np.array(list(map(int, bin(value)[2:].zfill(5))))
    return matrix * np.array(BIN_UNITS) * base


# ------ 文本拼装 ------ #
def _parts(tnt: np.ndarray, units: tuple[int, ...], values: list[np.ndarray]) -> dict[int, list[str]]:
    """把「小头」或「大头」的各进制位展开成每行可读文本。

    参数:
        tnt: 三颗 TNT 的当量，形状 (3,)，单位个（当前实现只用于对齐维度）。
        units: 各进制位的权重，例如小头 (260, 10, 1)、大头 (1000, 100, 10, 1)。
        values: 与 units 等长的数字位数组，values[i] 形状 (3,)。

    返回:
        {行号: 文本}，行号 0/1/2 对应三颗 TNT；文本形如 "125 = 80 + 40 + 4 + 1 "（末尾带空格）。
        注意注解写的是 dict[int, list[str]]，实际存的是 str；这里只补注释、不改签名。

    说明:
        每行共 5 * len(units) 列 = 每个进制位的 5 个二进制档；只列出非零档，
        结尾的 " + " 会被 text[:-2] 切掉，于是留下一个尾随空格（旧版文本如此）。
    """

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


# ------ 对外入口 ------ #
def decompose(
    tnt: list[int],
    motion: dict,
    origin: tuple[float, float, float],
    dir_label: str,
) -> dict:
    """把三颗 TNT 的当量解码成小头 / 大头配置、落点与旧版报告文本。

    参数:
        tnt: 三颗 TNT 的当量，单位个，长度必须为 3。
        motion: {"x", "y", "z"} 三轴总动量，单位方块/gt。
        origin: 炮口坐标 (x, y, z)，单位方块。
        dir_label: 方向名或方向码，用于在报告里显示方位。

    返回:
        valid=True 时含 small / big（{行号: 文本}）、landing（{x, z, ticks}）、
        dirCode 与 text（多行中文报告）；任一颗为负时返回
        {"valid": False, "reason": ...}，不抛异常（旧版同样解不出来）。

    说明:
        小头 = 当量对 780 取余后按 260 / 10 / 1 展开；大头 = 当量 // 780 后按十进制位展开。
        780 = constants.FULL_CHARGE（一次满当量蓄力），旧版直接写字面量，这里保持一致。
    """

    numbers = np.array([int(v) for v in tnt])
    # 负数解在旧版也生成不出阵列（取模没有意义），返回可读原因而不是抛异常。
    if numbers.min() < 0:
        return {
            "valid": False,
            "reason": "该组配置包含负数 TNT，无法生成阵列（旧版同样无法解码）",
        }

    # 小头：先对 780 取余，再拆成「260 的个数 / 十位 / 个位」。
    small_values = [
        (numbers % 780) // 260,
        (numbers % 780) % 260 // 10,
        (numbers % 780) % 260 % 10,
    ]
    # 大头：整 780 的次数，按千 / 百 / 十 / 个四位展开。
    charges = numbers // 780
    big_values = [
        charges // 1000,
        charges % 1000 // 100,
        charges % 1000 % 100 // 10,
        charges % 1000 % 100 % 10,
    ]

    # 两套数字位分别展开成文本；tnt 只用于保持与旧版一致的调用形状。
    small = _parts(numbers, SMALL_UNITS, small_values)
    big = _parts(numbers, BIG_UNITS, big_values)
    # 落点只取决于总动量与炮口，与 TNT 怎么拆无关。
    landing = predict(motion["x"], motion["y"], motion["z"], origin)

    # 报告逐行拼接：分隔线固定 50 个字符，与旧版排版对齐。
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
    # :f 默认输出 6 位小数，旧版文本就是这种格式。
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
