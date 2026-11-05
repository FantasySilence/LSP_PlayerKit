# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-05                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 方块/物品名称本地化      #
# =================================== #

from __future__ import annotations

from .block_names import BLOCK_NAMES, ITEM_NAMES

_SUPPORTED = ("zh_cn", "zh_tw", "en")
_ALIASES = {
    "zh_cn": "zh_cn",
    "zh_CN": "zh_cn",
    "zh_tw": "zh_tw",
    "zh_TW": "zh_tw",
    "en": "en",
    "en_us": "en",
    "en_US": "en",
}


def normalize_locale(locale: str) -> str:
    """
    把前端语言代码（zh_CN / zh_TW / en）归一化，未知语言回退简体中文.
    """

    return _ALIASES.get(str(locale or "").strip(), "zh_cn")


def item_name(item_id: str, locale: str = "zh_cn") -> str:
    """
    物品 ID 转当前语言下的显示名.

    自定义命名空间的物品没有翻译表，直接显示原 ID。
    """

    key = normalize_locale(locale)
    namespace, _, path = item_id.partition(":")
    if not path:
        namespace, path = "", item_id
    if namespace != "minecraft":
        return item_id
    return ITEM_NAMES[key].get(path) or BLOCK_NAMES[key].get(path) or path
