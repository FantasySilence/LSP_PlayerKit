# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 站点数据校验（纯函数）   #
# =================================== #

from __future__ import annotations

import re

from ..constants import DIMENSIONS, GROUP_MAX, MAX_STATIONS, NOTE_MAX, PREFIX_MAX

PREFIX_RE = re.compile(r"^[A-Za-z0-9_]+$")
ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
# 分组 tag 会出现在下拉框和文本导出里，不允许空白，避免解析歧义
GROUP_RE = re.compile(r"^[^\s]+$")

WORLD_LIMIT = 30_000_000
Y_LIMIT = 2048


def _coord(value, label: str, limit: int) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"「{label}」必须是数字") from None
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"「{label}」必须是有限数字")
    if abs(number) > limit:
        raise ValueError(f"「{label}」超出范围（±{limit}）")
    return number


def normalize(station: dict) -> dict:
    """
    把一份站点数据规整成标准结构；非法时抛 ValueError.
    """

    if not isinstance(station, dict):
        raise ValueError("站点数据必须是对象")

    name = str(station.get("name", "")).strip()
    if not name:
        raise ValueError("站点名称不能为空")

    group = str(station.get("group", "") or "").strip()
    if group and (not GROUP_RE.match(group) or len(group) > GROUP_MAX):
        raise ValueError(
            f"站点「{name}」的分组 tag 不能包含空格，且不超过 {GROUP_MAX} 个字符"
        )

    # 兼容旧数据：名字里带「工业区·地点」时自动拆成分组 + 短名称
    if not group and "·" in name:
        head, tail = name.split("·", 1)
        head, tail = head.strip(), tail.strip()
        if head and tail and GROUP_RE.match(head) and len(head) <= GROUP_MAX:
            group, name = head, tail

    if len(name) > 64:
        raise ValueError("站点名称不能超过 64 个字符")

    prefix = str(station.get("prefix", "")).strip()
    if not PREFIX_RE.match(prefix):
        raise ValueError(f"站点「{name}」的前缀只能用字母、数字、下划线")
    if len(prefix) > PREFIX_MAX:
        raise ValueError(f"站点「{name}」的前缀不能超过 {PREFIX_MAX} 个字符")

    station_id = str(station.get("id") or prefix).strip()
    if not ID_RE.match(station_id) or len(station_id) > 32:
        raise ValueError(f"站点「{name}」的 id 只能用字母、数字、下划线、短横线")

    dimension = str(station.get("dimension", "")).strip()
    if dimension not in DIMENSIONS:
        raise ValueError(f"站点「{name}」的维度必须是 {' / '.join(DIMENSIONS)} 之一")

    return {
        "id": station_id,
        "name": name,
        "group": group,
        "prefix": prefix,
        "dimension": dimension,
        "x": _coord(station.get("x"), f"{name} 的 X", WORLD_LIMIT),
        "y": _coord(station.get("y"), f"{name} 的 Y", Y_LIMIT),
        "z": _coord(station.get("z"), f"{name} 的 Z", WORLD_LIMIT),
        "note": str(station.get("note", "") or "").strip()[:NOTE_MAX],
    }


def normalize_all(stations) -> list:
    if not isinstance(stations, (list, tuple)):
        raise ValueError("站点列表格式错误")
    result = [normalize(item) for item in stations]
    _check_unique(result)
    if len(result) > MAX_STATIONS:
        raise ValueError(f"站点最多 {MAX_STATIONS} 个")
    return result


def _check_unique(stations: list) -> None:
    seen_id: dict = {}
    seen_prefix: dict = {}
    for station in stations:
        if station["id"] in seen_id:
            raise ValueError(f"站点 id 重复：{station['id']}")
        if station["prefix"] in seen_prefix:
            raise ValueError(
                f"站点前缀重复：「{seen_prefix[station['prefix']]}」与「{station['name']}」"
                f" 都用了 {station['prefix']}"
            )
        seen_id[station["id"]] = station["name"]
        seen_prefix[station["prefix"]] = station["name"]


def find(stations, station_id: str):
    for station in stations:
        if station["id"] == station_id:
            return station
    return None


def upsert(stations: list, station: dict) -> tuple:
    """
    新增或更新站点（按 id 匹配），返回 (新列表, 是否新增).
    """

    item = normalize(station)
    result = [dict(existing) for existing in stations]
    for index, existing in enumerate(result):
        if existing["id"] == item["id"]:
            result[index] = item
            _check_unique(result)
            return result, False
    result.append(item)
    _check_unique(result)
    if len(result) > MAX_STATIONS:
        raise ValueError(f"站点最多 {MAX_STATIONS} 个")
    return result, True


def remove(stations: list, station_id: str) -> list:
    result = [dict(item) for item in stations if item["id"] != station_id]
    if len(result) == len(stations):
        raise ValueError(f"没有找到站点：{station_id}")
    return result


def merge(stations: list, incoming: list) -> tuple:
    """
    合并导入的站点：按 id / 前缀匹配，已存在则覆盖坐标与名称.

    返回 (新列表, 统计)，统计含 added / updated / duplicated.
    """

    result = [dict(item) for item in stations]
    added = updated = duplicated = 0
    for raw in incoming:
        item = normalize(raw)
        target = None
        for candidate in result:
            if candidate["id"] == item["id"] or candidate["prefix"] == item["prefix"]:
                target = candidate
                break
        if target is None:
            result.append(item)
            added += 1
            continue
        if target == item:
            duplicated += 1
            continue
        target.update(item)
        updated += 1
    if len(result) > MAX_STATIONS:
        raise ValueError(f"合并后站点超过 {MAX_STATIONS} 个")
    _check_unique(result)
    return result, {"added": added, "updated": updated, "duplicated": duplicated}
