# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 材料换算纯计算           #
# =================================== #
# 本包只放纯函数与静态数据，不 import webview、不读写文件、不碰设置存储，
# 因此可以脱离界面单独调用与测试。模块分工：
#   parse.py     清单文本 / 已解析条目 → 统一的 {name, count} 列表
#   convert.py   数量 → 潜影盒 / 组 / 个
#   packing.py   数量 → 最少盒数的装填方案
#   litematic.py .litematic 二进制 → 材料条目（gzip + NBT + 方块索引解包）
#   localize.py  物品 ID → 当前语言显示名（查表顺序见文件内说明）
#   block_names.py / block_items.py  脚本生成的静态数据表，不要手改
# 依赖方向是单向的：actions → core → 常量与数据表。
