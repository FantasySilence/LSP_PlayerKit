# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 设置字段描述符           #
# =================================== #

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any

from lspkit.errors import AppError


def get_path(data: dict, dotted: str, default: Any = None) -> Any:
    node: Any = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def has_path(data: dict, dotted: str) -> bool:
    node: Any = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


def set_path(data: dict, dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    node = data
    for part in parts[:-1]:
        nxt = node.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            node[part] = nxt
        node = nxt
    node[parts[-1]] = value


@dataclass
class Field:
    key: str  # 支持点号路径，如 flat.xzMotion
    label: str  # i18n key
    type: str = "float"  # int | float | bool | enum | string
    default: Any = 0
    min: float | None = None
    max: float | None = None
    step: float | None = None
    digits: int = 4
    unit: str = ""
    options: list[dict] | None = None
    hint: str = ""

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "type": self.type,
            "default": self.default,
            "min": self.min,
            "max": self.max,
            "step": self.step,
            "digits": self.digits,
            "unit": self.unit,
            "options": self.options,
            "hint": self.hint,
        }

    def coerce(self, value: Any) -> Any:
        try:
            if self.type == "bool":
                if isinstance(value, str):
                    return value.strip().lower() in ("1", "true", "yes", "on")
                return bool(value)
            if self.type == "enum":
                allowed = [opt["value"] for opt in (self.options or [])]
                if value not in allowed:
                    raise ValueError(value)
                return value
            if self.type == "string":
                return str(value)
            number = float(value)
            if self.type == "int":
                if abs(number - round(number)) > 1e-9:
                    raise ValueError(value)
                number = int(round(number))
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                "INVALID_SETTING", f"「{self.label}」取值无效", str(exc)
            ) from exc

        if self.min is not None and number < self.min:
            raise AppError(
                "INVALID_SETTING", f"「{self.label}」不能小于 {self.min}", str(number)
            )
        if self.max is not None and number > self.max:
            raise AppError(
                "INVALID_SETTING", f"「{self.label}」不能大于 {self.max}", str(number)
            )
        return number


@dataclass
class Group:
    id: str
    label: str
    fields: list[Field] = dc_field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "fields": [f.to_dict() for f in self.fields],
        }


@dataclass
class SettingsSchema:
    version: int
    groups: list[Group]

    @property
    def fields(self) -> list[Field]:
        return [f for group in self.groups for f in group.fields]

    def defaults(self) -> dict:
        data: dict = {}
        for f in self.fields:
            set_path(data, f.key, f.default)
        return data

    def validate(self, raw: dict | None) -> dict:
        raw = raw if isinstance(raw, dict) else {}
        data: dict = {}
        for f in self.fields:
            value = get_path(raw, f.key, f.default)
            set_path(data, f.key, f.coerce(value))
        return data

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "groups": [g.to_dict() for g in self.groups],
        }
