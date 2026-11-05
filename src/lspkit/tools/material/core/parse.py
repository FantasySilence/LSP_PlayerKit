# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 材料清单解析             #
# =================================== #

from __future__ import annotations

import csv
import re

from ..constants import MAX_KINDS, MAX_WARNINGS, NAME_TRIM, TRAILING_COUNT

_TRAILING = re.compile(TRAILING_COUNT, re.IGNORECASE)
_SEPARATOR = re.compile(r"[,._\s]")

# 表头识别：名称列与数量列
_NAME_KEYS = {"item", "items", "name", "material", "物品", "名称", "材料"}
_COUNT_KEYS = {"total", "count", "amount", "quantity", "数量", "总数", "总计"}


def _to_int(value: str) -> int:
    """
    把「4,766」这类写法转成整数，无法解析时返回 -1.
    """

    text = _SEPARATOR.sub("", value.strip())
    return int(text) if text.isdigit() else -1


def _find(cells: list[str], keys: set[str]) -> int | None:
    for index, cell in enumerate(cells):
        if cell.strip().lower() in keys:
            return index
    return None


def _split(line: str) -> list[str]:
    try:
        return [cell.strip() for cell in next(csv.reader([line]))]
    except (csv.Error, StopIteration):
        return [line]


def parse_materials(text: str) -> dict:
    """
    解析材料清单，支持带表头的 CSV 与「名称 数量」文本.
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


def parse_sources(sources: list[dict]) -> dict:
    """
    解析多份材料清单，跨清单的同名材料按数量求和.
    """

    merged: dict[str, dict] = {}
    warnings: list[dict] = []
    summary: list[dict] = []
    skipped = 0
    truncated = False

    for source in sources:
        name = str(source.get("name") or "清单")
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
