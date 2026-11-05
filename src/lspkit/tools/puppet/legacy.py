# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 旧站点配置导入           #
# =================================== #

from __future__ import annotations

import json

from .constants import DIMENSIONS


def convert(raw: dict) -> dict:
    """
    设置导入的旧格式迁移：假人搬货没有旧版设置文件，原样返回.
    """

    return raw

# ------ 旧 command.txt 的前缀里带维度，导入时顺便拆出来 ------ #
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
    """

    if not isinstance(text, str) or not text.strip():
        raise ValueError("导入内容为空")

    stripped = text.lstrip("\ufeff \t\r\n")
    if stripped.startswith("{") or stripped.startswith("["):
        return _parse_json(stripped, default_dimension)
    return _parse_lines(text, default_dimension)


# ------------------------------ JSON ------------------------------ #
def _parse_json(text: str, default_dimension: str) -> dict:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
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
    if not isinstance(item, dict):
        skipped.append({"source": name, "reason": "站点内容不是对象"})
        return None

    coordinate = item.get("coordinate")
    if not isinstance(coordinate, dict):
        coordinate = {"x": item.get("x"), "y": item.get("y"), "z": item.get("z")}

    dimension = _dimension(item.get("dimension"), default_dimension, warnings, str(name))
    if dimension is None:
        return None

    prefix = str(item.get("prefix") or "").strip()
    if not prefix:
        skipped.append({"source": str(name), "reason": "缺少前缀"})
        return None

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
    stations: list = []
    skipped: list = []
    warnings: list = []

    for number, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
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
    text = str(value or default_dimension).strip()
    if text.startswith("minecraft:"):
        text = text[len("minecraft:"):]
    aliases = {"nether": "the_nether", "end": "the_end"}
    text = aliases.get(text, text)
    if text not in DIMENSIONS:
        warnings.append(f"「{name}」的维度 {value} 不认识，已按 {default_dimension} 导入")
        return default_dimension
    return text


def _split_dimension(prefix: str, default_dimension: str) -> tuple:
    lowered = prefix.lower()
    for head, dimension in DIMENSION_PREFIXES:
        if lowered.startswith(head) and len(prefix) > len(head):
            return dimension, prefix[len(head):]
    return default_dimension, prefix


def _dedupe(stations: list, warnings: list) -> tuple:
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
