# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 数据目录解析             #
# =================================== #
# 优先级：CLI/环境变量 → portable.json → 用户机器偏好 → 默认（exe 同级）。

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from lspkit.errors import AppError
from lspkit.paths import app_dir, appdata_dir

ENV_VAR = "LSPKIT_DATA_DIR"
PORTABLE_FILE = "portable.json"


@dataclass
class Location:
    path: Path
    source: str  # cli | env | portable | user | default | fallback
    portable: bool = False
    writable: bool = True
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "source": self.source,
            "portable": self.portable,
            "writable": self.writable,
            "note": self.note,
        }


def _probe(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:  # noqa: BLE001 - 任何失败都视为不可写
        return False


def _read_json(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def portable_file() -> Path:
    return app_dir() / PORTABLE_FILE


def user_pointer_file() -> Path:
    return appdata_dir() / "location.json"


def default_dir() -> Path:
    return app_dir() / "data"


def fallback_dir() -> Path:
    return appdata_dir() / "data"


def _candidate(cli_dir: str | None) -> tuple[Path, str, bool, str]:
    if cli_dir:
        return Path(cli_dir).expanduser(), "cli", False, ""
    env_dir = os.environ.get(ENV_VAR)
    if env_dir:
        return Path(env_dir).expanduser(), "env", False, ""

    portable_path = portable_file()
    if portable_path.exists():
        config = _read_json(portable_path)
        raw = config.get("dataDir")
        target = Path(raw).expanduser() if raw else default_dir()
        return target, "portable", True, ""

    pointer = user_pointer_file()
    if pointer.exists():
        raw = _read_json(pointer).get("dataDir")
        if raw:
            return Path(raw).expanduser(), "user", False, ""

    return default_dir(), "default", False, ""


def resolve(cli_dir: str | None = None) -> Location:
    path, source, portable, note = _candidate(cli_dir)
    if _probe(path):
        return Location(path=path, source=source, portable=portable, note=note)

    # exe 同级不可写：回退用户目录，并保留来源信息供 UI 提示
    fallback = fallback_dir()
    if _probe(fallback):
        return Location(
            path=fallback,
            source="fallback",
            portable=False,
            writable=True,
            note=f"配置目录 {path} 不可写，已使用用户目录",
        )
    raise AppError(
        "STORAGE_UNWRITABLE",
        "没有可写入的数据目录",
        f"尝试过：{path} 与 {fallback}",
    )


def set_user_location(path: Path) -> None:
    _write_json(user_pointer_file(), {"dataDir": str(path)})


def clear_user_location() -> None:
    pointer = user_pointer_file()
    try:
        pointer.unlink()
    except FileNotFoundError:
        pass


def set_portable(path: Path) -> None:
    target = portable_file()
    try:
        _write_json(target, {"dataDir": str(path)})
    except Exception as exc:  # noqa: BLE001 - 便携文件只是锦上添花
        raise AppError("PORTABLE_WRITE_FAILED", "无法写入 portable.json", str(exc)) from exc
