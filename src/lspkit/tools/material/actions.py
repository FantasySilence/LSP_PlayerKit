# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 对外动作                 #
# =================================== #

# 本文件是工具与前端之间的边界：只做参数校验、忽略名单拆分、结果装配，
# 具体换算与装箱都下沉到 core/（纯函数，便于单独测试）。
# 出错一律抛 AppError(code, 用户可读消息, 细节)，由 api 层转成前端 toast。

from __future__ import annotations

from lspkit.errors import AppError

from .constants import MAX_TEXT_LENGTH
from .core.convert import convert
from .core.packing import plan
from .core.parse import parse_materials, parse_sources

# ------ 动作处理 ------ #


def convert_action(payload: dict, ctx) -> dict:
    """
    解析材料清单并换算成潜影盒 / 组 / 个.

    动作 id 为 convert，返回值中 items 直接作为结果表格的行：
    每行含 name（材料名）、stack（堆叠数）、count（需求数量）、
    shulkers（整盒数）/ stacks（整组数）/ items（零散个数）。
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
    result["sources"] = parsed.get("sources", [])
    return result


def pack_action(payload: dict, ctx) -> dict:
    """
    给出用最少潜影盒装完所有材料的装填方案.

    与 convert_action 共享解析和拆分流程，差别只在最后调用 core.packing.plan：
    它把每种材料的数量折成占用格数，再逐盒装满，得到盒数最少的分盒方案。
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
    result["sources"] = parsed.get("sources", [])
    return result


# ------ 参数处理 ------ #


def _split(parsed: dict, payload: dict, settings: dict, overrides: dict) -> tuple[list, list]:
    """
    按「忽略」名单拆成待换算条目与被忽略条目.

    被忽略的材料不参与换算 / 装箱，但仍按原始数量回传给界面单独展示，
    因此这里顺手算好它的堆叠数，保证 ignoredItems 的字段与结果行一致。
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
    """
    取出忽略名单（材料显示名的列表），未提供时视为不忽略任何材料.
    """

    raw = payload.get("ignore")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise AppError("INVALID_INPUT", "忽略名单格式错误")
    return [str(name) for name in raw]


def _read(payload: dict, ctx) -> tuple[dict, dict]:
    """
    校验请求、解析清单并取回本工具设置.

    sources（多份清单，可含已解析好的 litematic 条目）优先于 text（单份文本）；
    locale 决定材料显示名语言。解析结果为空时直接报 NO_ENTRIES，
    由前端提示「导入的是投影模组导出的材料清单」。
    """

    raw_sources = payload.get("sources")
    if raw_sources is None:
        raw_sources = payload.get("texts")
    locale = payload.get("locale")
    locale = locale if isinstance(locale, str) else "zh_cn"
    if raw_sources is not None:
        parsed = parse_sources(_normalize_sources(raw_sources), locale)
    else:
        parsed = parse_materials(_normalize_text(payload.get("text")))

    if not parsed["entries"]:
        raise AppError(
            "NO_ENTRIES",
            "没有识别出任何材料条目",
            "请确认导入的是投影模组导出的材料清单 CSV",
        )
    return parsed, ctx.settings("material")


def _normalize_text(text) -> str:
    """
    校验单份清单的文本.

    长度上限是字符数（不是字节数）：中英混排时按字符计更接近用户直觉。
    """

    if not isinstance(text, str) or not text.strip():
        raise AppError("INVALID_INPUT", "请先导入材料清单")
    if len(text) > MAX_TEXT_LENGTH:
        raise AppError(
            "INPUT_TOO_LARGE", "材料清单太长，请分批换算", f"{len(text)} 字符"
        )
    return text


def _normalize_sources(raw) -> list[dict]:
    """
    校验多份清单的请求体，长度上限按总和计算.

    每个来源二选一：
    - entries：已解析好的条目（.litematic 由 api 层解析后直接传来），跳过长度统计；
    - text：原始文本（CSV / 纯文本），按字符计入总长度。
    空条目与空白文本会被静默跳过，全部无效时才报错。
    """

    if not isinstance(raw, list) or not raw:
        raise AppError("INVALID_INPUT", "请先导入材料清单")

    sources: list[dict] = []
    total = 0
    for item in raw:
        if not isinstance(item, dict):
            raise AppError("INVALID_INPUT", "材料清单格式错误")

        name = str(item.get("name") or "清单")
        entries = item.get("entries")
        if entries is not None:
            if not isinstance(entries, list) or not entries:
                continue
            sources.append({"name": name, "entries": entries})
            continue

        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        total += len(text)
        if total > MAX_TEXT_LENGTH:
            raise AppError(
                "INPUT_TOO_LARGE", "材料清单太长，请分批换算", f"{total} 字符"
            )
        sources.append({"name": name, "text": text})

    if not sources:
        raise AppError("INVALID_INPUT", "请先导入材料清单")
    return sources


def _stack_overrides(payload: dict) -> dict:
    """
    取出「按材料指定堆叠数」的表，只接受 64 / 16 / 1.

    键是材料的显示名（与清单里的名字完全一致才生效），值是堆叠数（个/组）。
    这里刻意保持字符串，不在边界处转 int，转换统一由 core 里的 int() 完成。
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
