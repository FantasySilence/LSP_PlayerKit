# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 假人搬货默认设置         #
# =================================== #

from .constants import (
    DEFAULT_BOTS_PER_BATCH,
    DEFAULT_BOXES_PER_BOT,
    DEFAULT_NAME_TEMPLATE,
)

DEFAULT_SETTINGS = {
    # ------ 运输口径 ------ #
    "boxesPerBot": DEFAULT_BOXES_PER_BOT,
    "botsPerBatch": DEFAULT_BOTS_PER_BATCH,
    "nameTemplate": DEFAULT_NAME_TEMPLATE,
    # ------ 执行 ------ #
    "allowExecute": False,
    "commandInterval": 1.0,
    "startDelay": 3,
    "inputMode": "paste",
    "requireFocus": True,
    "maxAttempts": 3,
    "restoreClipboard": True,
}
