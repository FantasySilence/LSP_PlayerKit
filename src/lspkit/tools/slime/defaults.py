# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-07                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 史莱姆区块查找器默认设置 #
# =================================== #

from .constants import DEFAULT_EXACT_CHUNKS, DEFAULT_PERIMETER_CHUNKS

DEFAULT_SETTINGS = {
    "seed": "0",
    "centerX": -32,
    "centerZ": -8,
    "exactLimit": DEFAULT_EXACT_CHUNKS,
    "perimeterChunks": DEFAULT_PERIMETER_CHUNKS,
    "ringInner": 24,
    "ringOuter": 128,
    "simDistance": 8,
    "topN": 100,
    "nmsChunks": 8,
    "mode": "auto",
    "samples": 50_000,
}
