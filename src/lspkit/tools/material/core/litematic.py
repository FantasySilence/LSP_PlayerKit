# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-05                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: .litematic 投影解析      #
# =================================== #

from __future__ import annotations

import gzip
import struct

import numpy as np

from ..constants import MAX_KINDS
from .block_items import BLOCK_ITEM_FORMS
from .localize import item_name

# ------ 常量 ------ #

MAX_VOLUME = 50_000_000
AIR_BLOCKS = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}

# 流体：只有 level=0 的源头能收集成桶
_FLUID_ITEMS = {"water": "water_bucket", "lava": "lava_bucket"}

# Wiki 抓取截断在 S 段，这些方块没有物品形式
_NO_ITEM_BLOCKS = {"soul_fire", "void_air", "structure_void"}

# Wiki 抓取截断在 S 段，这些方块的物品 ID 与方块 ID 不同
_ITEM_ALIASES = {"wheat": "wheat_seeds", "tripwire": "string"}

_TAG_BYTE = 1
_TAG_SHORT = 2
_TAG_INT = 3
_TAG_LONG = 4
_TAG_FLOAT = 5
_TAG_DOUBLE = 6
_TAG_BYTE_ARRAY = 7
_TAG_STRING = 8
_TAG_LIST = 9
_TAG_COMPOUND = 10
_TAG_INT_ARRAY = 11
_TAG_LONG_ARRAY = 12


class LitematicError(ValueError):
    """
    投影文件无法解析时抛出，消息可直接展示给用户.
    """


# ------ NBT 读取 ------ #


class _NbtReader:
    """
    只实现材料统计所需的 NBT 标签；遇到越界/非法标签直接报错.
    """

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0

    def _take(self, size: int) -> bytes:
        end = self._pos + size
        if size < 0 or end > len(self._data):
            raise LitematicError("投影数据不完整")
        chunk = self._data[self._pos:end]
        self._pos = end
        return chunk

    def _unpack(self, fmt: str, size: int):
        return struct.unpack(fmt, self._take(size))[0]

    def _u1(self) -> int:
        return self._take(1)[0]

    def _string(self) -> str:
        length = self._unpack(">H", 2)
        return self._take(length).decode("utf-8", "replace")

    def read_root(self) -> dict:
        tag = self._u1()
        if tag != _TAG_COMPOUND:
            raise LitematicError("不是有效的 .litematic（NBT 根标签错误）")
        self._string()
        root = self._payload(tag)
        if not isinstance(root, dict):
            raise LitematicError("不是有效的 .litematic（NBT 结构错误）")
        return root

    def _payload(self, tag: int):
        if tag == _TAG_BYTE:
            return self._take(1)[0]
        if tag == _TAG_SHORT:
            return self._unpack(">h", 2)
        if tag == _TAG_INT:
            return self._unpack(">i", 4)
        if tag == _TAG_LONG:
            return self._unpack(">q", 8)
        if tag == _TAG_FLOAT:
            return self._unpack(">f", 4)
        if tag == _TAG_DOUBLE:
            return self._unpack(">d", 8)
        if tag == _TAG_BYTE_ARRAY:
            return self._take(self._unpack(">i", 4))
        if tag == _TAG_STRING:
            return self._string()
        if tag == _TAG_LIST:
            element = self._u1()
            count = self._unpack(">i", 4)
            if count < 0:
                raise LitematicError("投影数据不完整")
            return [self._payload(element) for _ in range(count)]
        if tag == _TAG_COMPOUND:
            result = {}
            while True:
                child = self._u1()
                if child == 0:
                    return result
                name = self._string()
                result[name] = self._payload(child)
        if tag == _TAG_INT_ARRAY:
            count = self._unpack(">i", 4)
            if count < 0:
                raise LitematicError("投影数据不完整")
            return list(struct.unpack(">%di" % count, self._take(4 * count)))
        if tag == _TAG_LONG_ARRAY:
            count = self._unpack(">i", 4)
            if count < 0:
                raise LitematicError("投影数据不完整")
            block = self._take(8 * count)
            return np.frombuffer(block, dtype=">i8").astype(np.int64)
        raise LitematicError(f"投影里出现了不支持的 NBT 标签：{tag}")


# ------ 位打包解包 ------ #


def _unpack_compact(states: np.ndarray, volume: int, bits: int) -> np.ndarray:
    """
    Litematica 自有的紧凑打包：索引跨 long 连续存放.
    """

    longs = states.astype(np.uint64, copy=False)
    index = np.arange(volume, dtype=np.int64)
    bit = index * bits
    long_index = bit >> 6
    shift = (bit & 63).astype(np.uint64)
    mask = np.uint64((1 << bits) - 1)

    values = (longs[long_index] >> shift) & mask
    cross = (shift + np.uint64(bits)) > np.uint64(64)
    if cross.any():
        valid = cross & ((long_index + 1) < longs.size)
        if bool((cross & ~valid).any()):
            raise LitematicError("投影数据不完整（方块索引越界）")
        spill = np.zeros(volume, dtype=np.uint64)
        spill[valid] = (
            longs[long_index[valid] + 1] << (np.uint64(64) - shift[valid])
        ) & mask
        values = values | spill
    return values


def _unpack_padded(states: np.ndarray, volume: int, bits: int) -> np.ndarray:
    """
    1.16+ 原版风格的补齐打包：每个 long 放固定个数.
    """

    per_long = 64 // bits
    longs = states.astype(np.uint64, copy=False)
    mask = np.uint64((1 << bits) - 1)
    shifts = np.arange(per_long, dtype=np.uint64) * np.uint64(bits)
    values = (longs[:, None] >> shifts) & mask
    return values.reshape(-1)[:volume]


def _unpack(states: np.ndarray, volume: int, bits: int) -> tuple[np.ndarray, str]:
    per_long = 64 // bits
    compact_len = (volume * bits + 63) // 64
    padded_len = (volume + per_long - 1) // per_long

    if states.size == compact_len:
        return _unpack_compact(states, volume, bits), "compact"
    if states.size == padded_len:
        return _unpack_padded(states, volume, bits), "padded"
    raise LitematicError(
        "投影的方块数据长度与体积不匹配"
        f"（{states.size} 个 long，体积 {volume}）"
    )


# ------ 物品形式映射 ------ #


def _item_path(block_path: str, properties: dict) -> str | None:
    """
    方块名（不含命名空间）折算成物品 ID；返回 None 表示不可收集.

    - 水/岩浆：只有源头（level=0）能收集成桶，流动形态剔除；
    - 优先用 Wiki「物品形式」列，其次用规则补齐 S 段之后未抓到的方块。
    """

    if block_path in _FLUID_ITEMS:
        level = str(properties.get("level", "0"))
        return _FLUID_ITEMS[block_path] if level == "0" else None

    if block_path in _NO_ITEM_BLOCKS:
        return None

    if block_path in _ITEM_ALIASES:
        return _ITEM_ALIASES[block_path]

    if block_path in BLOCK_ITEM_FORMS:
        return BLOCK_ITEM_FORMS[block_path]

    # Wiki 只抓到 S 段，以下规则覆盖剩余的方块形态
    if block_path.startswith("wall_"):
        return block_path[len("wall_"):]
    if "_wall_" in block_path:
        return block_path.replace("_wall_", "_")
    if block_path.endswith("_cauldron"):
        return "cauldron"
    return block_path


def _item_name(item_path: str, locale: str) -> str:
    """
    物品 ID 转当前语言的显示名.
    """

    return item_name("minecraft:" + item_path, locale)


# ------ 主入口 ------ #


def parse_litematic(data: bytes, locale: str = "zh_cn") -> dict:
    """
    解析 .litematic，按物品形式统计材料；locale 决定材料名的语言.
    """

    if not data:
        raise LitematicError("文件是空的")

    raw = data
    if raw[:2] == b"\x1f\x8b":
        try:
            raw = gzip.decompress(raw)
        except (OSError, EOFError) as exc:
            raise LitematicError("不是有效的 .litematic（gzip 解压失败）") from exc

    reader = _NbtReader(raw)
    root = reader.read_root()

    regions = root.get("Regions")
    if not isinstance(regions, dict) or not regions:
        raise LitematicError("投影里没有任何区域")

    metadata = root.get("Metadata") or {}
    data_version = root.get("MinecraftDataVersion")

    counts: dict[str, int] = {}
    warnings: list[str] = []
    volumes = 0
    blocks = 0
    items = 0
    filtered = 0
    layouts: set[str] = set()
    used_regions = 0

    for region_name, region in regions.items():
        if not isinstance(region, dict):
            continue
        size = region.get("Size") or {}
        try:
            volume = int(size.get("x", 0)) * int(size.get("y", 0)) * int(size.get("z", 0))
        except (TypeError, ValueError):
            volume = 0
        if volume <= 0:
            continue

        palette = region.get("BlockStatePalette") or []
        states = region.get("BlockStates")
        if not palette or states is None or len(states) == 0:
            continue

        volumes += volume
        if volumes > MAX_VOLUME:
            raise LitematicError(
                f"投影太大（超过 {MAX_VOLUME // 1_000_000} 百万方块），请拆分后再导入"
            )

        bits = max(2, (len(palette) - 1).bit_length())
        try:
            indices, layout = _unpack(states, volume, bits)
        except LitematicError:
            raise
        except Exception as exc:  # noqa: BLE001 - 数据异常统一转成可读错误
            raise LitematicError(f"无法解析区域「{region_name}」的方块数据") from exc

        layouts.add(layout)
        if int(indices.max()) >= len(palette):
            raise LitematicError(f"区域「{region_name}」的调色板索引越界")

        histogram = np.bincount(indices.astype(np.int64), minlength=len(palette))
        used_regions += 1
        for position, entry in enumerate(palette):
            count = int(histogram[position])
            if count <= 0:
                continue

            block_id = ""
            properties: dict = {}
            if isinstance(entry, dict):
                block_id = str(entry.get("Name") or "")
                raw_props = entry.get("Properties")
                if isinstance(raw_props, dict):
                    properties = raw_props
            if not block_id or block_id in AIR_BLOCKS:
                continue

            blocks += count
            namespace, _, path = block_id.partition(":")
            if namespace != "minecraft":
                # 自定义方块没有映射表，按原 ID 统计并假定可收集
                counts[block_id] = counts.get(block_id, 0) + count
                items += count
                continue

            item_path = _item_path(path, properties)
            if item_path is None:
                filtered += count
                continue

            item_id = "minecraft:" + item_path
            counts[item_id] = counts.get(item_id, 0) + count
            items += count

    if not counts:
        raise LitematicError("投影里没有可统计的材料（方块都没有物品形式）")

    truncated = False
    if len(counts) > MAX_KINDS:
        kept = sorted(counts.items(), key=lambda item: -item[1])[:MAX_KINDS]
        counts = dict(kept)
        truncated = True
        warnings.append(f"材料种类过多，只保留数量最多的 {MAX_KINDS} 种")

    entries = [
        {"id": item_id, "name": item_name(item_id, locale), "count": count}
        for item_id, count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item_name(item[0], locale)),
        )
    ]

    return {
        "entries": entries,
        "meta": {
            "regions": used_regions,
            "volume": volumes,
            "blocks": blocks,
            "items": items,
            "filtered": filtered,
            "kinds": len(entries),
            "dataVersion": data_version,
            "layout": "mixed" if len(layouts) > 1 else (next(iter(layouts)) if layouts else ""),
            "name": str(metadata.get("Name") or ""),
        },
        "warnings": warnings,
        "truncated": truncated,
    }
