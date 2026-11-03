# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 对外动作                 #
# =================================== #

from lspkit.platform import params


def my_action(payload: dict, ctx) -> dict:
    settings = ctx.settings("my-tool")
    value = params.number(payload, "value", default=settings["someNumber"], label="数值")
    return {"value": value}
