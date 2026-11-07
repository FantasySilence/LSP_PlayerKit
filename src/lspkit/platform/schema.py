# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 设置字段描述符           #
# =================================== #
# 本文件职责：声明“一个工具的设置有哪些字段”，并负责默认值、类型转换与范围校验。
# 字段用点号路径（如 flat.xzMotion）描述嵌套结构，前端据此自动生成设置界面。

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any

from lspkit.errors import AppError


# ------ 点号路径读写 ------ #
def get_path(data: dict, dotted: str, default: Any = None) -> Any:
    """按 "a.b.c" 形式的路径取值；中间任一层缺失或不是对象时返回 default。"""

    node: Any = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def has_path(data: dict, dotted: str) -> bool:
    """判断点号路径是否真实存在（即使值为 None 也算存在）。"""

    node: Any = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


def set_path(data: dict, dotted: str, value: Any) -> None:
    """按点号路径写入；中间层不存在或不是对象时自动建空字典，已有内容会被覆盖。"""

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
    """一个设置字段的完整描述：前端据它生成控件，后端据它做类型转换与范围校验。"""

    key: str  # 支持点号路径，如 flat.xzMotion
    label: str  # i18n key
    type: str = "float"  # int | float | bool | enum | string
    default: Any = 0
    # min / max 是闭区间边界；step 是输入框步长；digits 是展示时保留的小数位数
    min: float | None = None
    max: float | None = None
    step: float | None = None
    digits: int = 4
    # 单位只用于界面标注（如 格 / 区块 / gt），不参与计算
    unit: str = ""
    # 仅 type=enum 时使用：每项形如 {"value": 实际值, "label": 显示名}
    options: list[dict] | None = None
    hint: str = ""

    def to_dict(self) -> dict:
        """转成前端可直接消费的 JSON 结构（键名与前端类型定义保持一致）。"""

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
        """把外部值转成本字段声明的类型，并检查 min / max。

        转换失败或越界时抛 AppError（INVALID_SETTING），message 里用中文 label 指路。
        """

        try:
            if self.type == "bool":
                # 字符串按“1/true/yes/on”理解为真，其余一律为假（旧配置可能存成文本）
                if isinstance(value, str):
                    return value.strip().lower() in ("1", "true", "yes", "on")
                return bool(value)
            if self.type == "enum":
                allowed = [opt["value"] for opt in (self.options or [])]
                if value not in allowed:
                    # 旧配置可能把枚举存成数字，这里做一次文本化兜底
                    text = str(value).strip()
                    if text in allowed:
                        return text
                    raise ValueError(value)
                return value
            if self.type in ("string", "path"):
                # path 与 string 一样只做文本处理，路径是否有效由使用方自行检查
                return str(value)
            number = float(value)
            if self.type == "int":
                # 拒绝 1.5 这类真小数，但容忍 3.0000000001 这种浮点误差
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
    """设置界面里的一个分组（通常渲染成一个折叠面板），组内字段按声明顺序显示。"""

    id: str
    label: str
    fields: list[Field] = dc_field(default_factory=list)

    def to_dict(self) -> dict:
        """转成前端结构：分组 id / i18n 标题 / 字段列表。"""

        return {
            "id": self.id,
            "label": self.label,
            "fields": [f.to_dict() for f in self.fields],
        }


@dataclass
class SettingsSchema:
    """一个工具的全部设置：schema 版本号 + 若干分组（每个分组再含若干字段）。"""

    version: int
    groups: list[Group]

    @property
    def fields(self) -> list[Field]:
        """把所有分组的字段摊平成一个列表，顺序就是界面上的显示顺序。"""

        return [f for group in self.groups for f in group.fields]

    def defaults(self) -> dict:
        """生成一份全部取默认值的设置字典（按点号路径展开成嵌套结构）。"""

        data: dict = {}
        for f in self.fields:
            set_path(data, f.key, f.default)
        return data

    def validate(self, raw: dict | None) -> dict:
        """把任意来源的原始设置清洗成合法字典：缺项补默认值，坏值/越界直接抛错。"""

        raw = raw if isinstance(raw, dict) else {}
        data: dict = {}
        for f in self.fields:
            value = get_path(raw, f.key, f.default)
            set_path(data, f.key, f.coerce(value))
        return data

    def to_dict(self) -> dict:
        """导出给前端的完整 schema（版本号 + 分组树）。"""

        return {
            "version": self.version,
            "groups": [g.to_dict() for g in self.groups],
        }
