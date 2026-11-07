# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 工具注册表               #
# =================================== #
# 本文件职责：维护“有哪些工具、每个工具能做哪些动作、设置长什么样”的注册表。
# 上层（api.py）不认识任何具体工具，只在这里按 id 查表并派发动作。

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from lspkit.errors import AppError
from lspkit.platform.schema import SettingsSchema, get_path, set_path

# 动作处理函数的签名：入参是 (payload 参数表, Context 上下文)，返回可 JSON 序列化的 dict
Handler = Callable[[dict, "Context"], dict]


@dataclass
class ToolManifest:
    """一个工具的静态描述：身份信息 + 设置 schema + 动作清单 + 结果表格列定义。"""

    id: str
    name_key: str
    icon: str
    order: int
    version: str
    schema: SettingsSchema
    # actions 是前端可调用的动作（id + 词条），columns 是结果表格的列定义
    actions: list[dict] = field(default_factory=list)
    columns: list[dict] = field(default_factory=list)
    description_key: str = ""

    def to_dict(self) -> dict:
        """转成前端消费的结构：键名统一成 camelCase，设置部分展开成完整 schema。"""

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
    """注册表里真正保存的一条记录：描述 + 动作处理函数表 + 旧版配置转换器。

    handlers 的键是动作名（与 manifest.actions 对应）；legacy 为 None 表示没有历史格式要迁移。
    """

    manifest: ToolManifest
    handlers: dict[str, Handler]
    legacy: Callable[[dict], dict] | None = None


class Context:
    """
    动作执行上下文：给工具读取自己那套设置，不暴露别的工具.
    """

    def __init__(self, runtime, registry: "Registry") -> None:
        """runtime 提供 store 等运行时服务；registry 用来反查工具及其 schema。"""

        self._runtime = runtime
        self._registry = registry

    def settings(self, tool_id: str) -> dict:
        """读取某工具的设置并逐字段清洗，返回嵌套 dict（缺项补默认值、坏值退回默认值）。"""

        tool = self._registry.get(tool_id)
        schema = tool.manifest.schema
        # 以默认值作为兜底读入：配置文件里缺失的键也能取到值
        raw = self._runtime.store.load(tool_id, schema.defaults())
        data: dict = {}
        for f in schema.fields:
            try:
                value = f.coerce(get_path(raw, f.key, f.default))
            except AppError:
                # 单个字段坏掉只影响它自己，界面仍能正常打开
                value = f.default
            set_path(data, f.key, value)
        return data

    def save_settings(self, tool_id: str, values: dict) -> dict:
        """校验并保存某工具的设置，返回清洗后的结果（前端用它刷新表单）。"""

        tool = self._registry.get(tool_id)
        validated = tool.manifest.schema.validate(values)
        self._runtime.store.save(tool_id, validated)
        return validated

    # ------ 工具自有的变长数据（站点、台账等） ------ #
    def doc_load(self, tool_id: str, name: str, default: dict | None = None) -> dict:
        """
        读取工具自有的 JSON 文档（与设置分文件存放，同样享受原子写与备份）.
        """

        # 先确认工具 id 有效（不存在会抛 UNKNOWN_TOOL），避免给不存在的工具写文件
        self._registry.get(tool_id)
        data = self._runtime.store.load(f"{tool_id}_{name}", default or {})
        return data if isinstance(data, dict) else dict(default or {})

    def doc_save(self, tool_id: str, name: str, data: dict) -> dict:
        """
        写入工具自有的 JSON 文档.
        """

        # 同上：先校验工具 id，再落盘
        self._registry.get(tool_id)
        if not isinstance(data, dict):
            raise AppError("INVALID_DATA", "文档内容必须是对象")
        return self._runtime.store.save(f"{tool_id}_{name}", data)


class Registry:
    """工具注册表：注册、查找、枚举与派发动作；整个应用只应有一个实例。"""

    def __init__(self) -> None:
        """初始化空注册表，键是工具 id。"""

        self._tools: dict[str, RegisteredTool] = {}

    def register(
        self,
        manifest: ToolManifest,
        handlers: dict[str, Handler],
        legacy: Callable[[dict], dict] | None = None,
    ) -> None:
        """注册一个工具；id 重复说明代码写错了，这里直接抛 ValueError。"""

        if manifest.id in self._tools:
            raise ValueError(f"tool already registered: {manifest.id}")
        self._tools[manifest.id] = RegisteredTool(manifest, handlers, legacy)

    def get(self, tool_id: str) -> RegisteredTool:
        """按 id 取已注册工具；不存在时抛 AppError（UNKNOWN_TOOL）。"""

        tool = self._tools.get(tool_id)
        if tool is None:
            raise AppError("UNKNOWN_TOOL", f"未知工具：{tool_id}")
        return tool

    def ids(self) -> list[str]:
        """按 manifest.order 升序返回工具 id，这个顺序就是侧边栏顺序。"""

        return sorted(self._tools, key=lambda i: self._tools[i].manifest.order)

    def manifests(self) -> list[dict]:
        """返回所有工具的描述字典，顺序与 ids() 一致。"""

        return [self._tools[i].manifest.to_dict() for i in self.ids()]

    def manifest(self, tool_id: str) -> dict:
        """返回单个工具的描述字典。"""

        return self.get(tool_id).manifest.to_dict()

    def call(self, tool_id: str, action: str, payload: dict, ctx: Context) -> dict:
        """按 id + 动作名派发到具体处理函数；未知工具或未知动作都转成 AppError。"""

        tool = self.get(tool_id)
        handler = tool.handlers.get(action)
        if handler is None:
            raise AppError("UNKNOWN_ACTION", f"工具 {tool_id} 没有动作 {action}")
        return handler(payload, ctx)

    def convert_legacy(self, tool_id: str, raw: dict) -> dict:
        """用旧版配置转换器把历史 JSON 迁移成当前格式；没有转换器就原样返回。"""

        tool = self.get(tool_id)
        if tool.legacy is None:
            return raw
        return tool.legacy(raw)
