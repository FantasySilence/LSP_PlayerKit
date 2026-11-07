# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 站点配置生成脚本测试     #
# =================================== #
# 测试层：独立控制台小工具 src/tool_bundles/station_configmaker.py。
# 策略：用 importlib 按路径加载脚本，临时目录承接输出，验证生成的 JSON 结构与
# 「假人搬货」导入格式一致，并锁定前缀正则边界。

import importlib.util
import json
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "tool_bundles"
    / "station_configmaker.py"
)
# 该脚本不在 lspkit 包内，也不能 import 成模块；只能按文件路径加载。


def _load():
    """按文件路径加载独立脚本并返回模块对象（不写入 sys.modules）."""
    spec = importlib.util.spec_from_file_location("station_configmaker", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_write_file_matches_import_format(tmp_path, monkeypatch):
    """验证写出的 JSON 结构与导入格式一致.

    输入：一条含 group / dimension / prefix 的站点；输出目录 monkeypatch 到 tmp_path。
    期望：顶层 version=1、stations 列表；名称/分组/维度/前缀都原样写入。
    """
    module = _load()
    monkeypatch.setattr(
        module.StationConfigMaker,
        "output_dir",
        staticmethod(lambda: str(tmp_path)),
    )
    stations = [
        {
            "id": "tst",
            "name": "测试站点",
            "group": "主城",
            "prefix": "tst",
            "dimension": "the_end",
            "x": 1.0,
            "y": 2.0,
            "z": 3.0,
            "note": "",
        }
    ]
    path = module.StationConfigMaker.write_file(stations, "stations.json")
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    # version=1 与 {"stations": [...]} 是 legacy.parse 识别的结构，字段名需与站点 normalize 一致。
    assert data["version"] == 1
    assert data["stations"][0]["name"] == "测试站点"
    assert data["stations"][0]["group"] == "主城"
    assert data["stations"][0]["dimension"] == "the_end"
    assert data["stations"][0]["prefix"] == "tst"


def test_prefix_pattern():
    """验证站点前缀正则的边界.

    输入："con"、中文前缀、13 个 "x"。
    期望：只有 con 匹配；中文与超长（>12）都不匹配。
    """
    module = _load()
    assert module.PREFIX_PATTERN.match("con")
    assert not module.PREFIX_PATTERN.match("中文前缀")
    assert not module.PREFIX_PATTERN.match("x" * 13)
