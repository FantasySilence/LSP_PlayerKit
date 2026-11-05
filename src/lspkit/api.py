# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 前端与后端的通信门面     #
# =================================== #

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

APP_DEFAULTS = {
    "language": "zh_CN",
    "theme": "dark",
    "lastTool": "pearl",
    "window": {},
}

MAX_TEXT_FILE_BYTES = 5 * 1024 * 1024


class Api:
    def __init__(self, runtime: Runtime, registry: Registry) -> None:
        self._rt = runtime
        self._registry = registry
        self._ctx = Context(runtime, registry)
        self._storage = StorageManager(runtime)

    # ------ 状态 ------ #
    def app_state(self) -> dict:
        return envelope(self._app_state)

    def _app_state(self) -> dict:
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
        return envelope(self._set_pref, key, value)

    def _set_pref(self, key: str, value: Any) -> dict:
        allowed = {"language", "theme", "lastTool"}
        if key not in allowed:
            raise AppError("INVALID_PREF", f"未知偏好：{key}")
        prefs = self._prefs()
        prefs[key] = value
        self._rt.store.save("app", prefs)
        return prefs

    def app_save_window(self, width: int, height: int) -> dict:
        def run() -> dict:
            prefs = self._prefs()
            prefs["window"] = {"width": int(width), "height": int(height)}
            self._rt.store.save("app", prefs)
            return prefs

        return envelope(run)

    # ------ 工具 ------ #
    def tool_manifests(self) -> dict:
        return envelope(self._registry.manifests)

    def tool_call(self, tool: str, action: str, payload: dict | None = None) -> dict:
        return envelope(self._call, tool, action, payload or {})

    def _call(self, tool: str, action: str, payload: dict) -> dict:
        return self._registry.call(tool, action, payload, self._ctx)

    # ------ 设置 ------ #
    def settings_get(self, tool: str) -> dict:
        return envelope(self._ctx.settings, tool)

    def settings_save(self, tool: str, values: dict) -> dict:
        return envelope(self._ctx.save_settings, tool, values or {})

    def settings_reset(self, tool: str) -> dict:
        def run() -> dict:
            defaults = self._registry.get(tool).manifest.schema.defaults()
            return self._ctx.save_settings(tool, defaults)

        return envelope(run)

    def settings_import_file(self, tool: str) -> dict:
        return envelope(self._import_settings, tool)

    def _import_settings(self, tool: str) -> dict:
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

        converted = self._registry.convert_legacy(tool, raw)
        schema = self._registry.get(tool).manifest.schema
        if not any(has_path(converted, field.key) for field in schema.fields):
            raise AppError(
                "WRONG_TOOL_FILE",
                "这个 JSON 里没有任何该工具的配置项，已取消导入",
                "请确认导入的是对应工具的配置文件",
            )
        values = schema.validate(converted)
        return {"path": str(path), "values": values, "migrated": converted is not raw}

    # ------ 数据目录 ------ #
    def storage_info(self) -> dict:
        return envelope(self._storage.info)

    def storage_pick_dir(self) -> dict:
        return envelope(self._storage.pick_dir)

    def storage_set_dir(self, path: str) -> dict:
        return envelope(self._storage.set_dir, path)

    def storage_reset(self) -> dict:
        return envelope(self._storage.reset)

    def storage_open_dir(self) -> dict:
        return envelope(self._storage.open_dir)

    def storage_export_bundle(self) -> dict:
        return envelope(self._storage.export_bundle)

    def storage_import_bundle(self) -> dict:
        return envelope(self._storage.import_bundle)

    # ------ 文件 ------ #
    def file_open_text(self) -> dict:
        return envelope(self._open_text)

    def file_open_texts(self) -> dict:
        return envelope(self._open_texts)

    def _open_text(self) -> dict:
        import webview

        paths = self._pick_files(webview, allow_multiple=False)
        if not paths:
            return {"cancelled": True}
        return self._read_text_file(Path(paths[0]))

    def _open_texts(self) -> dict:
        import webview

        paths = self._pick_files(webview, allow_multiple=True)
        if not paths:
            return {"cancelled": True}
        return {"files": [self._read_text_file(Path(path)) for path in paths]}

    def _pick_files(self, webview, allow_multiple: bool) -> tuple:
        window = self._rt.window
        if window is None:
            raise AppError("NO_WINDOW", "窗口尚未就绪")
        result = window.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=allow_multiple,
            file_types=("文本与表格 (*.txt;*.csv;*.tsv;*.log)", "所有文件 (*.*)"),
        )
        if not result:
            return ()
        if isinstance(result, (list, tuple)):
            return tuple(result)
        return (result,)

    def _read_text_file(self, path: Path) -> dict:
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise AppError("INVALID_FILE", "无法读取该文件", str(exc)) from exc
        if size > MAX_TEXT_FILE_BYTES:
            raise AppError(
                "FILE_TOO_LARGE", "文件太大，请只保留材料清单部分", f"{size} 字节"
            )
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise AppError("INVALID_FILE", "无法读取该文件", str(exc)) from exc
        return {"path": str(path), "name": path.name, "text": _decode_text(raw)}

    def file_save_text(self, filename: str, content: str, directory: str = "") -> dict:
        return envelope(self._save_text, filename, content, directory)

    def _save_text(self, filename: str, content: str, directory: str = "") -> dict:
        import webview

        if not isinstance(content, str) or not content:
            raise AppError("INVALID_INPUT", "没有可保存的内容")
        window = self._rt.window
        if window is None:
            raise AppError("NO_WINDOW", "窗口尚未就绪")
        safe_name = Path(str(filename or "")).name or "export.csv"
        suffix = Path(safe_name).suffix.lower() or ".csv"
        kwargs: dict = {
            "save_filename": safe_name,
            "file_types": (f"{suffix.upper()[1:]} 文件 (*{suffix})", "所有文件 (*.*)"),
        }
        target_dir = _export_dir(directory, self._rt.location.path)
        if target_dir is not None:
            kwargs["directory"] = str(target_dir)
        result = window.create_file_dialog(webview.FileDialog.SAVE, **kwargs)
        if not result:
            return {"cancelled": True}
        target = Path(result[0] if isinstance(result, (list, tuple)) else result)
        try:
            with open(target, "w", encoding="utf-8-sig", newline="") as f:
                f.write(content)
        except OSError as exc:
            raise AppError("WRITE_FAILED", "无法写入该文件", str(exc)) from exc
        return {"path": str(target)}

    # ------ 系统 ------ #
    def clipboard_write(self, text: str) -> dict:
        return envelope(_clipboard_write, text)

    def open_doc(self) -> dict:
        def run() -> None:
            target = resource_dir() / "docs" / "Config.pdf"
            if not target.exists():
                raise AppError("NOT_FOUND", "没有找到文档", str(target))
            os.startfile(str(target))  # noqa: S606

        return envelope(run)

    def open_external(self, url: str) -> dict:
        def run() -> None:
            if not url.startswith(("http://", "https://")):
                raise AppError("INVALID_URL", "只允许打开 http(s) 链接")
            import webbrowser

            webbrowser.open(url)

        return envelope(run)

    # ------ 内部 ------ #
    def _prefs(self) -> dict:
        saved = self._rt.store.load("app", APP_DEFAULTS)
        prefs = dict(APP_DEFAULTS)
        prefs.update({k: saved[k] for k in APP_DEFAULTS if k in saved})
        return prefs


def _export_dir(directory: str, data_dir: Path) -> Path | None:
    """
    解析导出目录：自定义目录优先，否则用数据目录下的 output.
    """

    candidates: list[Path] = []
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

    for encoding in ("utf-8-sig", "gbk", "utf-16"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def _clipboard_write(text: str) -> bool:
    """
    Windows 剪贴板写入（WebView2 下 navigator.clipboard 不稳定）.
    """

    import ctypes
    from ctypes import wintypes

    cf_unicode = 13
    gmem_moveable = 0x0002

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

    data = str(text).encode("utf-16-le") + b"\x00\x00"
    handle = kernel32.GlobalAlloc(gmem_moveable, len(data))
    if not handle:
        raise AppError("CLIPBOARD_FAILED", "剪贴板分配失败")
    pointer = kernel32.GlobalLock(handle)
    try:
        ctypes.memmove(pointer, data, len(data))
    finally:
        kernel32.GlobalUnlock(handle)

    if not user32.OpenClipboard(None):
        raise AppError("CLIPBOARD_FAILED", "剪贴板被其他程序占用")
    try:
        user32.EmptyClipboard()
        user32.SetClipboardData(cf_unicode, handle)
    finally:
        user32.CloseClipboard()
    return True
