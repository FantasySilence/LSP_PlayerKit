# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 站点配置生成脚本测试     #
# =================================== #

import importlib.util
import json
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "tool_bundles"
    / "station_configmaker.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("station_configmaker", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_write_file_matches_import_format(tmp_path, monkeypatch):
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
    assert data["version"] == 1
    assert data["stations"][0]["name"] == "测试站点"
    assert data["stations"][0]["group"] == "主城"
    assert data["stations"][0]["dimension"] == "the_end"
    assert data["stations"][0]["prefix"] == "tst"


def test_prefix_pattern():
    module = _load()
    assert module.PREFIX_PATTERN.match("con")
    assert not module.PREFIX_PATTERN.match("中文前缀")
    assert not module.PREFIX_PATTERN.match("x" * 13)
