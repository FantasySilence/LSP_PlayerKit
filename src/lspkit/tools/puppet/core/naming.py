# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 假人名字模板（纯函数）   #
# =================================== #

from __future__ import annotations

import re

from ..constants import PLAYER_NAME_MAX, PLAYER_NAME_MIN

PLACEHOLDERS = ("origin", "dest", "index")

_TOKEN = re.compile(r"\{([A-Za-z_]+)\}")
_NAME = re.compile(r"^[A-Za-z0-9_]+$")


def validate_template(template: str) -> str:
    """
    校验命名模板；非法时抛 ValueError（由动作层翻译成 AppError）.
    """

    if not isinstance(template, str) or not template.strip():
        raise ValueError("命名模板不能为空")

    text = template.strip()
    unknown = [name for name in _TOKEN.findall(text) if name not in PLACEHOLDERS]
    if unknown:
        raise ValueError(
            "命名模板里有不认识的占位符："
            + "、".join("{" + name + "}" for name in unknown)
            + "；可用 {origin}、{dest}、{index}"
        )
    if "{" not in text:
        raise ValueError("命名模板至少要包含 {index}，否则所有假人会重名")
    if "{index}" not in text:
        raise ValueError("命名模板必须包含 {index}")
    return text


def render(template: str, origin: str, dest: str, index: int) -> str:
    """
    按模板渲染单个假人名（保留字面量，不自动转义）.
    """

    text = validate_template(template)
    text = text.replace("{origin}", str(origin))
    text = text.replace("{dest}", str(dest))
    text = text.replace("{index}", str(index))
    return text


def check_name(name: str) -> str:
    """
    校验 Minecraft 用户名格式；非法时抛 ValueError.
    """

    if not _NAME.match(name or ""):
        raise ValueError(f"假人名「{name}」只能用字母、数字、下划线")
    if not PLAYER_NAME_MIN <= len(name) <= PLAYER_NAME_MAX:
        raise ValueError(
            f"假人名「{name}」长度 {len(name)}，Minecraft 要求 "
            f"{PLAYER_NAME_MIN}–{PLAYER_NAME_MAX} 个字符；请缩短站点前缀"
        )
    return name
