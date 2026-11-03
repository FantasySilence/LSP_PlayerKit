# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 材料换算常量             #
# =================================== #

# ------ 输入上限 ------ #

MAX_TEXT_LENGTH = 200_000
MAX_KINDS = 5_000
MAX_WARNINGS = 20

# ------ 解析 ------ #

# 行尾数量：支持 1728 / 1,728 / 1_728，以及「个 / item / block」后缀
TRAILING_COUNT = r"(?P<count>\d[\d,._]*)\s*(?:个|items?|blocks?|pcs?)?\s*$"

# 名字与数量之间的分隔符，切掉后即为物品名
NAME_TRIM = " \t,;:|×xX*-"
