# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 边境炮落点预测           #
# =================================== #

# 边境炮落点预测：按 3 轴初动量逐 gt 递推，直到 Y 掉到判定高度以下，再给出落点与耗时。
from __future__ import annotations

# 判定高度（Y=256，与默认炮口同层）。注意 constants.py 里也有同值常量 LANDING_Y，
# 本文件没有导入它；两处必须保持一致，改一处就要同步另一处。
LANDING_Y = 256.0


# ------ 轨迹递推 ------ #
def trace(
    x_motion: float,
    y_motion: float,
    z_motion: float,
    origin: tuple[float, float, float],
    landing_y: float = LANDING_Y,
) -> dict:
    """
    逐 gt 递推，直到珍珠落到 landing_y 以下.

    返回 points（[tick, x, y, z]）与 landing（最后一刻的位置）.
    """

    # 参数: 三轴初动量（方块/gt）与炮口坐标（方块）、落地判定高度（方块）；
    # 返回 points（每项 [gt, x, y, z]）与 landing（最后一刻的位置与 gt）。
    # 位置用 float 保存，避免整数坐标把小数动量吃掉。
    x, y, z = (float(v) for v in origin)
    tick = 0
    points = [[tick, x, y, z]]

    # while True 保证至少走一 gt：即使初始 Y 已在判定高度以下，也会先移动再停。
    while True:
        # 先用上一 gt 的速度位移，再按阻尼 / 重力更新速度。
        x = x + x_motion
        y = y + y_motion
        z = z + z_motion
        # 注意垂直是 0.99 * (v - 0.03)：先减重力再乘阻尼，与 pearl trace 的
        # 0.99 * v - 0.03 次序不同（终端速度分别是 -2.97 与 -3）；两边都按旧版原样保留。
        x_motion = 0.99 * x_motion
        y_motion = 0.99 * (y_motion - 0.03)
        z_motion = 0.99 * z_motion
        tick += 1
        points.append([tick, x, y, z])
        # 严格小于：y 正好等于判定高度时继续飞（与旧版一致）。
        if y < landing_y:
            break

    return {
        "points": points,
        "landing": {"x": x, "y": y, "z": z, "ticks": tick},
    }


# ------ 取点与落点摘要 ------ #
def position_at(points: list[list[float]], tick: int) -> dict | None:
    """
    取轨迹中某一 gt 的位置；该时刻已经落地（超出轨迹）则返回 None.
    """

    # 列表下标就是 gt：points[i] 存 [tick, x, y, z]，所以 t 直接从下标得来。
    index = int(tick)
    if index < 0 or index >= len(points):
        return None
    point = points[index]
    return {"tick": index, "x": point[1], "y": point[2], "z": point[3]}


def predict(
    x_motion: float,
    y_motion: float,
    z_motion: float,
    origin: tuple[float, float, float],
    landing_y: float = LANDING_Y,
) -> dict:
    """只给出落点 X / Z 与落地耗时，供解码文本使用。

    参数:
        x_motion: 三颗 TNT 合成的总 X 动量，单位方块/gt。
        y_motion: 总 Y 动量，单位方块/gt。
        z_motion: 总 Z 动量，单位方块/gt。
        origin: 炮口坐标 (x, y, z)，单位方块。
        landing_y: 落地判定高度，单位方块。

    返回:
        {"x": 落点 X, "z": 落点 Z, "ticks": 落地耗时（gt）}；坐标单位方块。

    说明:
        丢弃了 Y 与完整轨迹：解码文案只需要水平落点和耗时。
    """

    landing = trace(x_motion, y_motion, z_motion, origin, landing_y)["landing"]
    return {"x": landing["x"], "z": landing["z"], "ticks": landing["ticks"]}
