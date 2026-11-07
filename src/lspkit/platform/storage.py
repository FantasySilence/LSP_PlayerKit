# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 数据目录管理             #
# =================================== #
# 本文件职责：运行期共享状态（Runtime）与数据目录操作（切换 / 打开 / 导入导出配置包）。
# 只处理文件系统层面的事，不理解任何具体工具的配置含义。

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
    """运行期共享状态：当前数据目录、对应的 Store、WebView 缓存目录和窗口引用。

    启动时创建一份，之后 Api / StorageManager 都通过它读到同一份状态。
    """

    location: locator.Location
    store: Store
    # WebView2 的缓存目录：放在 AppData 下，避免污染用户选择的数据目录
    webview_dir: Path
    # pywebview 窗口对象；窗口创建后才有值，所有文件对话框都依赖它
    window: object | None = None

    def rebind(self, location: locator.Location) -> None:
        """切换数据目录：换掉 location 并为新目录重建 Store（旧目录内容不会自动搬走）。"""

        self.location = location
        self.store = Store(location.path)


class StorageManager:
    """数据目录相关操作：查询信息、切换目录、打开目录、导入导出配置包。"""

    def __init__(self, runtime: Runtime) -> None:
        """只保存运行期状态；真正的文件读写都通过 runtime.store 进行。"""

        self._rt = runtime

    def info(self) -> dict:
        """返回界面要展示的信息：数据目录、来源、是否可写、前端目录、版本号。"""

        data = self._rt.location.to_dict()
        data["webviewDir"] = str(self._rt.webview_dir)
        data["version"] = version_info().get("version", "")
        return data

    # ------ 切换 ------ #
    def pick_dir(self) -> str | None:
        """弹系统目录选择框，返回选中的路径；用户取消时返回 None。"""

        import webview

        window = self._rt.window
        if window is None:
            raise AppError("NO_WINDOW", "窗口尚未就绪")
        result = window.create_file_dialog(webview.FileDialog.FOLDER)
        if not result:
            return None
        # pywebview 不同版本返回 str 或 list，这里统一成单个字符串
        return str(result[0] if isinstance(result, (list, tuple)) else result)

    def set_dir(self, path: str) -> dict:
        """切换数据目录：校验可写、搬运旧设置、记住选择，最后返回新的存储信息。"""

        if not path:
            raise AppError("INVALID_INPUT", "请选择目录")
        target = Path(path).expanduser()
        # 先用写探针确认目标目录真能写，避免切过去之后才发现权限不够
        if not locator._probe(target):  # noqa: SLF001 - 同包工具函数
            raise AppError("STORAGE_UNWRITABLE", "该目录不可写，请换一个", str(target))
        # 选中的就是当前目录：什么都不用做，直接返回信息
        if target.resolve() == self._rt.location.path.resolve():
            return self.info()

        # 把旧目录里的设置复制到新目录，避免用户换目录后配置全部变回默认值
        self._copy_settings(self._rt.store.settings_dir, target / "settings")
        locator.set_user_location(target)
        if self._rt.location.portable:
            # 便携版换目录时同步改写 portable.json，保证下次启动仍认这个目录
            locator.set_portable(target)
        self._rt.rebind(
            locator.Location(path=target, source="user", portable=False, writable=True)
        )
        return self.info()

    def reset(self) -> dict:
        """清除“用户选择的目录”记录，回到默认解析结果。"""

        locator.clear_user_location()
        location = locator.resolve(None)
        self._rt.rebind(location)
        return self.info()

    def open_dir(self) -> None:
        """在资源管理器里打开当前数据目录（不存在就先创建）。"""

        path = self._rt.location.path
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(str(path))  # noqa: S606 - Windows 桌面应用

    # ------ 配置包 ------ #
    def export_bundle(self) -> dict:
        """把 settings/ 下所有 JSON 打包成 zip（内含 version.txt），保存路径由用户选择。"""

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
            # 统一放进 settings/ 子目录，导入时按这个前缀识别
            for file in sorted(self._rt.store.settings_dir.glob("*.json")):
                bundle.write(file, f"settings/{file.name}")
            # 附带生成配置包的应用版本，便于以后排查“旧包导入新版”的问题
            info = version_info()
            bundle.writestr("version.txt", info.get("version", ""))
        return {"path": str(target)}

    def import_bundle(self) -> dict:
        """从 zip 配置包导入：只认 settings/*.json，逐个写回当前数据目录。"""

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
                    # 只处理 settings/ 下的 json，version.txt 等其它条目直接忽略
                    if not name.startswith("settings/") or not name.endswith(".json"):
                        continue
                    # 文件名（去掉 .json）就是工具 id，例如 settings/pearl.json -> pearl
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
        """把旧目录的 *.json 设置复制到新目录；单个文件失败只跳过它。"""

        target.mkdir(parents=True, exist_ok=True)
        if not source.exists():
            return
        for file in source.glob("*.json"):
            try:
                shutil.copy2(file, target / file.name)
            except OSError:
                continue
