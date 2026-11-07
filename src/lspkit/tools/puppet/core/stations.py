# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 站点数据校验（纯函数）   #
# =================================== #

"""
站点数据的校验与增删合并。

一个站点在存储里长这样（键名前后端共用，不要随意改）：
    id        内部主键，字母 / 数字 / 下划线 / 短横线，≤32 位，缺省等于 prefix
    name      显示名，≤64 字；旧数据「工业区·地点」会自动拆成 group + name
    group     分组 tag，如「工业区」，不允许空白，≤32 字
    prefix    站点前缀，拼进假人名，只能用字母 / 数字 / 下划线，≤12 位
    dimension overworld / the_nether / the_end 三选一
    x, y, z   坐标，x/z 限 ±30,000,000（世界边界），y 限 ±2048
    note      备注，纯展示，超出 60 字截断而不是报错

去重口径：同一份数据里 id 与 prefix 都必须唯一（_check_unique），
因为 id 用来定位站点、prefix 用来生成假人名，两者撞了都会出错。
"""

from __future__ import annotations

import re

from ..constants import DIMENSIONS, GROUP_MAX, MAX_STATIONS, NOTE_MAX, PREFIX_MAX

PREFIX_RE = re.compile(r"^[A-Za-z0-9_]+$")
# id 比 prefix 宽松：允许短横线，方便旧数据直接拿 slug 当 id.
ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
# 分组 tag 会出现在下拉框和文本导出里，不允许空白，避免解析歧义
GROUP_RE = re.compile(r"^[^\s]+$")

# 世界边界 ±30,000,000；Y 轴取 ±2048，比实际建筑高度宽松，只为拦住手滑输错.
WORLD_LIMIT = 30_000_000
Y_LIMIT = 2048


def _coord(value, label: str, limit: int) -> float:
    """
    把坐标规整成 float，并拦住非数字 / NaN / 无穷 / 越界.

    label 用于拼报错文案（如「仓库 的 X」），limit 是该轴允许的绝对值。
    """

    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"「{label}」必须是数字") from None
    # NaN 不等于自身，用这个特性单独判掉；inf 比较也要显式拦，否则会写进命令.
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"「{label}」必须是有限数字")
    if abs(number) > limit:
        raise ValueError(f"「{label}」超出范围（±{limit}）")
    return number


def normalize(station: dict) -> dict:
    """
    把一份站点数据规整成标准结构；非法时抛 ValueError.

    入参可以是半成品（缺 note、缺 id、坐标是字符串），返回的 dict 键恒定，
    调用方可以放心按固定键名取值。校验顺序与报错文案对用户可见，改动需谨慎。
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
    # 只有在没显式给 group、且中点两侧都非空、前半段能当合法 tag 时才拆；
    # 拆完 name 变短，后面的长度校验针对的是新名字.
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
    # 前缀会拼进假人名，太长的话 bot_{origin}_{dest}_{index} 会超过 16 位.
    if len(prefix) > PREFIX_MAX:
        raise ValueError(f"站点「{name}」的前缀不能超过 {PREFIX_MAX} 个字符")

    # id 缺省时直接沿用 prefix：新建站点不必让用户再想一个 id.
    station_id = str(station.get("id") or prefix).strip()
    if not ID_RE.match(station_id) or len(station_id) > 32:
        raise ValueError(f"站点「{name}」的 id 只能用字母、数字、下划线、短横线")

    # 维度必须是三个合法值之一；不做别名转换（别名在 legacy 导入时已归一）.
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
        # 备注只截断不报错：用户写长了不该挡保存.
        "note": str(station.get("note", "") or "").strip()[:NOTE_MAX],
    }


def normalize_all(stations) -> list:
    """
    批量规整站点，并做唯一性与数量校验.

    出错时整批拒绝（不做部分保留），避免只导入一半造成数据不一致。
    """

    if not isinstance(stations, (list, tuple)):
        raise ValueError("站点列表格式错误")
    result = [normalize(item) for item in stations]
    _check_unique(result)
    if len(result) > MAX_STATIONS:
        raise ValueError(f"站点最多 {MAX_STATIONS} 个")
    return result


def _check_unique(stations: list) -> None:
    """
    检查 id 与 prefix 是否重复；重复时抛 ValueError 并带上冲突双方的名字.

    保存、合并、批量导入都要过这一关，是站点表的最后一道闸。
    """

    seen_id: dict = {}
    seen_prefix: dict = {}
    for station in stations:
        if station["id"] in seen_id:
            raise ValueError(f"站点 id 重复：{station['id']}")
        # 前缀撞了会让两个站点生成同名假人，所以也要拦.
        if station["prefix"] in seen_prefix:
            raise ValueError(
                f"站点前缀重复：「{seen_prefix[station['prefix']]}」与「{station['name']}」"
                f" 都用了 {station['prefix']}"
            )
        seen_id[station["id"]] = station["name"]
        seen_prefix[station["prefix"]] = station["name"]


def find(stations, station_id: str):
    """
    按 id 线性查找站点；找不到返回 None（不抛错，由调用方决定报什么）.
    """

    for station in stations:
        if station["id"] == station_id:
            return station
    return None


def upsert(stations: list, station: dict) -> tuple:
    """
    新增或更新站点（按 id 匹配），返回 (新列表, 是否新增).

    不修改入参列表与其中的 dict（先浅拷贝再改），失败时原数据保持可用。
    """

    item = normalize(station)
    result = [dict(existing) for existing in stations]
    for index, existing in enumerate(result):
        if existing["id"] == item["id"]:
            result[index] = item
            # 改完 id 没变，但 prefix 可能被改去撞别人，所以仍要整体复查.
            _check_unique(result)
            return result, False
    result.append(item)
    _check_unique(result)
    # 新增才需要查上限；更新不会让条数变多.
    if len(result) > MAX_STATIONS:
        raise ValueError(f"站点最多 {MAX_STATIONS} 个")
    return result, True


def remove(stations: list, station_id: str) -> list:
    """
    按 id 删除站点，返回新列表；没有该 id 时抛 ValueError.

    删除不会回收引用：已生成的运单/台账里仍保留当时的站点快照。
    """

    result = [dict(item) for item in stations if item["id"] != station_id]
    if len(result) == len(stations):
        raise ValueError(f"没有找到站点：{station_id}")
    return result


def merge(stations: list, incoming: list) -> tuple:
    """
    合并导入的站点：按 id / 前缀匹配，已存在则覆盖坐标与名称.

    返回 (新列表, 统计)，统计含 added / updated / duplicated.
    匹配顺序是「先 id 后 prefix」：id 相同视为同一站；id 不同但 prefix 相同
    也按同一站处理并合并，否则导入后会因前缀冲突而无法保存。
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
        # 内容完全一致算「重复」，只计数不改数据，方便前端提示「无变化」.
        if target == item:
            duplicated += 1
            continue
        target.update(item)
        updated += 1
    if len(result) > MAX_STATIONS:
        raise ValueError(f"合并后站点超过 {MAX_STATIONS} 个")
    _check_unique(result)
    return result, {"added": added, "updated": updated, "duplicated": duplicated}
