# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 配置读写与备份           #
# =================================== #
# 本文件职责：一个数据目录下的配置仓储 —— JSON 读写、原子替换、自动备份与损坏恢复。
# 上层只用 load / save；当前配置放 settings/，历史副本放 backups/。

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

# 每个配置最多保留 5 份历史备份，避免 backups/ 无限涨
MAX_BACKUPS = 5


class Store:
    """一个数据目录的配置仓储：<root>/settings 存配置，<root>/backups 存历史副本。"""

    def __init__(self, root: Path) -> None:
        """记录根目录，并确保 settings/ 与 backups/ 两个子目录存在（首次运行会创建）。"""

        self.root = Path(root)
        self.settings_dir = self.root / "settings"
        self.backup_dir = self.root / "backups"
        self.settings_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    # ------ 路径 ------ #
    def path(self, name: str) -> Path:
        """配置名 → 完整路径（<root>/settings/<name>.json，name 不带后缀）。"""

        return self.settings_dir / f"{name}.json"

    # ------ 读写 ------ #
    def load(self, name: str, default: dict | None = None) -> dict:
        """读取配置：主文件可用就用它；损坏或缺失时尝试最新备份；再不行返回默认值副本。"""

        default = default or {}
        path = self.path(name)
        data = self._read(path)
        if data is not None:
            return data
        # 主文件读不出来才动备份：_restore 会把选中的备份复制回主文件位置
        restored = self._restore(name)
        if restored is not None:
            return restored
        return dict(default)

    def save(self, name: str, data: dict) -> dict:
        """保存配置：先给旧文件拍快照，再写临时文件并原子替换，避免写到一半损坏。"""

        path = self.path(name)
        # 先备份：即使新内容有问题，也还能从 backups/ 找回上一版
        self._snapshot(name, path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        # 先写 .tmp 再改名：同分区上 os.replace 是原子操作，不会留下半个文件
        os.replace(tmp, path)
        return data

    def export_all(self) -> dict[str, Any]:
        """把所有 *.json 配置汇总成 {名称: 内容}；单个文件读不出来就跳过它。"""

        result: dict[str, Any] = {}
        for file in sorted(self.settings_dir.glob("*.json")):
            try:
                with open(file, encoding="utf-8") as f:
                    result[file.stem] = json.load(f)
            except Exception:  # noqa: BLE001
                continue
        return result

    def import_all(self, payload: dict[str, Any]) -> None:
        """批量写入配置；名称只允许字母/数字/连字符，防止 ../ 之类的路径穿越。"""

        for name, data in payload.items():
            # 只接受顶层是对象的配置，且名字必须干净
            if isinstance(data, dict) and name.replace("-", "").isalnum():
                self.save(name, data)

    # ------ 内部 ------ #
    @staticmethod
    def _read(path: Path) -> dict | None:
        """读一个 JSON；文件不存在、解析失败或顶层不是对象时返回 None（交给备份逻辑）。"""

        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else None
        except Exception:  # noqa: BLE001 - 损坏时交给备份
            return None

    def _snapshot(self, name: str, path: Path) -> None:
        """写前备份：把现有文件复制到 backups/，并只保留最近 MAX_BACKUPS 份。"""

        if not path.exists():
            return
        # 时间戳固定为 YYYYMMDD-HHMMSS，因此文件名排序等价于时间排序
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = self.backup_dir / f"{name}.{stamp}.json"
        try:
            shutil.copy2(path, target)
        except Exception:  # noqa: BLE001
            return
        backups = sorted(self.backup_dir.glob(f"{name}.*.json"))
        # 升序排列后，backups[:-MAX_BACKUPS] 正是最旧、需要清理的那几份
        for old in backups[:-MAX_BACKUPS]:
            try:
                old.unlink()
            except OSError:
                pass

    def _restore(self, name: str) -> dict | None:
        """从备份恢复：取时间最新的一份可用备份，复制回主路径并返回其内容。"""

        # reverse=True 让最新的备份排在前面
        backups = sorted(self.backup_dir.glob(f"{name}.*.json"), reverse=True)
        for backup in backups:
            data = self._read(backup)
            if data is not None:
                try:
                    shutil.copy2(backup, self.path(name))
                except OSError:
                    # 回写失败也照样把内容还给调用方：能读到数据比修好文件更重要
                    pass
                return data
        return None
