# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 假人搬货 manifest        #
# =================================== #

from lspkit.platform.registry import ToolManifest

from .actions import (
    diagnose_action,
    history_clear,
    history_list,
    plan_action,
    run_start,
    run_status,
    run_stop,
    stations_delete,
    stations_export,
    stations_import,
    stations_list,
    stations_save,
    validate_template_action,
)
from .legacy import convert
from .schema import SCHEMA

MANIFEST = ToolManifest(
    id="puppet",
    name_key="puppet.name",
    description_key="puppet.description",
    icon="route",
    order=40,
    version="1.0.0",
    schema=SCHEMA,
    actions=[
        {"id": "plan", "labelKey": "puppet.action.plan"},
        {"id": "run_start", "labelKey": "puppet.action.execute"},
    ],
    columns=[
        {"key": "index", "nameKey": "puppet.col.index", "type": "int"},
        {"key": "phase", "nameKey": "puppet.col.phase", "type": "string"},
        {"key": "bot", "nameKey": "puppet.col.bot", "type": "int"},
        {"key": "text", "nameKey": "puppet.col.command", "type": "string"},
    ],
)

HANDLERS = {
    "stations_list": stations_list,
    "stations_save": stations_save,
    "stations_delete": stations_delete,
    "stations_export": stations_export,
    "stations_import": stations_import,
    "plan": plan_action,
    "history_list": history_list,
    "history_clear": history_clear,
    "run_start": run_start,
    "run_status": run_status,
    "run_stop": run_stop,
    "diagnose": diagnose_action,
    "validate_template": validate_template_action,
}

LEGACY = convert
