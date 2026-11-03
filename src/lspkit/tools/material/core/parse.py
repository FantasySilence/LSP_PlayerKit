# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 材料清单解析             #
# =================================== #

from __future__ import annotations

import re

from ..constants import MAX_KINDS, MAX_WARNINGS, NAME_TRIM, TRAILING_COUNT

_TRAILING = re.compile(TRAILING_COUNT, re.IGNORECASE)
_SEPARATOR = re.compile(r"[,._]")


def parse_materials(text: str) -> dict:
    """
    把材料清单文本解析成按物品名合并后的条目.
    """

    entries: dict[str, dict] = {}
    warnings: list[dict] = []
    skipped = 0
    truncated = False

    for line_no, raw_line in enumerate(text.replace("\ufeff", "").splitlines(), start=1):

        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue

        match = _TRAILING.search(line)
        name = line[: match.start()].rstrip(NAME_TRIM).strip() if match else ""
        count = int(_SEPARATOR.sub("", match.group("count"))) if match else 0

        if not name or count <= 0:
            skipped += 1
            if len(warnings) < MAX_WARNINGS:
                warnings.append(
                    {"line": line_no, "text": line[:60], "reason": "unparsed"}
                )
            continue

        key = name.lower()
        entry = entries.get(key)
        if entry is not None:
            entry["count"] += count
            continue

        if len(entries) >= MAX_KINDS:
            truncated = True
            break
        entries[key] = {"name": name, "count": count}

    return {
        "entries": list(entries.values()),
        "warnings": warnings,
        "skipped": skipped,
        "truncated": truncated,
    }
