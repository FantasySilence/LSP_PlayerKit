# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 假人搬货默认设置         #
# =================================== #

"""
假人搬货的出厂设置。

这里只定义值，不做校验；取值范围在 schema.py，校验由设置层负责。
用户改过的值会覆盖这里的同名键，缺失的键回落到这里。
"""

from .constants import (
    DEFAULT_BOTS_PER_BATCH,
    DEFAULT_BOXES_PER_BOT,
    DEFAULT_NAME_TEMPLATE,
)

DEFAULT_SETTINGS = {
    # ------ 运输口径 ------ #
    # 一个假人带多少盒；36 是背包容量上限，调小只会让假人变多.
    "boxesPerBot": DEFAULT_BOXES_PER_BOT,
    # 一批最多多少个假人；超过就分批，批间需要用户点「继续」.
    "botsPerBatch": DEFAULT_BOTS_PER_BATCH,
    # 名字模板占位符：{origin} {dest} {index}，必须含 {index} 以免重名.
    "nameTemplate": DEFAULT_NAME_TEMPLATE,
    # ------ 执行 ------ #
    # 安全开关：默认关闭，关闭时 run_start 直接报 EXECUTE_DISABLED.
    "allowExecute": False,
    # 两条命令之间的间隔（秒），太小会被服务器判定为刷屏.
    "commandInterval": 1.0,
    # 切换到游戏窗口后等多久才开始发第一条命令（秒），留时间给用户松手.
    "startDelay": 3,
    # paste：整条粘贴（快，依赖剪贴板）；type：逐字敲（慢，但更稳）.
    "inputMode": "paste",
    # 要求游戏窗口处于前台，否则不发命令，避免把聊天框输入打到别处.
    "requireFocus": True,
    # 单条命令失败后的重试次数（1–5）.
    "maxAttempts": 3,
    # 用完剪贴板后恢复原来的内容，避免污染用户剪贴板.
    "restoreClipboard": True,
}
