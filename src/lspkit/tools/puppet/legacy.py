# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 旧站点配置导入           #
# =================================== #

"""
旧版站点配置导入。

支持以下四类输入，按内容首字符自动判别：
1. JSON 对象 {"stations": [...]}：本工具导出的格式，可直接再导入；
2. JSON 数组 [...]：站点对象列表，键名同导出的 JSON；
3. JSON 对象 {"站点名": {...}}：旧版 stops.json，键是显示名、值是坐标与前缀；
4. 纯文本：每行一条，「名称 x y z 前缀」最少 5 列，也接受 6 / 7 列。

统一输出 {format, stations, skipped, warnings}：
- format 是 "json" 或 "lines"，供动作层回显；
- stations 是规整前的原始 dict 列表，最终校验交给 core/stations.normalize；
- skipped 是逐条被丢弃的原因（行号 / 站点名 + 原因），warnings 是不致命提示。
导入时只抛 ValueError：空内容、坏 JSON、无法识别的结构属于结构性错误，
单条站点的问题（缺前缀、坐标不是数字等）只记进 skipped / warnings，不影响其余站点。
"""

from __future__ import annotations

import json

from .constants import DIMENSIONS


def convert(raw: dict) -> dict:
    """
    设置导入的旧格式迁移：假人搬货没有旧版设置文件，原样返回.

    保留这个空实现是为了满足注册表对 LEGACY 钩子的要求。
    """

    return raw

# ------ 旧 command.txt 的前缀里带维度，导入时顺便拆出来 ------ #
# 顺序有意义：先匹配更长的前缀，否则 end_ 会先把 the_end_ 截走.
# 命中后前缀会去掉这一段，例如 the_end_wh → 维度 the_end + 前缀 wh。
DIMENSION_PREFIXES = (
    ("the_end_", "the_end"),
    ("nether_", "the_nether"),
    ("end_", "the_end"),
    ("ov_", "overworld"),
)


def parse(text: str, default_dimension: str = "overworld") -> dict:
    """
    解析旧版站点配置：stops.json（对象）或「名称 x y z 前缀」文本.

    返回 {format, stations, skipped, warnings}.

    default_dimension 用于文本里没有维度、前缀里也没带维度线索的行。
    判型只去掉 BOM 与空白后看首字符，不做完整 JSON 预检，坏 JSON 由 _parse_json 报错。
    """

    if not isinstance(text, str) or not text.strip():
        raise ValueError("导入内容为空")

    # 去 BOM：Windows 记事本存出来的 UTF-8 常带 \ufeff，会破坏首字符判断.
    stripped = text.lstrip("\ufeff \t\r\n")
    if stripped.startswith("{") or stripped.startswith("["):
        return _parse_json(stripped, default_dimension)
    return _parse_lines(text, default_dimension)


# ------------------------------ JSON ------------------------------ #
def _parse_json(text: str, default_dimension: str) -> dict:
    """
    解析 JSON 形态的站点配置，兼容「新导出」与「旧 stops.json」两种结构.

    新结构（dict 含 stations 列表 / 直接是 list）：逐项走 _from_new_format；
    旧结构（dict 的键是站点名）：逐项走 _from_stops。
    两种结构最后都会去重，重复项并入 skipped。
    """

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        # 带上行号，用户能直接定位到出问题的位置.
        raise ValueError(f"JSON 解析失败：{exc.msg}（第 {exc.lineno} 行）") from None

    skipped: list = []
    warnings: list = []
    stations: list = []

    if isinstance(raw, dict) and isinstance(raw.get("stations"), list):
        for index, item in enumerate(raw["stations"], 1):
            station = _from_new_format(item, default_dimension, skipped, warnings, index)
            if station:
                stations.append(station)
    elif isinstance(raw, list):
        for index, item in enumerate(raw, 1):
            station = _from_new_format(item, default_dimension, skipped, warnings, index)
            if station:
                stations.append(station)
    elif isinstance(raw, dict):
        # 旧 stops.json：{"仓库A": {"coordinate": {...}, "prefix": "wa"}}
        for name, item in raw.items():
            station = _from_stops(name, item, default_dimension, skipped, warnings)
            if station:
                stations.append(station)
    else:
        raise ValueError("无法识别的 JSON 结构")

    stations, dropped = _dedupe(stations, warnings)
    return {
        "format": "json",
        "stations": stations,
        "skipped": skipped + dropped,
        "warnings": warnings,
    }


def _from_stops(name: str, item, default_dimension: str, skipped, warnings) -> dict | None:
    """
    把旧 stops.json 的一条（键 = 站点名）转成站点原始 dict.

    坐标兼容两种写法：嵌套的 {"coordinate": {x,y,z}} 或平铺的 x / y / z。
    缺少前缀或维度不可用时返回 None，并把原因写进 skipped / warnings。
    """

    if not isinstance(item, dict):
        skipped.append({"source": name, "reason": "站点内容不是对象"})
        return None

    coordinate = item.get("coordinate")
    if not isinstance(coordinate, dict):
        coordinate = {"x": item.get("x"), "y": item.get("y"), "z": item.get("z")}

    # 维度不认识时 _dimension 会回落成 default_dimension 并记 warning，不丢数据.
    dimension = _dimension(item.get("dimension"), default_dimension, warnings, str(name))
    if dimension is None:
        return None

    prefix = str(item.get("prefix") or "").strip()
    if not prefix:
        skipped.append({"source": str(name), "reason": "缺少前缀"})
        return None

    # id 直接取前缀：旧数据没有独立 id，用前缀当主键最省事.
    return {
        "id": prefix,
        "name": str(name),
        "group": str(item.get("group", "") or ""),
        "prefix": prefix,
        "dimension": dimension,
        "x": coordinate.get("x"),
        "y": coordinate.get("y"),
        "z": coordinate.get("z"),
    }


def _from_new_format(item, default_dimension: str, skipped, warnings, index: int) -> dict | None:
    """
    把新版导出的一条站点对象转成站点原始 dict.

    prefix 缺失时回落到 id，两者都没有才算无效；坐标原样透传，
    类型与范围校验统一留给 core/stations.normalize。
    """

    if not isinstance(item, dict):
        skipped.append({"source": f"第 {index} 项", "reason": "不是对象"})
        return None
    name = str(item.get("name") or "").strip()
    prefix = str(item.get("prefix") or item.get("id") or "").strip()
    if not name or not prefix:
        skipped.append({"source": name or f"第 {index} 项", "reason": "缺少名称或前缀"})
        return None
    dimension = _dimension(item.get("dimension"), default_dimension, warnings, name)
    if dimension is None:
        return None
    return {
        "id": prefix,
        "name": name,
        "group": str(item.get("group", "") or ""),
        "prefix": prefix,
        "dimension": dimension,
        "x": item.get("x"),
        "y": item.get("y"),
        "z": item.get("z"),
    }


# ------------------------------ 文本 ------------------------------ #
def _parse_lines(text: str, default_dimension: str) -> dict:
    """
    解析纯文本站点表，一行一个站点.

    支持三种列数（从右往左取，名称里允许有空格）：
    - 7 列：名称 x y z 前缀 分组 维度（本工具导出的格式，分组为空写 "-"）；
    - 6 列：名称 x y z 前缀 维度（旧导出，没有分组）；
    - 5 列及以上：名称 x y z 前缀（没有维度，按前缀线索或默认维度推断）。

    空行与 # / // 开头的行视为注释跳过；坐标不是数字、名称缺失都记 skipped 而不中断。
    """

    stations: list = []
    skipped: list = []
    warnings: list = []

    for number, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        # 注释用整行判断，行内 # 不特殊处理（避免站点名带 # 时被截断）.
        if not line or line.startswith("#") or line.startswith("//"):
            continue

        parts = line.split()
        if len(parts) < 5:
            skipped.append(
                {"source": f"第 {number} 行", "reason": "格式应为「名称 x y z 前缀」"}
            )
            continue

        explicit_dimension = None
        group = ""
        if len(parts) >= 7 and parts[-1] in DIMENSIONS:
            # 导出格式：名称 x y z 前缀 分组 维度（分组为空时写 "-"）
            explicit_dimension = parts[-1]
            raw_group = parts[-2]
            try:
                # 用负数下标从行尾取，名称里有空格也能整体保留.
                z = float(parts[-4])
                y = float(parts[-5])
                x = float(parts[-6])
                prefix = parts[-3]
                name = " ".join(parts[:-6]).strip()
            except ValueError:
                skipped.append({"source": f"第 {number} 行", "reason": "坐标不是数字"})
                continue
            group = "" if raw_group == "-" else raw_group
        elif len(parts) >= 6 and parts[-1] in DIMENSIONS:
            # 兼容旧导出：名称 x y z 前缀 维度（无分组）
            explicit_dimension = parts[-1]
            try:
                z = float(parts[-3])
                y = float(parts[-4])
                x = float(parts[-5])
                prefix = parts[-2]
                name = " ".join(parts[:-5]).strip()
            except ValueError:
                skipped.append({"source": f"第 {number} 行", "reason": "坐标不是数字"})
                continue
        else:
            # 最短格式：名称 x y z 前缀；维度靠默认值或前缀里的维度片段.
            try:
                z = float(parts[-2])
                y = float(parts[-3])
                x = float(parts[-4])
                prefix = parts[-1]
                name = " ".join(parts[:-4]).strip()
            except ValueError:
                skipped.append({"source": f"第 {number} 行", "reason": "坐标不是数字"})
                continue

        if not name:
            skipped.append({"source": f"第 {number} 行", "reason": "缺少站点名称"})
            continue

        # 显式写了维度就信它；否则尝试从前缀里拆出维度（如 nether_wa）.
        if explicit_dimension:
            dimension = explicit_dimension
        else:
            dimension, prefix = _split_dimension(prefix, default_dimension)
        stations.append(
            {
                "id": prefix,
                "name": name,
                "group": group,
                "prefix": prefix,
                "dimension": dimension,
                "x": x,
                "y": y,
                "z": z,
            }
        )

    stations, dropped = _dedupe(stations, warnings)
    return {
        "format": "lines",
        "stations": stations,
        "skipped": skipped + dropped,
        "warnings": warnings,
    }


def _dimension(value, default_dimension: str, warnings: list, name: str) -> str | None:
    """
    归一化维度名：去掉 minecraft: 前缀、展开 nether / end 别名.

    不认识的维度不报错，回落成 default_dimension 并记一条 warning，
    这样旧数据里写错的维度不会挡住整次导入。
    """

    text = str(value or default_dimension).strip()
    if text.startswith("minecraft:"):
        text = text[len("minecraft:"):]
    # 旧配置里常见简写 nether / end，转成规范值.
    aliases = {"nether": "the_nether", "end": "the_end"}
    text = aliases.get(text, text)
    if text not in DIMENSIONS:
        warnings.append(f"「{name}」的维度 {value} 不认识，已按 {default_dimension} 导入")
        return default_dimension
    return text


def _split_dimension(prefix: str, default_dimension: str) -> tuple:
    """
    从前缀里剥离维度片段，返回 (维度, 去掉片段后的前缀).

    例：("nether_wa", "overworld") → ("the_nether", "wa")。
    只有命中表项且剥离后仍有剩余字符时才拆，避免把整个前缀吃成空串。
    """

    lowered = prefix.lower()
    for head, dimension in DIMENSION_PREFIXES:
        if lowered.startswith(head) and len(prefix) > len(head):
            return dimension, prefix[len(head):]
    return default_dimension, prefix


def _dedupe(stations: list, warnings: list) -> tuple:
    """
    按前缀去重，保留第一次出现的站点，返回 (保留列表, 被丢弃的条目).

    Minecraft 里假人靠名字区分，前缀相同就会生成同名假人，所以必须去重；
    被丢弃的条目会同时写进 warnings（人看的提示）与 dropped（结构化结果）。
    """

    seen: dict = {}
    result: list = []
    dropped: list = []
    for station in stations:
        prefix = station["prefix"]
        if prefix in seen:
            warnings.append(f"前缀 {prefix} 重复，已保留「{seen[prefix]}」，跳过「{station['name']}」")
            dropped.append({"source": station["name"], "reason": f"前缀 {prefix} 重复"})
            continue
        seen[prefix] = station["name"]
        result.append(station)
    return result, dropped
