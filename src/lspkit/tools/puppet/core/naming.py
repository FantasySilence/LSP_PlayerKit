# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 假人名字模板（纯函数）   #
# =================================== #

"""
假人名字的模板校验与渲染。

名字规则分两层：
- 模板层：只认 {origin} / {dest} / {index} 三个占位符，且必须含 {index}，
  否则同一张运单里所有假人会同名，后生成的会顶掉先前的；
- 名字层：渲染结果必须是 3–16 位字母 / 数字 / 下划线（Minecraft 用户名限制）。

默认模板 bot_{origin}_{dest}_{index}，其中 origin / dest 用站点前缀，
前缀过长（>12 位）时拼出来的名字会超长，由 check_name 抛错提醒用户改名。
"""

from __future__ import annotations

import re

from ..constants import PLAYER_NAME_MAX, PLAYER_NAME_MIN

# 模板里允许出现的占位符，顺序影响报错提示里的列举顺序.
PLACEHOLDERS = ("origin", "dest", "index")

# 匹配 {xxx} 形式的占位符，用于挑出不认识的占位符名.
_TOKEN = re.compile(r"\{([A-Za-z_]+)\}")
# Minecraft 用户名允许的字符集：字母、数字、下划线，不允许中文与短横线.
_NAME = re.compile(r"^[A-Za-z0-9_]+$")


def validate_template(template: str) -> str:
    """
    校验命名模板；非法时抛 ValueError（由动作层翻译成 AppError）.

    返回去掉首尾空白后的模板文本，调用方应使用返回值而不是原始入参。
    校验项：非空、占位符可识别、至少含一个占位符、必须含 {index}。
    """

    if not isinstance(template, str) or not template.strip():
        raise ValueError("命名模板不能为空")

    text = template.strip()
    # 未知占位符一次报全，避免用户改一个跑一次.
    unknown = [name for name in _TOKEN.findall(text) if name not in PLACEHOLDERS]
    if unknown:
        raise ValueError(
            "命名模板里有不认识的占位符："
            + "、".join("{" + name + "}" for name in unknown)
            + "；可用 {origin}、{dest}、{index}"
        )
    if "{" not in text:
        raise ValueError("命名模板至少要包含 {index}，否则所有假人会重名")
    # 只认字面量 {index}；写成 {Index} 或 {index:02d} 都会走到这里报错.
    if "{index}" not in text:
        raise ValueError("命名模板必须包含 {index}")
    return text


def render(template: str, origin: str, dest: str, index: int) -> str:
    """
    按模板渲染单个假人名（保留字面量，不自动转义）.

    origin / dest 传的是站点前缀而不是站点全名；index 从 1 开始，
    与运单里 bot 的编号一致。渲染结果不保证合法，需再过 check_name。
    """

    # 先校验再替换：非法模板在这里就抛 ValueError，不会带出半成品名字.
    text = validate_template(template)
    text = text.replace("{origin}", str(origin))
    text = text.replace("{dest}", str(dest))
    text = text.replace("{index}", str(index))
    return text


def check_name(name: str) -> str:
    """
    校验 Minecraft 用户名格式；非法时抛 ValueError.

    只做字符集与长度检查，不查重；同名判重由 plan 层的序号保证。
    返回原名字，方便在表达式里链式调用。
    """

    # 空名 / None 都落到这里：先报字符集错误，比报长度更好懂.
    if not _NAME.match(name or ""):
        raise ValueError(f"假人名「{name}」只能用字母、数字、下划线")
    # 3–16 位是 Minecraft 客户端的硬限制，超出后服务器会拒绝该玩家登录.
    if not PLAYER_NAME_MIN <= len(name) <= PLAYER_NAME_MAX:
        raise ValueError(
            f"假人名「{name}」长度 {len(name)}，Minecraft 要求 "
            f"{PLAYER_NAME_MIN}–{PLAYER_NAME_MAX} 个字符；请缩短站点前缀"
        )
    return name
