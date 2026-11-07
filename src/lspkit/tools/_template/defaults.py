# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 出厂默认值               #
# =================================== #
# schema.py 里每个 Field 的 default 都从 DEFAULT_SETTINGS[...] 取，这里是唯一来源；
# 键名必须与 Field 的 key 完全一致（含点号路径，如 "flat.xzMotion"），
# 平台读取设置时用它补齐缺失项，所以这里少了键会直接 KeyError。

# ------ 默认值 ------ #

DEFAULT_SETTINGS = {
    # 示例字段：与 schema.py 里的 someNumber 对应（无单位，示例用）
    "someNumber": 1.0,
}
