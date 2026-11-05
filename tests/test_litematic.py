# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-05                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: .litematic 解析测试      #
# =================================== #

from __future__ import annotations

import gzip
import struct

import pytest

from lspkit.tools.material.core.litematic import LitematicError, parse_litematic


# ------ 构造最小 litematic ------ #


def _str(value: str) -> bytes:
    raw = value.encode("utf-8")
    return struct.pack(">H", len(raw)) + raw


def _int(value: int) -> bytes:
    return struct.pack(">i", value)


def _compound(name: str, parts: list[bytes]) -> bytes:
    return b"\x0a" + _str(name) + b"".join(parts) + b"\x00"


def _compound_payload(parts: list[bytes]) -> bytes:
    """列表里的复合标签只写负载，不带类型与名字。"""
    return b"".join(parts) + b"\x00"


def _int_tag(name: str, value: int) -> bytes:
    return b"\x03" + _str(name) + _int(value)


def _string_tag(name: str, value: str) -> bytes:
    return b"\x08" + _str(name) + _str(value)


def _list_of_compounds(name: str, items: list[bytes]) -> bytes:
    return b"\x09" + _str(name) + b"\x0a" + _int(len(items)) + b"".join(items)


def _long_array(name: str, values: list[int]) -> bytes:
    body = b"".join(
        struct.pack(">q", value - (1 << 64) if value >= (1 << 63) else value)
        for value in values
    )
    return b"\x0c" + _str(name) + _int(len(values)) + body


def _palette_entry(block_id: str, properties: dict | None = None) -> bytes:
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
    mask = (1 << bits) - 1
    if layout == "compact":
        size = (len(indices) * bits + 63) // 64
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
    bits = max(2, (len(palette) - 1).bit_length())
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
    palette: list[tuple[str, dict | None]] = [("minecraft:air", None)]
    palette += [(f"minecraft:test_{index}", None) for index in range(1, 16)]
    palette.append(("minecraft:stone", None))
    return palette


# ------ 测试 ------ #


def test_parses_compact_layout():
    palette = _big_palette()
    stone = len(palette) - 1
    indices = [stone] * 5 + [0] * 95

    result = parse_litematic(build_litematic(palette, indices, (10, 10, 1), "compact"))

    assert result["meta"]["blocks"] == 5
    assert result["meta"]["regions"] == 1
    assert result["meta"]["layout"] == "compact"
    assert [(entry["name"], entry["count"]) for entry in result["entries"]] == [("石头", 5)]


def test_parses_padded_layout():
    palette = _big_palette()
    stone = len(palette) - 1
    indices = [stone] * 3 + [0] * 97

    result = parse_litematic(build_litematic(palette, indices, (10, 10, 1), "padded"))

    assert result["meta"]["layout"] == "padded"
    assert [(entry["name"], entry["count"]) for entry in result["entries"]] == [("石头", 3)]


def test_merges_wall_variants_into_items():
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
    palette = [
        ("minecraft:water", {"level": "0"}),
        ("minecraft:lava", {"level": "0"}),
    ]
    indices = [0, 0, 1]

    result = parse_litematic(build_litematic(palette, indices, (3, 1, 1)))

    counts = {entry["name"]: entry["count"] for entry in result["entries"]}
    assert counts == {"水桶": 2, "熔岩桶": 1}


def test_missing_regions_is_rejected():
    data = gzip.compress(_compound("", [_int_tag("MinecraftDataVersion", 3465)]))
    with pytest.raises(LitematicError):
        parse_litematic(data)


def test_not_a_nbt_file_is_rejected():
    with pytest.raises(LitematicError):
        parse_litematic(b"not a schematic")

def test_names_follow_locale():
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
