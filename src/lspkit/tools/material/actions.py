# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 对外动作                 #
# =================================== #

from __future__ import annotations

from lspkit.errors import AppError

from .constants import MAX_TEXT_LENGTH
from .core.convert import convert
from .core.packing import plan
from .core.parse import parse_materials


def convert_action(payload: dict, ctx) -> dict:
    """
    解析材料清单并换算成潜影盒 / 组 / 个.
    """

    parsed, settings = _read(payload, ctx)
    overrides = _stack_overrides(payload)
    active, ignored = _split(parsed, payload, settings, overrides)
    result = convert(
        active,
        settings["stackSize"],
        settings["shulkerSlots"],
        overrides,
    )
    result["ignoredItems"] = ignored
    result["warnings"] = parsed["warnings"]
    result["skipped"] = parsed["skipped"]
    result["truncated"] = parsed["truncated"]
    return result


def pack_action(payload: dict, ctx) -> dict:
    """
    给出用最少潜影盒装完所有材料的装填方案.
    """

    parsed, settings = _read(payload, ctx)
    overrides = _stack_overrides(payload)
    active, ignored = _split(parsed, payload, settings, overrides)
    result = plan(
        active,
        settings["stackSize"],
        settings["shulkerSlots"],
        overrides,
    )
    result["ignoredItems"] = ignored
    result["warnings"] = parsed["warnings"]
    result["skipped"] = parsed["skipped"]
    result["truncated"] = parsed["truncated"]
    return result


def _split(parsed: dict, payload: dict, settings: dict, overrides: dict) -> tuple[list, list]:
    """
    按「忽略」名单拆成待换算条目与被忽略条目.
    """

    ignore = set(_ignore_names(payload))
    active: list = []
    ignored: list = []
    for entry in parsed["entries"]:
        if entry["name"] in ignore:
            stack = max(1, int(overrides.get(entry["name"], settings["stackSize"])))
            ignored.append(
                {"name": entry["name"], "count": int(entry["count"]), "stack": stack}
            )
        else:
            active.append(entry)
    return active, ignored


def _ignore_names(payload: dict) -> list:
    raw = payload.get("ignore")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise AppError("INVALID_INPUT", "忽略名单格式错误")
    return [str(name) for name in raw]


def _read(payload: dict, ctx) -> tuple[dict, dict]:
    """
    校验请求、解析清单并取回本工具设置.
    """

    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise AppError("INVALID_INPUT", "请先导入材料清单")
    if len(text) > MAX_TEXT_LENGTH:
        raise AppError(
            "INPUT_TOO_LARGE", "材料清单太长，请分批换算", f"{len(text)} 字符"
        )

    settings = ctx.settings("material")
    parsed = parse_materials(text)
    if not parsed["entries"]:
        raise AppError(
            "NO_ENTRIES",
            "没有识别出任何材料条目",
            "请确认导入的是投影模组导出的材料清单 CSV",
        )
    return parsed, settings


def _stack_overrides(payload: dict) -> dict:
    """
    取出「按材料指定堆叠数」的表，只接受 64 / 16 / 1.
    """

    raw = payload.get("stacks")
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise AppError("INVALID_INPUT", "材料堆叠设置格式错误")

    allowed = ("64", "16", "1")
    overrides: dict = {}
    for name, value in raw.items():
        text = str(value).strip()
        if text not in allowed:
            raise AppError(
                "INVALID_INPUT", f"「{name}」的堆叠数只能是 64 / 16 / 1", text
            )
        overrides[str(name)] = text
    return overrides
