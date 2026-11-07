# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 纯计算模块               #
# =================================== #
# 本包只放纯函数：输入普通 Python 数据，输出普通 Python 数据。
# 约定（保持这几条，计算部分才能脱离界面单独测试）：
#   1. 不 import webview / lspkit.api，不读文件、不写文件、不访问设置存储；
#   2. 不抛 UI 相关异常，参数非法时抛 ValueError 或 lspkit.errors.AppError，
#      由 actions.py 决定是否转成用户提示；
#   3. 一个模块一个主题（如 parse / convert / packing），函数之间通过参数传递数据，
#      不共享模块级可变状态；
#   4. 返回 dict 时键名与 manifest.columns 对齐，方便 actions 直接拼进结果。
# 需要示例时参照 material/core/ 下的实现：它按同样约定拆分了解析、换算与装箱。
