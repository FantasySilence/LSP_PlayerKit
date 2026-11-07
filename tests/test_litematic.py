# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-05                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: .litematic 解析测试      #
# =================================== #
# 测试层：material 的 .litematic 纯解析器。
# 策略：在内存里手工拼最小 NBT + gzip，分别覆盖 compact / padded 两种位打包、
# 方块→物品映射、流体/空气过滤与三语名称；不依赖任何外部 .litematic 文件。

from __future__ import annotations

import gzip
import struct

import pytest

from lspkit.tools.material.core.litematic import LitematicError, parse_litematic


# ------ 构造最小 litematic ------ #


def _str(value: str) -> bytes:
    """NBT 字符串：2 字节大端长度 + UTF-8 内容."""
    raw = value.encode("utf-8")
    return struct.pack(">H", len(raw)) + raw


def _int(value: int) -> bytes:
    """NBT TAG_Int：4 字节大端有符号整数."""
    return struct.pack(">i", value)


def _compound(name: str, parts: list[bytes]) -> bytes:
    """带名字的 TAG_Compound（根 / 具名子标签），以 TAG_End=0 结尾."""
    return b"\x0a" + _str(name) + b"".join(parts) + b"\x00"


def _compound_payload(parts: list[bytes]) -> bytes:
    """列表里的复合标签只写负载，不带类型与名字。"""
    return b"".join(parts) + b"\x00"


def _int_tag(name: str, value: int) -> bytes:
    """TAG_Int 的完整编码：类型 0x03 + 名字 + 4 字节值."""
    return b"\x03" + _str(name) + _int(value)


def _string_tag(name: str, value: str) -> bytes:
    """TAG_String 的完整编码：类型 0x08 + 名字 + 字符串负载."""
    return b"\x08" + _str(name) + _str(value)


def _list_of_compounds(name: str, items: list[bytes]) -> bytes:
    """TAG_List：元素类型 0x0a（compound）+ 元素个数 + 各元素负载."""
    return b"\x09" + _str(name) + b"\x0a" + _int(len(items)) + b"".join(items)


def _long_array(name: str, values: list[int]) -> bytes:
    """TAG_LongArray：把 Python 整数按 64 位有符号补码写成大端 long.

    Litematica 的 BlockStates 是 long 数组；这里先做 >= 2^63 的回绕，
    保证负的 long 与 Java 的补码表示一致。
    """
    body = b"".join(
        struct.pack(">q", value - (1 << 64) if value >= (1 << 63) else value)
        for value in values
    )
    return b"\x0c" + _str(name) + _int(len(values)) + body


def _palette_entry(block_id: str, properties: dict | None = None) -> bytes:
    """调色板的一项：{Name: "minecraft:xxx", Properties: {...}}（Properties 可选）."""
    parts = [_string_tag("Name", block_id)]
    if properties:
        parts.append(
            _compound(
                "Properties",
                [_string_tag(key, value) for key, value in properties.items()],
            )
        )
    return _compound_payload(parts)


def _pack(indices: list[int], bits: int, layout: str) -> list[int]:
    """把调色板下标按指定布局压进 long 数组.

    compact：位流连续，允许一个下标跨 long 边界；
    padded ：每个 long 只放 64 // bits 个下标，剩余高位留空。
    两种布局的长度不同，解析器据此自动判别（见 core/litematic._unpack）。
    """
    mask = (1 << bits) - 1
    if layout == "compact":
        # compact 的总 long 数 = ceil(下标数 × 位宽 / 64)。
        size = (len(indices) * bits + 63) // 64
    # padded 每个 long 固定放 per_long 个，末尾不足的补 0。
    else:
        per_long = 64 // bits
        size = (len(indices) + per_long - 1) // per_long
    longs = [0] * size

    if layout == "compact":
        for index, value in enumerate(indices):
            bit = index * bits
            position = bit >> 6
            offset = bit & 63
            longs[position] |= (value & mask) << offset
            if offset + bits > 64:
                # 起始位 + 位宽超过 64 时，高位落到下一个 long 的低位。
                longs[position + 1] |= (value & mask) >> (64 - offset)
    else:
        per_long = 64 // bits
        for index, value in enumerate(indices):
            position = index // per_long
            offset = (index % per_long) * bits
            longs[position] |= (value & mask) << offset
    return longs


def build_litematic(
    palette: list[tuple[str, dict | None]],
    indices: list[int],
    volume: tuple[int, int, int],
    layout: str = "compact",
) -> bytes:
    """构造一个可被 parse_litematic 读取的最小 litematic 字节串.

    palette 是 (方块 id, Properties) 列表；indices 是每个格子的调色板下标；
    volume 是区域 x*y*z；layout 决定 BlockStates 用 compact 还是 padded。
    位宽按格式规定取 max(2, ceil(log2(调色板长度)))，并在根里写入
    MinecraftDataVersion=3465、Version=6 与 Regions。
    """
    bits = max(2, (len(palette) - 1).bit_length())
    # 位宽下限 2 是 litematic 格式规定，调色板只有 1 项时也不能是 0 位。
    entries = [_palette_entry(block_id, props) for block_id, props in palette]
    region = _compound(
        "R",
        [
            _compound("Position", [_int_tag("x", 0), _int_tag("y", 0), _int_tag("z", 0)]),
            _compound(
                "Size",
                [
                    _int_tag("x", volume[0]),
                    _int_tag("y", volume[1]),
                    _int_tag("z", volume[2]),
                ],
            ),
            _list_of_compounds("BlockStatePalette", entries),
            _long_array("BlockStates", _pack(indices, bits, layout)),
        ],
    )
    # Metadata.TotalBlocks 只统计非空气方块（下标 0 视为空气）；
    # MinecraftDataVersion 会被解析器读进 meta，Version 只用于让文件结构更像真实投影。
    root = _compound(
        "",
        [
            _int_tag("MinecraftDataVersion", 3465),
            _int_tag("Version", 6),
            _compound("Metadata", [_int_tag("TotalBlocks", sum(1 for i in indices if i))]),
            _compound("Regions", [region]),
        ],
    )
    return gzip.compress(root)


def _big_palette() -> list[tuple[str, dict | None]]:
    """17 项调色板：1 项空气 + 15 项占位方块 + 1 项石头.

    15 项占位把调色板撑到 17 项，使位宽变成 5；在 5 位下 compact 与 padded
    的 long 数量不同（100 格时分别是 8 与 9），解析器才能可靠区分两种布局。
    """
    palette: list[tuple[str, dict | None]] = [("minecraft:air", None)]
    palette += [(f"minecraft:test_{index}", None) for index in range(1, 16)]
    palette.append(("minecraft:stone", None))
    return palette


# ------ 测试 ------ #


def test_parses_compact_layout():
    """验证 compact 位流能正确解包并统计.

    输入：17 项调色板、100 格中 5 格石头、其余空气，compact 布局。
    期望：blocks=5，regions=1，layout="compact"，只统计出 5 个石头。
    """
    palette = _big_palette()
    stone = len(palette) - 1
    indices = [stone] * 5 + [0] * 95

    result = parse_litematic(build_litematic(palette, indices, (10, 10, 1), "compact"))

    assert result["meta"]["blocks"] == 5
    assert result["meta"]["regions"] == 1
    assert result["meta"]["layout"] == "compact"
    assert [(entry["name"], entry["count"]) for entry in result["entries"]] == [("石头", 5)]


def test_parses_padded_layout():
    """验证 padded 位流能正确解包并统计.

    输入：同样的调色板，100 格中 3 格石头，padded 布局。
    期望：layout="padded"，只统计出 3 个石头。
    """
    palette = _big_palette()
    stone = len(palette) - 1
    indices = [stone] * 3 + [0] * 97

    result = parse_litematic(build_litematic(palette, indices, (10, 10, 1), "padded"))

    assert result["meta"]["layout"] == "padded"
    assert [(entry["name"], entry["count"]) for entry in result["entries"]] == [("石头", 3)]


def test_merges_wall_variants_into_items():
    """验证墙类变体折算成本体物品后合并.

    输入：橡木告示牌 + 橡木墙告示牌、火把 + 墙火把各 1 个。
    期望：橡木告示牌 2、火把 2（_item_path 把 wall_ 变体映射到本体）。
    """
    palette = [
        ("minecraft:air", None),
        ("minecraft:oak_sign", None),
        ("minecraft:oak_wall_sign", None),
        ("minecraft:torch", None),
        ("minecraft:wall_torch", None),
    ]
    indices = [1, 2, 3, 4]

    result = parse_litematic(build_litematic(palette, indices, (2, 2, 1)))

    counts = {entry["name"]: entry["count"] for entry in result["entries"]}
    assert counts == {"橡木告示牌": 2, "火把": 2}


def test_cauldron_variants_and_redstone_wire():
    """验证炼药锅各变体与红石线的物品折算.

    输入：普通/水/岩浆/细雪炼药锅各 1 个，红石线 1 个，红石块 1 个。
    期望：炼药锅合计 4，红石粉 1（redstone_wire → redstone）。
    """
    palette = [
        ("minecraft:air", None),
        ("minecraft:cauldron", None),
        ("minecraft:water_cauldron", {"level": "3"}),
        ("minecraft:lava_cauldron", None),
        ("minecraft:powder_snow_cauldron", {"level": "3"}),
        ("minecraft:redstone_wire", None),
        ("minecraft:redstone_block", None),
    ]
    indices = [1, 2, 3, 4, 5, 6]

    result = parse_litematic(build_litematic(palette, indices, (2, 4, 1)))

    counts = {entry["name"]: entry["count"] for entry in result["entries"]}
    assert counts["炼药锅"] == 4
    assert counts["红石粉"] == 1


def test_filters_collectable_none_blocks():
    """验证没有物品形式的方块会被过滤.

    输入：气泡柱、流动水、流动岩浆、石头各 1 个。
    期望：只剩石头 1；filtered=3，items=1（流动流体与气泡柱不可收集）。
    """
    palette = [
        ("minecraft:air", None),
        ("minecraft:bubble_column", {"drag": "up"}),
        ("minecraft:water", {"level": "5"}),
        ("minecraft:lava", {"level": "2"}),
        ("minecraft:stone", None),
    ]
    indices = [1, 2, 3, 4]

    result = parse_litematic(build_litematic(palette, indices, (2, 2, 1)))

    counts = {entry["name"]: entry["count"] for entry in result["entries"]}
    assert counts == {"石头": 1}
    assert result["meta"]["filtered"] == 3
    assert result["meta"]["items"] == 1


def test_source_water_becomes_bucket():
    """验证只有源头流体（level=0）能折算成桶.

    输入：水源方块 ×2、岩浆源方块 ×1（均 level=0）。
    期望：水桶 2、熔岩桶 1。
    """
    palette = [
        ("minecraft:water", {"level": "0"}),
        ("minecraft:lava", {"level": "0"}),
    ]
    indices = [0, 0, 1]

    result = parse_litematic(build_litematic(palette, indices, (3, 1, 1)))

    counts = {entry["name"]: entry["count"] for entry in result["entries"]}
    assert counts == {"水桶": 2, "熔岩桶": 1}


def test_missing_regions_is_rejected():
    """验证缺少 Regions 的 NBT 会报 LitematicError.

    输入：只有 MinecraftDataVersion 的根 compound。
    期望：parse_litematic 抛 LitematicError（投影里没有任何区域）。
    """
    data = gzip.compress(_compound("", [_int_tag("MinecraftDataVersion", 3465)]))
    with pytest.raises(LitematicError):
        parse_litematic(data)


def test_not_a_nbt_file_is_rejected():
    """验证非 NBT 字节会报 LitematicError.

    输入：b"not a schematic"。
    期望：根标签不是 TAG_Compound，parse_litematic 抛 LitematicError。
    """
    with pytest.raises(LitematicError):
        parse_litematic(b"not a schematic")

def test_names_follow_locale():
    """验证同一批方块在三种语言下输出不同名称.

    输入：石头 + 橡木墙告示牌，locale 分别为 zh_CN / zh_TW / en。
    期望：石头 / 石頭 / Stone，橡木告示牌 / 橡木告示牌 / Oak Sign；
          所有条目 id 仍带 minecraft: 命名空间。
    """
    palette = [
        ("minecraft:air", None),
        ("minecraft:stone", None),
        ("minecraft:oak_wall_sign", None),
    ]
    data = build_litematic(palette, [1, 2], (2, 1, 1))

    simplified = parse_litematic(data, "zh_CN")
    traditional = parse_litematic(data, "zh_TW")
    english = parse_litematic(data, "en")

    assert {entry["name"] for entry in simplified["entries"]} == {"石头", "橡木告示牌"}
    assert {entry["name"] for entry in traditional["entries"]} == {"石頭", "橡木告示牌"}
    assert {entry["name"] for entry in english["entries"]} == {"Stone", "Oak Sign"}
    assert all(entry["id"].startswith("minecraft:") for entry in english["entries"])
