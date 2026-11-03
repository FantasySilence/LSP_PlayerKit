# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: TNT 数量微调             #
# =================================== #

from __future__ import annotations

import itertools

import numpy as np


def generate_combinations(base: np.ndarray, modifiers=range(-2, 3)) -> np.ndarray:
    combos = list(itertools.product(modifiers, repeat=len(base)))
    results = np.array([[x + y for x, y in zip(base, combo)] for combo in combos])
    return results[results.min(axis=1) >= 0]
