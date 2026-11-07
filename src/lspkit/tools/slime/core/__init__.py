# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-07                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 核心算法包               #
# =================================== #
"""
史莱姆区块查找器的纯计算层：只做 numpy 运算，不依赖平台、不读写状态。

模块分工（自底向上）：
- seed.py     ：种子解析（十进制 long / Java String.hashCode）；
- mask.py     ：单区块史莱姆判定与矩形位图，复刻 Java 的 32 位 int 溢出；
- ring.py     ：24..128 格圆环权重表，17×17 区块 × 16×16 块内偏移；
- score.py    ：掩码与权重表的互相关、候选挑选、NMS、块内 256 点精修；
- search.py   ：分块精确扫描（scan_exact）与采样 + 爬山（scan_sample）。

数据约定：位图/得分图的行是 Z、列是 X，即 arr[z, x]；对外结果里的方块坐标
与区块坐标（floor(方块 / 16)）由 search._make_result() 统一换算。
"""
