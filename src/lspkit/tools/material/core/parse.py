# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 材料清单解析             #
# =================================== #
# 纯函数：把文本 / 已解析条目统一整理成
# {"entries": [{name, count}], "warnings": [...], "skipped": n, "truncated": bool}。
# 三种入口的差异只在「名字从哪来」，最终都走同一套同名单合并规则。

from __future__ import annotations

import csv
import re

from ..constants import MAX_KINDS, MAX_WARNINGS, NAME_TRIM, TRAILING_COUNT
from .localize import item_name

_TRAILING = re.compile(TRAILING_COUNT, re.IGNORECASE)
# 数字里的分隔符（4,766 / 4.766 / 4 766 都能读成 4766）
_SEPARATOR = re.compile(r"[,._\s]")

# ------ 表头识别 ------ #
# 表头识别：名称列与数量列；匹配时忽略大小写与首尾空白。
# Litematica 导出的材料清单 CSV 表头是 Item / Total，所以 "item" 与 "total" 必须在内。
_NAME_KEYS = {"item", "items", "name", "material", "物品", "名称", "材料"}
_COUNT_KEYS = {"total", "count", "amount", "quantity", "数量", "总数", "总计"}

# ------ 基础工具 ------ #


def _to_int(value: str) -> int:
    """
    把「4,766」这类写法转成整数，无法解析时返回 -1.

    返回 -1 而不是抛异常，是为了让解析循环把该行计入 skipped 并继续往下读。
    """

    text = _SEPARATOR.sub("", value.strip())
    return int(text) if text.isdigit() else -1


def _find(cells: list[str], keys: set[str]) -> int | None:
    """
    在一行单元格里找出表头关键字所在列号，找不到返回 None.
    """

    for index, cell in enumerate(cells):
        if cell.strip().lower() in keys:
            return index
    return None


def _split(line: str) -> list[str]:
    """
    按 CSV 规则切一行（支持引号内的逗号），失败时整行当成一列.
    """

    try:
        return [cell.strip() for cell in next(csv.reader([line]))]
    except (csv.Error, StopIteration):
        return [line]


# ------ 文本清单 ------ #


def parse_materials(text: str) -> dict:
    """
    解析材料清单，支持带表头的 CSV 与「名称 数量」文本.

    解析规则：
    1. 逐行处理，去掉 BOM；空行、# 与 // 开头的注释行直接跳过；
    2. 首个非空行先尝试当表头：同时命中名称列（Item 等）与数量列（Total 等）
       才认作表头，记下两列下标并跳过该行；否则按普通数据行继续解析；
    3. 有表头时按列取单元格；没有表头时用行尾数量正则从右往左切
       （「石头 1728」「1,728 个」都支持），名字两侧的引号与分隔符会被去掉；
    4. 名称原样保留，不统一大小写、不翻译、不裁剪内部空白；
    5. 只有完全同名的条目才合并数量（词典按名索引），保证「红石」与「红石粉」
       这类不同写法不会被误合并；
    6. 数量为 0 的行计入 skipped；无法解析的行最多记 MAX_WARNINGS 条提示；
    7. 材料超过 MAX_KINDS 种时停止解析并置 truncated，只保留先出现的种类。
    """

    entries: dict[str, dict] = {}
    warnings: list[dict] = []
    skipped = 0
    truncated = False
    name_index: int | None = None
    count_index: int | None = None
    header_done = False

    for line_no, raw_line in enumerate(text.replace("\ufeff", "").splitlines(), start=1):

        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue

        cells = _split(line)

        # 首个非空行若是表头，记下名称列与数量列
        if not header_done:
            header_done = True
            found_name = _find(cells, _NAME_KEYS)
            found_count = _find(cells, _COUNT_KEYS)
            if found_name is not None and found_count is not None:
                name_index, count_index = found_name, found_count
                continue

        name = ""
        count = -1

        if name_index is not None and count_index is not None:
            if len(cells) > max(name_index, count_index):
                name = cells[name_index]
                count = _to_int(cells[count_index])
        else:
            matched = _TRAILING.search(line)
            if matched:
                name = line[: matched.start()].rstrip(NAME_TRIM).strip()
                # 名字可能被 CSV 引号包起来，成对剥掉一层
                if len(name) >= 2 and name[0] == '"' and name[-1] == '"':
                    name = name[1:-1].strip()
                count = _to_int(matched.group("count"))

        if not name or count < 0:
            skipped += 1
            if len(warnings) < MAX_WARNINGS:
                warnings.append(
                    {"line": line_no, "text": line[:60], "reason": "unparsed"}
                )
            continue
        if count == 0:
            skipped += 1
            continue

        # 名称保持原样，仅在完全同名时合并
        if name in entries:
            entries[name]["count"] += count
            continue

        if len(entries) >= MAX_KINDS:
            truncated = True
            break
        entries[name] = {"name": name, "count": count}

    return {
        "entries": list(entries.values()),
        "warnings": warnings,
        "skipped": skipped,
        "truncated": truncated,
    }


# ------ 已解析条目 ------ #


def parse_entries(raw: list, locale: str = "zh_cn") -> dict:
    """
    校验并整理已经解析好的条目（如 .litematic 统计结果）.

    带 id 的条目按当前语言重新取名，保证切换语言后材料名跟着变；
    没有 id 的条目沿用传入的 name。规则与文本解析一致：
    名称原样保留、完全同名才合并、数量非正整数记为 skipped。
    """

    entries: dict[str, dict] = {}
    skipped = 0
    truncated = False

    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            skipped += 1
            continue

        item_id = item.get("id")
        if isinstance(item_id, str) and item_id.strip():
            name = item_name(item_id.strip(), locale)
        else:
            name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            skipped += 1
            continue
        try:
            count = int(item.get("count"))
        except (TypeError, ValueError):
            skipped += 1
            continue
        if count <= 0:
            skipped += 1
            continue

        key = name.strip()
        if key in entries:
            entries[key]["count"] += count
        elif len(entries) >= MAX_KINDS:
            truncated = True
        else:
            entries[key] = {"name": key, "count": count}

    return {
        "entries": list(entries.values()),
        "warnings": [],
        "skipped": skipped,
        "truncated": truncated,
    }


# ------ 多份清单 ------ #


def parse_sources(sources: list[dict], locale: str = "zh_cn") -> dict:
    """
    解析多份材料清单，跨清单的同名材料按数量求和.

    每个来源要么是已解析条目（entries，来自 .litematic），
    要么是原始文本（text，来自 CSV / 纯文本）；两种来源可以混在一起导入。
    返回的 sources 是逐份清单的概况（种数 / 总数），供界面显示「从哪几份清单来」。
    """

    merged: dict[str, dict] = {}
    warnings: list[dict] = []
    summary: list[dict] = []
    skipped = 0
    truncated = False

    for source in sources:
        name = str(source.get("name") or "清单")
        if source.get("entries") is not None:
            parsed = parse_entries(source.get("entries"), locale)
        else:
            parsed = parse_materials(source.get("text") or "")

        kinds = 0
        items = 0
        for entry in parsed["entries"]:
            kinds += 1
            items += int(entry["count"])
            if entry["name"] in merged:
                merged[entry["name"]]["count"] += int(entry["count"])
            elif len(merged) >= MAX_KINDS:
                truncated = True
            else:
                merged[entry["name"]] = {
                    "name": entry["name"],
                    "count": int(entry["count"]),
                }

        skipped += int(parsed["skipped"])
        truncated = truncated or bool(parsed["truncated"])
        # 提示里带上来源名，方便用户定位是哪个文件的行没读懂
        for warning in parsed["warnings"]:
            if len(warnings) < MAX_WARNINGS:
                warnings.append({**warning, "source": name})

        summary.append({"name": name, "kinds": kinds, "items": items})

    return {
        "entries": list(merged.values()),
        "warnings": warnings,
        "skipped": skipped,
        "truncated": truncated,
        "sources": summary,
    }
