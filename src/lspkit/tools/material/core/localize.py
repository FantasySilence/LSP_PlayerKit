# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-05                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 方块/物品名称本地化      #
# =================================== #
# 名称数据都在 block_names.py（脚本生成），这里只负责「语言归一化」与「查表顺序」。

from __future__ import annotations

from .block_names import BLOCK_NAMES, ITEM_NAMES

# ------ 语言代码 ------ #
# 对外只认三种语言：简体中文 / 繁体中文 / 英文；其余写法都是别名。
# _SUPPORTED 只用于声明支持范围，实际归一化查 _ALIASES（两边要一起改）。
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

# ------ 查询 ------ #


def normalize_locale(locale: str) -> str:
    """
    把前端语言代码（zh_CN / zh_TW / en）归一化，未知语言回退简体中文.

    回退是「语言」这一层的兜底：不认识的语言一律按 zh_cn 处理，
    这样即使前端传入空串或新语言代码，界面也不会出现未翻译的键名。
    """

    return _ALIASES.get(str(locale or "").strip(), "zh_cn")


def item_name(item_id: str, locale: str = "zh_cn") -> str:
    """
    物品 ID 转当前语言下的显示名.

    查找顺序（逐级回退，前一级命中就不再往下走）：
    1. 先归一化语言，未知语言回退 zh_cn；
    2. 去掉 minecraft: 命名空间，取得物品路径；没有命名空间时整串都当路径；
    3. 非 minecraft 命名空间（模组 / 自定义方块）没有翻译表，直接显示原 ID；
    4. 先查 ITEM_NAMES（桶、种子、红石粉等只在物品表里的条目），
       再查 BLOCK_NAMES（方块与物品同名的条目都在这里）；
    5. 两级都查不到时回退物品路径本身（英文 ID），保证界面上总有可显示的名字。
    """

    key = normalize_locale(locale)
    namespace, _, path = item_id.partition(":")
    if not path:
        namespace, path = "", item_id
    if namespace != "minecraft":
        return item_id
    return ITEM_NAMES[key].get(path) or BLOCK_NAMES[key].get(path) or path
