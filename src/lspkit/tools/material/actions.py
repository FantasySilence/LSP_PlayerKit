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
from .core.parse import parse_materials


def convert_action(payload: dict, ctx) -> dict:
    """
    解析材料清单并换算成潜影盒 / 组 / 个.
    """

    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise AppError("INVALID_INPUT", "请先粘贴或导入材料清单")
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
            "每行写成「物品名 数量」，例如 minecraft:stone 1728",
        )

    result = convert(
        parsed["entries"], settings["stackSize"], settings["shulkerSlots"]
    )
    result["warnings"] = parsed["warnings"]
    result["skipped"] = parsed["skipped"]
    result["truncated"] = parsed["truncated"]
    return result
