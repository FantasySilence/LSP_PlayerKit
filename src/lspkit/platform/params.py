# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 请求参数校验             #
# =================================== #

from __future__ import annotations

from typing import Any

from lspkit.errors import AppError


def payload_dict(payload: Any) -> dict:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise AppError("INVALID_PAYLOAD", "请求参数格式错误")
    return payload


def obj(payload: dict, key: str) -> dict:
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
    name = label or key
    if key not in payload or payload[key] is None:
        if default is None:
            raise AppError("INVALID_PAYLOAD", f"缺少参数：{name}")
        value = float(default)
    else:
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
    value = number(
        payload, key, default=default, minimum=minimum, maximum=maximum, label=label
    )
    if abs(value - round(value)) > 1e-9:
        raise AppError("INVALID_INPUT", f"「{label or key}」必须是整数")
    return int(round(value))


def choice(payload: dict, key: str, options: tuple[str, ...], *, default: str | None = None) -> str:
    value = payload.get(key, default)
    if value not in options:
        raise AppError("INVALID_INPUT", f"「{key}」取值必须是 {', '.join(options)} 之一")
    return value
