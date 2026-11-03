# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 配置读写与备份           #
# =================================== #

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

MAX_BACKUPS = 5


class Store:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.settings_dir = self.root / "settings"
        self.backup_dir = self.root / "backups"
        self.settings_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    # ------ 路径 ------ #
    def path(self, name: str) -> Path:
        return self.settings_dir / f"{name}.json"

    # ------ 读写 ------ #
    def load(self, name: str, default: dict | None = None) -> dict:
        default = default or {}
        path = self.path(name)
        data = self._read(path)
        if data is not None:
            return data
        restored = self._restore(name)
        if restored is not None:
            return restored
        return dict(default)

    def save(self, name: str, data: dict) -> dict:
        path = self.path(name)
        self._snapshot(name, path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return data

    def export_all(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for file in sorted(self.settings_dir.glob("*.json")):
            try:
                with open(file, encoding="utf-8") as f:
                    result[file.stem] = json.load(f)
            except Exception:  # noqa: BLE001
                continue
        return result

    def import_all(self, payload: dict[str, Any]) -> None:
        for name, data in payload.items():
            if isinstance(data, dict) and name.replace("-", "").isalnum():
                self.save(name, data)

    # ------ 内部 ------ #
    @staticmethod
    def _read(path: Path) -> dict | None:
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else None
        except Exception:  # noqa: BLE001 - 损坏时交给备份
            return None

    def _snapshot(self, name: str, path: Path) -> None:
        if not path.exists():
            return
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = self.backup_dir / f"{name}.{stamp}.json"
        try:
            shutil.copy2(path, target)
        except Exception:  # noqa: BLE001
            return
        backups = sorted(self.backup_dir.glob(f"{name}.*.json"))
        for old in backups[:-MAX_BACKUPS]:
            try:
                old.unlink()
            except OSError:
                pass

    def _restore(self, name: str) -> dict | None:
        backups = sorted(self.backup_dir.glob(f"{name}.*.json"), reverse=True)
        for backup in backups:
            data = self._read(backup)
            if data is not None:
                try:
                    shutil.copy2(backup, self.path(name))
                except OSError:
                    pass
                return data
        return None
