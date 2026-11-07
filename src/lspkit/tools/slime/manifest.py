# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-07                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 史莱姆区块查找器 manifest #
# =================================== #

from lspkit.platform.registry import ToolManifest

from .actions import (
    find_action,
    map_action,
    scan_start,
    scan_status,
    scan_stop,
    seed_preview,
)
from .schema import SCHEMA

MANIFEST = ToolManifest(
    id="slime",
    name_key="slime.name",
    description_key="slime.description",
    icon="slime",
    order=50,
    version="1.0.0",
    schema=SCHEMA,
    actions=[
        {"id": "find", "labelKey": "slime.action.find"},
        {"id": "scan_start", "labelKey": "slime.action.scan"},
    ],
    columns=[
        {"key": "rank", "nameKey": "slime.col.rank", "type": "int"},
        {"key": "x", "nameKey": "slime.col.x", "type": "int"},
        {"key": "z", "nameKey": "slime.col.z", "type": "int"},
        {"key": "score", "nameKey": "slime.col.score", "type": "int"},
        {"key": "coverage", "nameKey": "slime.col.coverage", "type": "float", "digits": 3},
    ],
)

HANDLERS = {
    "find": find_action,
    "scan_start": scan_start,
    "scan_status": scan_status,
    "scan_stop": scan_stop,
    "map": map_action,
    "seed_preview": seed_preview,
}

LEGACY = None
