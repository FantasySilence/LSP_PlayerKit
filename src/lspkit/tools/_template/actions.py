# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 对外动作                 #
# =================================== #
# 动作处理只做三件事：从 payload 取参数（用 lspkit.platform.params 校验）、
# 从 ctx.settings 读本工具设置、把计算下沉到 core/ 后返回可序列化的 dict。
# 出错一律 raise AppError(code, 用户可读消息, 详情)，由 api 层转成前端提示。

from lspkit.platform import params

# ------ 动作处理 ------ #


def my_action(payload: dict, ctx) -> dict:
    """
    示例动作：返回界面上某个数值设置.

    复制后按需修改：
    1. 函数名与 manifest.py 的 actions[].id、HANDLERS 的键保持一致；
    2. ctx.settings("my-tool") 的参数是工具 id，必须与 manifest 的 id 相同，
       返回的 dict 里只有 schema.py 声明过的字段（缺项已用默认值补齐）；
    3. 参数校验用 params.number / integer / choice / obj，label 是要展示给用户的字段名；
    4. 返回值中的列表字段会被 manifest.columns 渲染成表格行，键名要能对上；
    5. 耗时计算请放到 core/ 的纯函数里，本函数只负责取值与组装。
    """

    settings = ctx.settings("my-tool")
    value = params.number(payload, "value", default=settings["someNumber"], label="数值")
    return {"value": value}
