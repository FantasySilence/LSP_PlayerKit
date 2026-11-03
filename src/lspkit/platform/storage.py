# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 数据目录管理             #
# =================================== #

from __future__ import annotations

import os
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from lspkit.errors import AppError
from lspkit.platform import locator
from lspkit.platform.store import Store
from lspkit.paths import version_info


@dataclass
class Runtime:
    location: locator.Location
    store: Store
    webview_dir: Path
    window: object | None = None

    def rebind(self, location: locator.Location) -> None:
        self.location = location
        self.store = Store(location.path)


class StorageManager:
    def __init__(self, runtime: Runtime) -> None:
        self._rt = runtime

    def info(self) -> dict:
        data = self._rt.location.to_dict()
        data["webviewDir"] = str(self._rt.webview_dir)
        data["version"] = version_info().get("version", "")
        return data

    # ------ 切换 ------ #
    def pick_dir(self) -> str | None:
        import webview

        window = self._rt.window
        if window is None:
            raise AppError("NO_WINDOW", "窗口尚未就绪")
        result = window.create_file_dialog(webview.FileDialog.FOLDER)
        if not result:
            return None
        return str(result[0] if isinstance(result, (list, tuple)) else result)

    def set_dir(self, path: str) -> dict:
        if not path:
            raise AppError("INVALID_INPUT", "请选择目录")
        target = Path(path).expanduser()
        if not locator._probe(target):  # noqa: SLF001 - 同包工具函数
            raise AppError("STORAGE_UNWRITABLE", "该目录不可写，请换一个", str(target))
        if target.resolve() == self._rt.location.path.resolve():
            return self.info()

        self._copy_settings(self._rt.store.settings_dir, target / "settings")
        locator.set_user_location(target)
        if self._rt.location.portable:
            locator.set_portable(target)
        self._rt.rebind(
            locator.Location(path=target, source="user", portable=False, writable=True)
        )
        return self.info()

    def reset(self) -> dict:
        locator.clear_user_location()
        location = locator.resolve(None)
        self._rt.rebind(location)
        return self.info()

    def open_dir(self) -> None:
        path = self._rt.location.path
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(str(path))  # noqa: S606 - Windows 桌面应用

    # ------ 配置包 ------ #
    def export_bundle(self) -> dict:
        import webview

        window = self._rt.window
        if window is None:
            raise AppError("NO_WINDOW", "窗口尚未就绪")
        result = window.create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename="lsp_playerkit_settings.zip",
            file_types=("ZIP 压缩包 (*.zip)",),
        )
        if not result:
            return {"cancelled": True}
        target = Path(result[0] if isinstance(result, (list, tuple)) else result)
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
            for file in sorted(self._rt.store.settings_dir.glob("*.json")):
                bundle.write(file, f"settings/{file.name}")
            info = version_info()
            bundle.writestr("version.txt", info.get("version", ""))
        return {"path": str(target)}

    def import_bundle(self) -> dict:
        import json

        import webview

        window = self._rt.window
        if window is None:
            raise AppError("NO_WINDOW", "窗口尚未就绪")
        result = window.create_file_dialog(
            webview.FileDialog.OPEN, file_types=("ZIP 压缩包 (*.zip)",)
        )
        if not result:
            return {"cancelled": True}
        source = Path(result[0] if isinstance(result, (list, tuple)) else result)
        imported: list[str] = []
        try:
            with zipfile.ZipFile(source) as bundle:
                for name in bundle.namelist():
                    if not name.startswith("settings/") or not name.endswith(".json"):
                        continue
                    tool = Path(name).stem
                    data = json.loads(bundle.read(name).decode("utf-8"))
                    if isinstance(data, dict):
                        self._rt.store.save(tool, data)
                        imported.append(tool)
        except zipfile.BadZipFile as exc:
            raise AppError("INVALID_BUNDLE", "不是有效的配置包", str(exc)) from exc
        return {"imported": imported}

    # ------ 内部 ------ #
    @staticmethod
    def _copy_settings(source: Path, target: Path) -> None:
        target.mkdir(parents=True, exist_ok=True)
        if not source.exists():
            return
        for file in source.glob("*.json"):
            try:
                shutil.copy2(file, target / file.name)
            except OSError:
                continue
