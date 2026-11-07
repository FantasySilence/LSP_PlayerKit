# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: TNT 数量微调             #
# =================================== #

# TNT 数量微调：把初解 (蓝, 红) 的每个轴各自加上一组偏移，生成全部候选组合，
# 并剔除出现负数的组合；求解器再从候选中挑落点误差最小的一组。
from __future__ import annotations

import itertools

import numpy as np


# ------ 组合枚举 ------ #
def generate_combinations(base: np.ndarray, modifiers=range(-2, 3)) -> np.ndarray:
    """在初解附近枚举所有偏移组合。

    参数:
        base: 初解，形状 (n,) 的整数数组（如 [蓝, 红]），单位个。
        modifiers: 每轴可加的偏移集合，默认 -2..+2（5 档）；抛射传 ±10（21 档）。

    返回:
        形状 (m, n) 的整数数组，每行一组候选当量；已剔除任一维为负的行。
        组合总数至多 len(modifiers) ** n（平射 25、抛射 441），过滤后只会更少。

    说明:
        负数当量摆不出来（旧版同样不允许），所以 m 可能小于组合总数。
    """

    # 先做笛卡尔积（每轴独立取偏移），再与初解逐轴相加。
    combos = list(itertools.product(modifiers, repeat=len(base)))
    results = np.array([[x + y for x, y in zip(base, combo)] for combo in combos])
    # 只保留所有轴都非负的行，负当量直接丢弃。
    return results[results.min(axis=1) >= 0]
