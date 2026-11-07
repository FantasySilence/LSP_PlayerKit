# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 主程序入口               #
# =================================== #
# 本文件职责：整个应用的启动点 —— 把 src/ 加进模块搜索路径，然后调用 lspkit.app.run()。
# 打包时 PyInstaller 也以本文件为入口（见 packaging/*.spec 的 Analysis 参数）。
from __future__ import annotations

import os
import sys

# 源码运行时 Python 找不到 src/lspkit，这里手动把 <仓库>/src 放到搜索路径最前面；
# 打包后 lspkit 已经收进 exe，这行只是多了一个无效路径，不会影响运行。
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

# 导入必须放在 sys.path 调整之后，所以这里要允许“导入不在文件顶部”的告警
from lspkit.app import run  # noqa: E402

if __name__ == "__main__":
    # 只有直接运行本文件才启动窗口；被 import（例如测试）时不启动
    run()
