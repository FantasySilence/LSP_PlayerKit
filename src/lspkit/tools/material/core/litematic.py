# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-05                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: .litematic 投影解析      #
# =================================== #
# 纯函数：把 .litematic 二进制文件统计成「物品 ID → 数量」。
# 流程：gzip 解压 → NBT 解析 → 遍历 Regions → 解包方块索引 → 按调色板计数
#      → 方块名折算成物品形式 → 查三语名称。
# 不读磁盘、不依赖 webview；文件由 api.py 的 _read_litematic 读入后传字节进来。

from __future__ import annotations

import gzip
import struct

import numpy as np

from ..constants import MAX_KINDS
from .block_items import BLOCK_ITEM_FORMS
from .localize import item_name

# ------ 常量 ------ #

# 单次导入的体积上限（方块数），超过说明投影太大，提示用户拆分；
# 体积按所有区域的 x*y*z 累加，与是否空区域无关
MAX_VOLUME = 50_000_000
# 三种空气都不计入材料
AIR_BLOCKS = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}

# 流体：只有 level=0 的源头能收集成桶
# 流动的水 / 岩浆 level>0，用桶接不到，统计时应剔除
_FLUID_ITEMS = {"water": "water_bucket", "lava": "lava_bucket"}

# Wiki 抓取截断在 S 段，这些方块没有物品形式
_NO_ITEM_BLOCKS = {"soul_fire", "void_air", "structure_void"}

# Wiki 抓取截断在 S 段，这些方块的物品 ID 与方块 ID 不同
_ITEM_ALIASES = {"wheat": "wheat_seeds", "tripwire": "string"}

# NBT 标签类型编号（与 NBT 规范一致，1..12）
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

    NBT 是「标签类型 + 名称 + 负载」的树：这里只做顺序读取，不建完整索引。
    所有长度字段都做上限检查，避免损坏的文件让内存爆掉。
    """

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0

    def _take(self, size: int) -> bytes:
        """
        取 size 字节并前移游标；越界说明文件被截断，直接报错.
        """

        end = self._pos + size
        if size < 0 or end > len(self._data):
            raise LitematicError("投影数据不完整")
        chunk = self._data[self._pos:end]
        self._pos = end
        return chunk

    def _unpack(self, fmt: str, size: int):
        """
        按 struct 格式解一个大端标量，size 为它占的字节数.
        """

        return struct.unpack(fmt, self._take(size))[0]

    def _u1(self) -> int:
        return self._take(1)[0]

    def _string(self) -> str:
        """
        NBT 字符串：2 字节大端长度（字符数）+ UTF-8 内容.
        """

        length = self._unpack(">H", 2)
        return self._take(length).decode("utf-8", "replace")

    def read_root(self) -> dict:
        """
        读根标签：必须是带名字的 compound（TAG_Compound）.
        """

        tag = self._u1()
        if tag != _TAG_COMPOUND:
            raise LitematicError("不是有效的 .litematic（NBT 根标签错误）")
        self._string()
        root = self._payload(tag)
        if not isinstance(root, dict):
            raise LitematicError("不是有效的 .litematic（NBT 结构错误）")
        return root

    def _payload(self, tag: int):
        """
        按标签类型读取负载，返回 Python 标量 / bytes / list / dict.

        LongArray 用 numpy 的大端 int64 直接映射，供后面按位解包，
        避免几百万个 long 逐个转成 Python int。
        """

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
            # 列表元素同类型：先读一个元素类型 + 元素个数，再逐个读负载
            element = self._u1()
            count = self._unpack(">i", 4)
            if count < 0:
                raise LitematicError("投影数据不完整")
            return [self._payload(element) for _ in range(count)]
        if tag == _TAG_COMPOUND:
            # compound 以 TAG_End(0) 结尾，每个子标签前都有名字
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
# 投影把每个方块的调色板下标按 bits 位宽压进一串 long（64 位）里，有两种排布：
#   compact  Litematica 自有：下标位流连续，允许跨 long 边界；
#   padded   1.16+ 原版风格：每个 long 只放 64 // bits 个，余下的高位留空。
# 两者长度不同，_unpack 用长度差自动判别，不需要读版本号。


def _unpack_compact(states: np.ndarray, volume: int, bits: int) -> np.ndarray:
    """
    Litematica 自有的紧凑打包：索引跨 long 连续存放.

    第 i 个下标的起始位 = i * bits，落在第 (i*bits)>>6 个 long 的第 (i*bits)&63 位；
    当起始位 + bits 超过 64 时，高位溢出到下一个 long，需要拼回来。
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
        # 跨界的下标需要下一个 long 的低位；最后一个长还跨界说明数据被截断
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

    per_long = 64 // bits 个下标并排放在一个 long 的低位，
    展平后取前 volume 个即可（末尾多余的是填充位）。
    """

    per_long = 64 // bits
    longs = states.astype(np.uint64, copy=False)
    mask = np.uint64((1 << bits) - 1)
    shifts = np.arange(per_long, dtype=np.uint64) * np.uint64(bits)
    values = (longs[:, None] >> shifts) & mask
    return values.reshape(-1)[:volume]


def _unpack(states: np.ndarray, volume: int, bits: int) -> tuple[np.ndarray, str]:
    """
    按 long 数组长度判别打包方式并解包，返回（下标数组, "compact"/"padded"）.

    compact_len = ceil(volume*bits / 64)，padded_len = ceil(volume / (64//bits))；
    两者只有在 bits 能整除 64 时相等，此时优先按 compact 处理（结果一致）。
    """

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

    判定顺序即优先级：流体 → 无物品方块 → 别名 → 映射表 → 规则。
    映射表里值为 None 的条目表示「该方块没有物品形式」，同样返回 None。
    """

    if block_path in _FLUID_ITEMS:
        # level 缺省按 0 处理：没有 Properties 的流体视为源头
        level = str(properties.get("level", "0"))
        return _FLUID_ITEMS[block_path] if level == "0" else None

    if block_path in _NO_ITEM_BLOCKS:
        return None

    if block_path in _ITEM_ALIASES:
        return _ITEM_ALIASES[block_path]

    if block_path in BLOCK_ITEM_FORMS:
        return BLOCK_ITEM_FORMS[block_path]

    # Wiki 只抓到 S 段，以下规则覆盖剩余的方块形态：
    # 墙类去掉 wall_ 前缀 / 中缀即为其本体（如 wall_torch → torch）；
    # 炼药锅的各变体统一折算成炼药锅
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

    这里补齐 minecraft: 命名空间后交给 localize.item_name 查表。
    """

    return item_name("minecraft:" + item_path, locale)


# ------ 主入口 ------ #


def parse_litematic(data: bytes, locale: str = "zh_cn") -> dict:
    """
    解析 .litematic，按物品形式统计材料；locale 决定材料名的语言.

    步骤：
    1. 文件头是 1f 8b（gzip 魔数）时先解压；Litematica 生成的文件基本都是压缩的，
       未压缩的也能读取，所以按魔数判断而不是按后缀；
    2. NBT 根标签里取 Regions，每个区域含 Size / BlockStatePalette / BlockStates；
    3. 体积 = x*y*z；位宽 bits = max(2, ceil(log2(palette 长度)))，
       下限 2 是格式规定（调色板只有 1 项时也按 2 位存放）；
    4. 解包出每个格子的调色板下标，用 bincount 直方图统计，避免逐块 Python 循环；
    5. 只统计非空气方块；方块名去掉命名空间后折算成物品形式，
       不可收集（无物品形式、流动流体）的计入 filtered 并从结果剔除；
    6. 统计结果按数量降序，名字用 item_name 本地化，最后返回 entries / meta / warnings。
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

        # 位宽：调色板需要能表示 0..len(palette)-1，故取 (len-1) 的二进制位长；
        # 格式下限是 2 位，与 max 一起取保证 palette=1 时也不会算出 0 位
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

        # 直方图统计：下标即调色板位置，一次 bincount 得到每种方块的格数
        histogram = np.bincount(indices.astype(np.int64), minlength=len(palette))
        used_regions += 1
        for position, entry in enumerate(palette):
            count = int(histogram[position])
            if count <= 0:
                continue

            # BlockStatePalette 的每一项是 {Name: "minecraft:xxx", Properties: {...}}
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
                # 不计入 items：这些方块拿不到对应物品（如流动水、结构空位）
                filtered += count
                continue

            item_id = "minecraft:" + item_path
            counts[item_id] = counts.get(item_id, 0) + count
            items += count

    if not counts:
        raise LitematicError("投影里没有可统计的材料（方块都没有物品形式）")

    # 材料种类超过上限时只保留数量最多的几种，并给出提示
    truncated = False
    if len(counts) > MAX_KINDS:
        kept = sorted(counts.items(), key=lambda item: -item[1])[:MAX_KINDS]
        counts = dict(kept)
        truncated = True
        warnings.append(f"材料种类过多，只保留数量最多的 {MAX_KINDS} 种")

    # 排序键第二项是本地化名字，保证同数量时顺序稳定且符合当前语言习惯
    entries = [
        {"id": item_id, "name": item_name(item_id, locale), "count": count}
        for item_id, count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item_name(item[0], locale)),
        )
    ]

    # meta 供界面显示概况：regions 为参与统计的区域数，volume 为体积（方块格），
    # blocks 为非空气方块数，items 为可收集方块数，filtered 为被剔除的方块数，
    # layout 为识别到的打包方式（多个区域不一致时为 mixed）
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
