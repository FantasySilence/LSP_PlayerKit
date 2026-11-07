# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 请求参数校验             #
# =================================== #
# 本文件职责：把前端传来的弱类型 JSON 参数，校验并转换成后端可用的强类型值。
# 任何不合法输入都抛 AppError（INVALID_PAYLOAD / INVALID_INPUT），由上层包成返回信封。

from __future__ import annotations

from typing import Any

from lspkit.errors import AppError


# ------ 基础类型校验 ------ #
def payload_dict(payload: Any) -> dict:
    """把请求 payload 统一成 dict：None 视为空字典，其它非 dict 类型直接拒绝。"""

    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise AppError("INVALID_PAYLOAD", "请求参数格式错误")
    return payload


def obj(payload: dict, key: str) -> dict:
    """取出一个必填的嵌套对象参数；缺失或类型不是 dict 都抛 INVALID_PAYLOAD。"""

    value = payload.get(key)
    if not isinstance(value, dict):
        raise AppError("INVALID_PAYLOAD", f"缺少参数：{key}")
    return value


def number(
    payload: dict,
    key: str,
    *,
    default: float | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
    label: str | None = None,
) -> float:
    """取一个数值参数并返回 float。

    payload: 参数表；key: 字段名；default: 缺省值（为 None 表示必填）。
    minimum / maximum: 闭区间上下限，越界抛 INVALID_INPUT。
    label: 报错时展示的中文名，缺省时直接用 key。
    """

    name = label or key
    # 字段缺失（或显式传 null）时走默认值；连默认值都没有就说明是必填项
    if key not in payload or payload[key] is None:
        if default is None:
            raise AppError("INVALID_PAYLOAD", f"缺少参数：{name}")
        value = float(default)
    else:
        # 兼容前端把输入框内容直接当字符串传上来，转不成数字才算错误
        try:
            value = float(payload[key])
        except (TypeError, ValueError) as exc:
            raise AppError("INVALID_INPUT", f"「{name}」必须是数字") from exc
    if minimum is not None and value < minimum:
        raise AppError("INVALID_INPUT", f"「{name}」不能小于 {minimum}")
    if maximum is not None and value > maximum:
        raise AppError("INVALID_INPUT", f"「{name}」不能大于 {maximum}")
    return value


def integer(
    payload: dict,
    key: str,
    *,
    default: int | None = None,
    minimum: int | None = None,
    maximum: int | None = None,
    label: str | None = None,
) -> int:
    """取一个整数参数：先按 number() 校验数值与范围，再要求没有小数部分。"""

    value = number(
        payload, key, default=default, minimum=minimum, maximum=maximum, label=label
    )
    # 1e-9 的容差是为了容忍浮点误差（如 12.0000000001），而不是允许传小数
    if abs(value - round(value)) > 1e-9:
        raise AppError("INVALID_INPUT", f"「{label or key}」必须是整数")
    return int(round(value))


def choice(payload: dict, key: str, options: tuple[str, ...], *, default: str | None = None) -> str:
    """取一个枚举参数：值必须落在 options 里，否则抛 INVALID_INPUT。"""

    # 缺省时用 default；default 也不在候选里同样会被下面的判断拦下
    value = payload.get(key, default)
    if value not in options:
        raise AppError("INVALID_INPUT", f"「{key}」取值必须是 {', '.join(options)} 之一")
    return value
