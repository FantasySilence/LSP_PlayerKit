# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 假人搬货 manifest        #
# =================================== #

"""
工具注册信息：元数据 + 动作表 + 前端表格列 + HANDLERS。

MANIFEST 里的 labelKey / nameKey 都是 i18n 键，不是文案本身；
动作 id 必须与前端调用的名字一致，HANDLERS 的键必须覆盖前端会用到的每个动作，
否则前端点了会报「未知动作」。新增动作时三处都要加：
MANIFEST.actions（工具栏按钮）、HANDLERS（后端实现）、前端调用点。
"""

from lspkit.platform.registry import ToolManifest

from .actions import (
    diagnose_action,
    draft_load,
    draft_save,
    history_clear,
    history_list,
    plan_action,
    run_continue,
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
    # id 是工具目录与文档存储的命名空间，改动会让已存的站点 / 台账读不出来.
    id="puppet",
    name_key="puppet.name",
    description_key="puppet.description",
    icon="route",
    order=40,
    version="1.0.0",
    schema=SCHEMA,
    # 工具栏主按钮：生成计划、开始执行；其余动作由页面内部按钮触发.
    actions=[
        {"id": "plan", "labelKey": "puppet.action.plan"},
        {"id": "run_start", "labelKey": "puppet.action.execute"},
    ],
    # 命令预览表的列定义；phase 取 spawn / kill，bot 是假人序号.
    columns=[
        {"key": "index", "nameKey": "puppet.col.index", "type": "int"},
        {"key": "phase", "nameKey": "puppet.col.phase", "type": "string"},
        {"key": "bot", "nameKey": "puppet.col.bot", "type": "int"},
        {"key": "text", "nameKey": "puppet.col.command", "type": "string"},
    ],
)

# 动作名 → 处理函数；键名与前端 invoke 的 action 一一对应.
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
    "run_continue": run_continue,
    "draft_load": draft_load,
    "draft_save": draft_save,
    "diagnose": diagnose_action,
    "validate_template": validate_template_action,
}

# 设置迁移钩子：本工具没有旧版设置文件，convert 原样返回.
LEGACY = convert
