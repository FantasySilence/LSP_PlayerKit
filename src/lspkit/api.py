# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 前端与后端的通信门面     #
# =================================== #
# 本文件职责：暴露给 WebView 的 js_api 对象 —— 前端每个 window.pywebview.api.xxx 调用都落到这里。
# 约定：公开方法只负责“参数兜底 + 包返回信封”，真正逻辑在同名 _ 私有方法里，便于单测。

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from lspkit import __version__
from lspkit.errors import AppError, envelope
from lspkit.paths import resource_dir, version_info
from lspkit.platform import locator
from lspkit.platform.registry import Context, Registry
from lspkit.platform.schema import has_path
from lspkit.platform.storage import Runtime, StorageManager

# 应用级偏好的默认值：读配置时用它们兜底，也决定“重置偏好”后的初始状态
APP_DEFAULTS = {
    "language": "zh_CN",
    "theme": "dark",
    "lastTool": "pearl",
    "window": {},
}

# 单个文本类文件的大小上限：5MB，超过就拒绝读取，避免把界面卡死
MAX_TEXT_FILE_BYTES = 5 * 1024 * 1024
# 投影（.litematic）允许更大：上限 64MB，因为它保存的是完整方块数据
MAX_LITEMATIC_BYTES = 64 * 1024 * 1024


class Api:
    """pywebview 的 js_api 门面：前端的每次 API 调用都对应这里的一个公开方法。"""

    def __init__(self, runtime: Runtime, registry: Registry) -> None:
        """保存运行期状态，并预先建好动作上下文与数据目录管理器。"""

        self._rt = runtime
        self._registry = registry
        # 所有工具动作共用同一个 Context：它负责按工具 id 隔离各自的设置
        self._ctx = Context(runtime, registry)
        self._storage = StorageManager(runtime)

    # ------ 状态 ------ #
    def app_state(self) -> dict:
        """前端首屏调用：一次拿到版本、偏好、全部工具清单与存储信息。"""

        return envelope(self._app_state)

    def _app_state(self) -> dict:
        """真正组装首屏数据；版本号优先取 resources/version.json，取不到退回代码常量。"""

        prefs = self._prefs()
        info = version_info()
        return {
            "version": info.get("version", __version__),
            "language": prefs["language"],
            "theme": prefs["theme"],
            "lastTool": prefs["lastTool"],
            "tools": self._registry.manifests(),
            "storage": self._storage.info(),
        }

    def app_set_pref(self, key: str, value: Any) -> dict:
        """设置一条应用偏好（语言 / 主题 / 上次打开的工具），返回保存后的全部偏好。"""

        return envelope(self._set_pref, key, value)

    def _set_pref(self, key: str, value: Any) -> dict:
        """校验偏好名后写入并返回完整偏好表；未知的键直接拒绝。"""

        # 白名单：只允许改这三项，防止前端顺手写入任意键污染配置
        allowed = {"language", "theme", "lastTool"}
        if key not in allowed:
            raise AppError("INVALID_PREF", f"未知偏好：{key}")
        prefs = self._prefs()
        prefs[key] = value
        self._rt.store.save("app", prefs)
        return prefs

    def app_save_window(self, width: int, height: int) -> dict:
        """记录窗口尺寸，下次启动时据此恢复（转成 int 兜底，防止前端传字符串）。"""

        def run() -> dict:
            prefs = self._prefs()
            prefs["window"] = {"width": int(width), "height": int(height)}
            self._rt.store.save("app", prefs)
            return prefs

        return envelope(run)

    # ------ 工具 ------ #
    def tool_manifests(self) -> dict:
        """返回所有工具的描述（侧边栏据此渲染，前端不硬编码工具列表）。"""

        return envelope(self._registry.manifests)

    def tool_call(self, tool: str, action: str, payload: dict | None = None) -> dict:
        """调用某工具的动作；payload 允许为 None，统一当作空字典处理。"""

        return envelope(self._call, tool, action, payload or {})

    def _call(self, tool: str, action: str, payload: dict) -> dict:
        """把调用转给注册表，由具体工具的处理函数完成业务计算。"""

        return self._registry.call(tool, action, payload, self._ctx)

    # ------ 设置 ------ #
    def settings_get(self, tool: str) -> dict:
        """读取某工具的当前设置（逐字段清洗过，可直接绑定到表单）。"""

        return envelope(self._ctx.settings, tool)

    def settings_save(self, tool: str, values: dict) -> dict:
        """保存某工具的设置；values 为 None 时按空对象处理，由 schema 补齐默认值。"""

        return envelope(self._ctx.save_settings, tool, values or {})

    def settings_reset(self, tool: str) -> dict:
        """把某工具的设置恢复成 schema 里的默认值（旧值会被 store 自动备份）。"""

        def run() -> dict:
            defaults = self._registry.get(tool).manifest.schema.defaults()
            return self._ctx.save_settings(tool, defaults)

        return envelope(run)

    def settings_import_file(self, tool: str) -> dict:
        """从本地 JSON 文件导入某工具的设置（兼容旧格式，见 _import_settings）。"""

        return envelope(self._import_settings, tool)

    def _import_settings(self, tool: str) -> dict:
        """挑一个 JSON 文件导入：旧格式先转换，再确认“确实是这个工具的文件”。"""

        import webview

        window = self._rt.window
        if window is None:
            raise AppError("NO_WINDOW", "窗口尚未就绪")
        result = window.create_file_dialog(
            webview.FileDialog.OPEN, file_types=("JSON 文件 (*.json)",)
        )
        if not result:
            return {"cancelled": True}
        path = Path(result[0] if isinstance(result, (list, tuple)) else result)
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as exc:  # noqa: BLE001
            raise AppError("INVALID_FILE", "无法读取该 JSON 文件", str(exc)) from exc
        if not isinstance(raw, dict):
            raise AppError("INVALID_FILE", "配置文件内容必须是一个对象")

        # 先过一遍旧版转换器，把历史字段名映射成现在使用的 key
        converted = self._registry.convert_legacy(tool, raw)
        schema = self._registry.get(tool).manifest.schema
        # 一个字段都对不上 -> 多半是选错了文件（例如导入了别的工具的配置）
        if not any(has_path(converted, field.key) for field in schema.fields):
            raise AppError(
                "WRONG_TOOL_FILE",
                "这个 JSON 里没有任何该工具的配置项，已取消导入",
                "请确认导入的是对应工具的配置文件",
            )
        values = schema.validate(converted)
        # migrated 用于告诉前端“这份文件被转换过”，可以提示用户另存为新格式
        return {"path": str(path), "values": values, "migrated": converted is not raw}

    # ------ 数据目录 ------ #
    def storage_info(self) -> dict:
        """查询当前数据目录（路径、来源、是否便携、是否可写）。"""

        return envelope(self._storage.info)

    def storage_pick_dir(self) -> dict:
        """弹目录选择框；用户取消时返回的数据为 None。"""

        return envelope(self._storage.pick_dir)

    def storage_set_dir(self, path: str) -> dict:
        """把数据目录切换到 path，成功后返回新的存储信息。"""

        return envelope(self._storage.set_dir, path)

    def storage_reset(self) -> dict:
        """恢复默认数据目录。"""

        return envelope(self._storage.reset)

    def storage_open_dir(self) -> dict:
        """在资源管理器里打开数据目录（未取消即算成功）。"""

        return envelope(self._storage.open_dir)

    def storage_export_bundle(self) -> dict:
        """导出配置包为 zip；用户取消时返回 {cancelled: True}。"""

        return envelope(self._storage.export_bundle)

    def storage_import_bundle(self) -> dict:
        """从 zip 配置包导入设置，返回被导入的工具名列表。"""

        return envelope(self._storage.import_bundle)

    # ------ 文件 ------ #
    def file_open_text(self) -> dict:
        """选一个文本文件并读取内容；用户取消时返回 {cancelled: True}。"""

        return envelope(self._open_text)

    def file_open_texts(self) -> dict:
        """选多个文本文件，返回 {files: [每个文件的结果]}。"""

        return envelope(self._open_texts)

    def file_open_material_lists(self, locale: str = "zh_cn") -> dict:
        """选材料清单/投影文件；locale 决定 .litematic 里的方块名用哪种语言。"""

        return envelope(self._open_material_lists, locale)

    def _open_text(self) -> dict:
        """单选文本文件的具体实现。"""

        import webview

        paths = self._pick_files(webview, allow_multiple=False)
        if not paths:
            return {"cancelled": True}
        return self._read_text_file(Path(paths[0]))

    def _open_texts(self) -> dict:
        """多选文本文件的具体实现：逐个读取后一起返回。"""

        import webview

        paths = self._pick_files(webview, allow_multiple=True)
        if not paths:
            return {"cancelled": True}
        return {"files": [self._read_text_file(Path(path)) for path in paths]}

    def _open_material_lists(self, locale: str = "zh_cn") -> dict:
        """多选材料清单：按扩展名决定走文本解析还是投影解析。"""

        import webview

        paths = self._pick_files(
            webview,
            allow_multiple=True,
            file_types=(
                "材料清单或投影 (*.csv;*.txt;*.tsv;*.litematic)",
                "材料清单 (*.csv;*.txt;*.tsv)",
                "投影 (*.litematic)",
                "所有文件 (*.*)",
            ),
        )
        if not paths:
            return {"cancelled": True}

        files = []
        for raw_path in paths:
            path = Path(raw_path)
            # .litematic 是二进制格式，必须走专用解析器；其余都按文本读
            if path.suffix.lower() == ".litematic":
                files.append(self._read_litematic(path, locale))
            else:
                files.append(self._read_text_file(path))
        return {"files": files}

    def _read_litematic(self, path: Path, locale: str = "zh_cn") -> dict:
        """读取投影文件并解析成材料清单；解析失败转成 AppError（INVALID_LITEMATIC）。"""

        from lspkit.tools.material.core.litematic import LitematicError, parse_litematic

        raw = self._read_bytes(path, MAX_LITEMATIC_BYTES)
        try:
            parsed = parse_litematic(raw, locale)
        except LitematicError as exc:
            raise AppError("INVALID_LITEMATIC", str(exc), path.name) from exc
        return {
            "kind": "litematic",
            "path": str(path),
            "name": path.name,
            "entries": parsed["entries"],
            "meta": parsed["meta"],
            "warnings": parsed["warnings"],
        }

    def _pick_files(self, webview, allow_multiple: bool, file_types: tuple | None = None) -> tuple:
        """弹文件选择框并统一返回 tuple；用户取消时返回空 tuple。"""

        window = self._rt.window
        if window is None:
            raise AppError("NO_WINDOW", "窗口尚未就绪")
        result = window.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=allow_multiple,
            file_types=file_types
            or ("文本与表格 (*.txt;*.csv;*.tsv;*.log)", "所有文件 (*.*)"),
        )
        if not result:
            return ()
        # pywebview 单选时返回 str、多选时返回 list/tuple，这里统一成 tuple
        if isinstance(result, (list, tuple)):
            return tuple(result)
        return (result,)

    def _read_bytes(self, path: Path, limit: int) -> bytes:
        """读文件字节；先查大小，超过 limit 直接拒绝，避免一次性把内存吃爆。"""

        try:
            size = path.stat().st_size
        except OSError as exc:
            raise AppError("INVALID_FILE", "无法读取该文件", str(exc)) from exc
        if size > limit:
            raise AppError(
                "FILE_TOO_LARGE",
                "文件太大，请拆分后再导入",
                f"{size} 字节（上限 {limit}）",
            )
        try:
            return path.read_bytes()
        except OSError as exc:
            raise AppError("INVALID_FILE", "无法读取该文件", str(exc)) from exc

    def _read_text_file(self, path: Path) -> dict:
        """读文本文件并按常见编码解码，返回前端统一使用的文件对象。"""

        raw = self._read_bytes(path, MAX_TEXT_FILE_BYTES)
        return {"kind": "text", "path": str(path), "name": path.name, "text": _decode_text(raw)}

    def file_save_text(
        self, filename: str, content: str, directory: str = "", bom: bool = True
    ) -> dict:
        """另存文本文件（弹对话框）；bom=True 时写 UTF-8 BOM，方便 Excel 识别中文。"""

        return envelope(self._save_text, filename, content, directory, bom)

    def _save_text(
        self, filename: str, content: str, directory: str = "", bom: bool = True
    ) -> dict:
        """另存为的具体实现：清理文件名、准备导出目录、按指定编码写盘。"""

        import webview

        if not isinstance(content, str) or not content:
            raise AppError("INVALID_INPUT", "没有可保存的内容")
        window = self._rt.window
        if window is None:
            raise AppError("NO_WINDOW", "窗口尚未就绪")
        # 只取文件名部分，防止前端传进来的名字里带路径分隔符
        safe_name = Path(str(filename or "")).name or "export.csv"
        suffix = Path(safe_name).suffix.lower() or ".csv"
        kwargs: dict = {
            "save_filename": safe_name,
            "file_types": (f"{suffix.upper()[1:]} 文件 (*{suffix})", "所有文件 (*.*)"),
        }
        # 默认打开到数据目录下的 output/，用户仍可在对话框里改到别处
        target_dir = _export_dir(directory, self._rt.location.path)
        if target_dir is not None:
            kwargs["directory"] = str(target_dir)
        result = window.create_file_dialog(webview.FileDialog.SAVE, **kwargs)
        if not result:
            return {"cancelled": True}
        target = Path(result[0] if isinstance(result, (list, tuple)) else result)
        try:
            # utf-8-sig 会写 BOM：中文 CSV 不写 BOM 时 Excel 容易打开乱码
            encoding = "utf-8-sig" if bom else "utf-8"
            # newline="" 把换行控制权交给内容本身，避免 Windows 上多出空行
            with open(target, "w", encoding=encoding, newline="") as f:
                f.write(content)
        except OSError as exc:
            raise AppError("WRITE_FAILED", "无法写入该文件", str(exc)) from exc
        return {"path": str(target)}

    # ------ 系统 ------ #
    def clipboard_write(self, text: str) -> dict:
        """把文本写进系统剪贴板（WebView2 里 navigator.clipboard 不稳定，改走后端）。"""

        return envelope(_clipboard_write, text)

    def open_manual(self, locale: str = "zh_CN") -> dict:
        """用系统默认阅读器打开内置说明 PDF；locale 以 en 开头时打开英文版。"""

        def run() -> None:
            english = str(locale).lower().startswith("en")
            name = "README.en.pdf" if english else "README.pdf"
            target = resource_dir() / "docs" / name
            if not target.exists():
                raise AppError("NOT_FOUND", "没有找到说明文件", str(target))
            os.startfile(str(target))  # noqa: S606

        return envelope(run)

    def open_external(self, url: str) -> dict:
        """用默认浏览器打开外链；只放行 http(s)，避免被利用打开本地路径或程序。"""

        def run() -> None:
            # 白名单式校验：只接受 http/https，file:// 之类一律拒绝
            if not url.startswith(("http://", "https://")):
                raise AppError("INVALID_URL", "只允许打开 http(s) 链接")
            import webbrowser

            webbrowser.open(url)

        return envelope(run)

    # ------ 内部 ------ #
    def _prefs(self) -> dict:
        """读取应用偏好：只保留认识的键，缺的用默认值补齐。"""

        saved = self._rt.store.load("app", APP_DEFAULTS)
        prefs = dict(APP_DEFAULTS)
        # 只覆盖默认表里已有的键，配置文件里残留的旧字段会被忽略
        prefs.update({k: saved[k] for k in APP_DEFAULTS if k in saved})
        return prefs


def _export_dir(directory: str, data_dir: Path) -> Path | None:
    """
    解析导出目录：自定义目录优先，否则用数据目录下的 output.

    返回第一个能创建成功的目录；都失败返回 None（此时由系统保存框自己选目录）。
    """

    candidates: list[Path] = []
    # 候选按优先级排列：用户指定的目录排第一，其次才是默认 output/
    if directory:
        candidates.append(Path(directory).expanduser())
    candidates.append(data_dir / "output")

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except OSError:
            continue
    return None


def _decode_text(raw: bytes) -> str:
    """
    按常见编码依次尝试解码，失败时用替换字符兜底.
    """

    # 顺序有讲究：utf-8-sig 能顺手吃掉 BOM，gbk 覆盖中文 Windows，最后才试 utf-16
    for encoding in ("utf-8-sig", "gbk", "utf-16"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    # 全失败也要给出可读文本：用替换字符，不让整个导入流程崩掉
    return raw.decode("utf-8", errors="replace")


def _clipboard_write(text: str) -> bool:
    """
    Windows 剪贴板写入（WebView2 下 navigator.clipboard 不稳定）.
    """

    import ctypes
    from ctypes import wintypes

    # Win32 剪贴板常量：CF_UNICODETEXT=13（Unicode 文本），GMEM_MOVEABLE=0x0002（可移动全局内存）
    cf_unicode = 13
    gmem_moveable = 0x0002

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    # 64 位下 HANDLE/HGLOBAL 必须显式声明，否则 ctypes 按 32 位 int 处理会溢出
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL

    # 末尾补两个 0 字节：Windows 剪贴板要求文本以 UTF-16 的 NUL 结尾
    data = str(text).encode("utf-16-le") + b"\x00\x00"
    # 先申请一块全局内存，把内容拷进去后再交给剪贴板（所有权随之转移）
    handle = kernel32.GlobalAlloc(gmem_moveable, len(data))
    if not handle:
        raise AppError("CLIPBOARD_FAILED", "剪贴板分配失败")
    pointer = kernel32.GlobalLock(handle)
    try:
        ctypes.memmove(pointer, data, len(data))
    finally:
        # 拷完立刻解锁：加锁期间别的进程碰不到这块内存
        kernel32.GlobalUnlock(handle)

    # 剪贴板是全局独占资源，别的程序正开着时 OpenClipboard 会失败
    if not user32.OpenClipboard(None):
        raise AppError("CLIPBOARD_FAILED", "剪贴板被其他程序占用")
    try:
        user32.EmptyClipboard()
        user32.SetClipboardData(cf_unicode, handle)
    finally:
        user32.CloseClipboard()
    return True
