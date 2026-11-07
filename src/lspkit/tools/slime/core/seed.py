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

注意两层的区别：
- parse_seed() 产出的是「世界种子」，即 Java 的 long（有符号 64 位）；
- seed_bits() 产出的是这个 long 的无符号 64 位位模式，供 bit 运算使用。
Java 的整数溢出是回绕语义，Python 的 int 是任意精度，所以凡是「参与
位运算」的地方都要先取模，否则负种子会被当成无限宽整数处理。
"""

from __future__ import annotations

import re

from ..constants import MASK64

# 只接受纯十进制整数（可带正负号）；带 0x、下划线或内部空格的一律走 hashCode
_LONG_RE = re.compile(r"^[+-]?\d+$")
_INT64_MIN = -(1 << 63)
_INT64_MAX = (1 << 63) - 1


def _utf16_units(text: str) -> list[int]:
    """把字符串拆成 UTF-16 码元序列（Java 的 char[]，每个 0..65535）.

    先按小端 UTF-16 编码再两字节一组还原：Java 的 char 是 16 位，
    所以 BMP 之外的字符会被拆成代理对（两个码元），这与 Java 行为一致。
    """

    raw = text.encode("utf-16-le")
    return [raw[i] | (raw[i + 1] << 8) for i in range(0, len(raw), 2)]


def java_string_hash(text: str) -> int:
    """Java String.hashCode()，按 UTF-16 码元计算，返回 32 位有符号整数.

    递推式 h = 31 * h + c，每步都对 2^32 取模（等价于 Java int 溢出回绕）；
    最后把 [2^31, 2^32) 的无符号值减 2^32 映射回有符号区间。
    """

    value = 0
    for unit in _utf16_units(text):
        value = (31 * value + unit) & 0xFFFFFFFF
    if value >= 0x80000000:
        value -= 0x100000000
    return value


def parse_seed(text: object) -> int:
    """把用户输入解析成 Java long（返回 Python int，范围 -2^63..2^63-1）.

    解析顺序与 Java 版一致：先试 Long.parseLong；数字格式但超出 long
    范围、或根本不是数字时，退回 String.hashCode()（32 位，天然在 long 内）。
    空输入直接报错，由调用方翻译成 INVALID_SEED。
    """

    raw = str(text if text is not None else "").strip()
    if not raw:
        raise ValueError("种子不能为空")

    if _LONG_RE.match(raw):
        value = int(raw, 10)
        if _INT64_MIN <= value <= _INT64_MAX:
            return value

    return java_string_hash(raw)


def seed_bits(seed: int) -> int:
    """把 long 转成 64 位无符号位模式.

    Python 的负数没有固定位宽，先 & MASK64 才能得到与 Java long 相同的
    补码位模式（-1 → 0xFFFF_FFFF_FFFF_FFFF）。
    """

    return int(seed) & MASK64
