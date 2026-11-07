# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 数据目录解析             #
# =================================== #
# 本文件职责：决定“设置 / 站点 / 日志”这些数据到底写到哪个目录。
# 只做路径决策与可写性探测，不负责配置内容的读写（那是 store.py 的事）。
# 优先级：CLI/环境变量 → portable.json → 用户机器偏好 → 默认（exe 同级）。

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from lspkit.errors import AppError
from lspkit.paths import app_dir, appdata_dir

# 环境变量名：设置后优先级仅次于命令行参数，方便快捷方式/脚本固定数据目录
ENV_VAR = "LSPKIT_DATA_DIR"
# 便携标记文件名：放在 exe 同级时表示“数据就放在我旁边”，可随 U 盘搬走
PORTABLE_FILE = "portable.json"


@dataclass
class Location:
    """一次解析的结果：最终目录 + 来源 + 是否便携 + 是否可写 + 给用户看的提示。"""

    path: Path
    source: str  # cli | env | portable | user | default | fallback
    portable: bool = False
    writable: bool = True
    note: str = ""

    def to_dict(self) -> dict:
        """转成前端“存储位置”面板要的 JSON（路径转成字符串）。"""

        return {
            "path": str(self.path),
            "source": self.source,
            "portable": self.portable,
            "writable": self.writable,
            "note": self.note,
        }


def _probe(directory: Path) -> bool:
    """真写一个临时文件来确认目录可写（只看 exists 不够，只读盘/权限问题会漏）。"""

    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        # 探测完立刻删除，不在用户目录里留垃圾
        probe.unlink()
        return True
    except Exception:  # noqa: BLE001 - 任何失败都视为不可写
        return False


def _read_json(path: Path) -> dict:
    """读 JSON 配置；文件缺失、损坏或顶层不是对象时一律返回空字典（不抛异常）。"""

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _write_json(path: Path, data: dict) -> None:
    """原子写 JSON：先写 .tmp 再改名，避免进程中途被杀时留下半个文件。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # 同分区改名是原子的，跨进程读到的要么是旧文件、要么是新文件
    os.replace(tmp, path)


def portable_file() -> Path:
    """便携标记文件路径（应用目录下的 portable.json）。"""

    return app_dir() / PORTABLE_FILE


def user_pointer_file() -> Path:
    """用户级“上次选过的数据目录”指针文件（存放在 AppData 下）。"""

    return appdata_dir() / "location.json"


def default_dir() -> Path:
    """默认数据目录：应用目录下的 data/，跟着 exe 走，便于整包搬动。"""

    return app_dir() / "data"


def fallback_dir() -> Path:
    """兜底数据目录：用户在 AppData 下的 data/，应用目录不可写时改用它。"""

    return appdata_dir() / "data"


def _candidate(cli_dir: str | None) -> tuple[Path, str, bool, str]:
    """按优先级挑出候选目录，返回 (路径, 来源标记, 是否便携, 附加说明)。

    这里只负责“选”，不保证可写；可写性由 resolve() 用 _probe 检查。
    """

    # 1. 命令行 --data-dir 优先级最高，主要给调试和多开用
    if cli_dir:
        return Path(cli_dir).expanduser(), "cli", False, ""
    # 2. 环境变量：适合用快捷方式或脚本固定数据目录
    env_dir = os.environ.get(ENV_VAR)
    if env_dir:
        return Path(env_dir).expanduser(), "env", False, ""

    # 3. 便携模式：exe 旁边有 portable.json，就按它里的 dataDir 走（没写则用默认 data/）
    portable_path = portable_file()
    if portable_path.exists():
        config = _read_json(portable_path)
        raw = config.get("dataDir")
        target = Path(raw).expanduser() if raw else default_dir()
        return target, "portable", True, ""

    # 4. 用户偏好：在界面上选过目录，会记在 AppData 的 location.json 里
    pointer = user_pointer_file()
    if pointer.exists():
        raw = _read_json(pointer).get("dataDir")
        if raw:
            return Path(raw).expanduser(), "user", False, ""

    # 5. 都没有，就用默认目录（应用目录下的 data/）
    return default_dir(), "default", False, ""


def resolve(cli_dir: str | None = None) -> Location:
    """解析出真正可用的数据目录：候选目录不可写时自动回退到用户目录。

    成功返回 Location；连兜底目录都不可写时抛 AppError（STORAGE_UNWRITABLE）。
    """

    path, source, portable, note = _candidate(cli_dir)
    if _probe(path):
        return Location(path=path, source=source, portable=portable, note=note)

    # exe 同级不可写：回退用户目录，并保留来源信息供 UI 提示
    fallback = fallback_dir()
    if _probe(fallback):
        return Location(
            path=fallback,
            source="fallback",
            # 回退目录不是用户主动选的便携目录，所以 portable 一律置 False
            portable=False,
            writable=True,
            note=f"配置目录 {path} 不可写，已使用用户目录",
        )
    # 两处都写不了：这是无法继续的启动错误，交给上层弹窗提示
    raise AppError(
        "STORAGE_UNWRITABLE",
        "没有可写入的数据目录",
        f"尝试过：{path} 与 {fallback}",
    )


def set_user_location(path: Path) -> None:
    """记住用户选中的数据目录（写到 AppData 的 location.json）。"""

    _write_json(user_pointer_file(), {"dataDir": str(path)})


def clear_user_location() -> None:
    """清除用户的选择，下次启动回到默认目录；文件本来就不存在时静默忽略。"""

    pointer = user_pointer_file()
    try:
        pointer.unlink()
    except FileNotFoundError:
        pass


def set_portable(path: Path) -> None:
    """把数据目录写进 portable.json（便携模式）；写失败转成 AppError 让界面提示。"""

    target = portable_file()
    try:
        _write_json(target, {"dataDir": str(path)})
    except Exception as exc:  # noqa: BLE001 - 便携文件只是锦上添花
        raise AppError("PORTABLE_WRITE_FAILED", "无法写入 portable.json", str(exc)) from exc
