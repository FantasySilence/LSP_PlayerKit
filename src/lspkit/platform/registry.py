# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 工具注册表               #
# =================================== #

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from lspkit.errors import AppError
from lspkit.platform.schema import SettingsSchema, get_path, set_path

Handler = Callable[[dict, "Context"], dict]


@dataclass
class ToolManifest:
    id: str
    name_key: str
    icon: str
    order: int
    version: str
    schema: SettingsSchema
    actions: list[dict] = field(default_factory=list)
    columns: list[dict] = field(default_factory=list)
    description_key: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "nameKey": self.name_key,
            "descriptionKey": self.description_key,
            "icon": self.icon,
            "order": self.order,
            "version": self.version,
            "actions": self.actions,
            "columns": self.columns,
            "settingsSchema": self.schema.to_dict(),
        }


@dataclass
class RegisteredTool:
    manifest: ToolManifest
    handlers: dict[str, Handler]
    legacy: Callable[[dict], dict] | None = None


class Context:
    """
    动作执行上下文：给工具读取自己那套设置，不暴露别的工具.
    """

    def __init__(self, runtime, registry: "Registry") -> None:
        self._runtime = runtime
        self._registry = registry

    def settings(self, tool_id: str) -> dict:
        tool = self._registry.get(tool_id)
        schema = tool.manifest.schema
        raw = self._runtime.store.load(tool_id, schema.defaults())
        data: dict = {}
        for f in schema.fields:
            try:
                value = f.coerce(get_path(raw, f.key, f.default))
            except AppError:
                value = f.default
            set_path(data, f.key, value)
        return data

    def save_settings(self, tool_id: str, values: dict) -> dict:
        tool = self._registry.get(tool_id)
        validated = tool.manifest.schema.validate(values)
        self._runtime.store.save(tool_id, validated)
        return validated

    # ------ 工具自有的变长数据（站点、台账等） ------ #
    def doc_load(self, tool_id: str, name: str, default: dict | None = None) -> dict:
        """
        读取工具自有的 JSON 文档（与设置分文件存放，同样享受原子写与备份）.
        """

        self._registry.get(tool_id)
        data = self._runtime.store.load(f"{tool_id}_{name}", default or {})
        return data if isinstance(data, dict) else dict(default or {})

    def doc_save(self, tool_id: str, name: str, data: dict) -> dict:
        """
        写入工具自有的 JSON 文档.
        """

        self._registry.get(tool_id)
        if not isinstance(data, dict):
            raise AppError("INVALID_DATA", "文档内容必须是对象")
        return self._runtime.store.save(f"{tool_id}_{name}", data)


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(
        self,
        manifest: ToolManifest,
        handlers: dict[str, Handler],
        legacy: Callable[[dict], dict] | None = None,
    ) -> None:
        if manifest.id in self._tools:
            raise ValueError(f"tool already registered: {manifest.id}")
        self._tools[manifest.id] = RegisteredTool(manifest, handlers, legacy)

    def get(self, tool_id: str) -> RegisteredTool:
        tool = self._tools.get(tool_id)
        if tool is None:
            raise AppError("UNKNOWN_TOOL", f"未知工具：{tool_id}")
        return tool

    def ids(self) -> list[str]:
        return sorted(self._tools, key=lambda i: self._tools[i].manifest.order)

    def manifests(self) -> list[dict]:
        return [self._tools[i].manifest.to_dict() for i in self.ids()]

    def manifest(self, tool_id: str) -> dict:
        return self.get(tool_id).manifest.to_dict()

    def call(self, tool_id: str, action: str, payload: dict, ctx: Context) -> dict:
        tool = self.get(tool_id)
        handler = tool.handlers.get(action)
        if handler is None:
            raise AppError("UNKNOWN_ACTION", f"工具 {tool_id} 没有动作 {action}")
        return handler(payload, ctx)

    def convert_legacy(self, tool_id: str, raw: dict) -> dict:
        tool = self.get(tool_id)
        if tool.legacy is None:
            return raw
        return tool.legacy(raw)
