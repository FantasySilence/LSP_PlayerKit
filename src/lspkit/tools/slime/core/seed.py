# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-07                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 世界种子解析             #
# =================================== #
"""
Minecraft Java 版的种子解析规则：

1. 能按十进制 long 解析的字符串，直接当 64 位有符号整数；
2. 否则按 Java String.hashCode()（32 位有符号）转成整数。

前端一律以字符串传种子，避免 JS Number 超过 2^53 丢精度。
"""

from __future__ import annotations

import re

from ..constants import MASK64

_LONG_RE = re.compile(r"^[+-]?\d+$")
_INT64_MIN = -(1 << 63)
_INT64_MAX = (1 << 63) - 1


def _utf16_units(text: str) -> list[int]:
    raw = text.encode("utf-16-le")
    return [raw[i] | (raw[i + 1] << 8) for i in range(0, len(raw), 2)]


def java_string_hash(text: str) -> int:
    """Java String.hashCode()，按 UTF-16 码元计算，返回 32 位有符号整数."""

    value = 0
    for unit in _utf16_units(text):
        value = (31 * value + unit) & 0xFFFFFFFF
    if value >= 0x80000000:
        value -= 0x100000000
    return value


def parse_seed(text: object) -> int:
    """把用户输入解析成 Java long（返回 Python int，范围 -2^63..2^63-1）."""

    raw = str(text if text is not None else "").strip()
    if not raw:
        raise ValueError("种子不能为空")

    if _LONG_RE.match(raw):
        value = int(raw, 10)
        if _INT64_MIN <= value <= _INT64_MAX:
            return value

    return java_string_hash(raw)


def seed_bits(seed: int) -> int:
    """把 long 转成 64 位无符号位模式."""

    return int(seed) & MASK64
