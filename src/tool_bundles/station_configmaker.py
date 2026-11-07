# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Description: 假人搬货站点配置生成器  #
# =================================== #
# 本文件职责：交互式命令行小工具，逐项录入站点后生成「假人搬货」可直接导入的 JSON。
# 生成的字段结构必须与 src/lspkit/tools/puppet/schema.py 里的站点定义保持一致。

import json
import os
import re
import sys


# ------ 写在前面的信息 ------ #
# banner 是启动时原样打印的说明（ASCII 标题 + 使用提示），不参与任何计算
banner = """

====================================================================================================
   _____ _        _   _              _____             __ _       __  __       _             
  / ____| |      | | (_)            / ____|           / _(_)     |  \/  |     | |            
 | (___ | |_ __ _| |_ _  ___  _ __ | |     ___  _ __ | |_ _  __ _| \  / | __ _| | _____ _ __ 
  \___ \| __/ _` | __| |/ _ \| '_ \| |    / _ \| '_ \|  _| |/ _` | |\/| |/ _` | |/ / _ \ '__|
  ____) | || (_| | |_| | (_) | | | | |___| (_) | | | | | | | (_| | |  | | (_| |   <  __/ |   
 |_____/ \__\__,_|\__|_|\___/|_| |_|\_____\___/|_| |_|_| |_|\__, |_|  |_|\__,_|_|\_\___|_|   
                                                             __/ |                           
                                                            |___/                            
----------------------------------------------------------------------------------------------------
  逐项输入分组 tag、站点名称、维度、坐标与前缀，生成「假人搬货」可以直接导入的 JSON 文件。
  分组 tag 会显示在下拉框和站点列表里，方便按工业区归类。
  生成后打开应用 → 假人搬货 → 站点「导入」，选中这个文件即可。

  Powered By 御河DE天街
  Github: https://github.com/FantasySilence/LSP_PlayerKit
====================================================================================================
"""

# ------ 维度：输入编号或英文名都行 ------ #
# 键是用户输入的编号；值的第一项是配置里的维度 id，第二项是给它看的中文名
DIMENSIONS = {
    "1": ("overworld", "主世界"),
    "2": ("the_nether", "下界"),
    "3": ("the_end", "末地"),
}
# 反向索引：维度 id → 中文名，用于结果回显
DIMENSION_NAMES = {value[0]: value[1] for value in DIMENSIONS.values()}

# 站点前缀会拼进假人名，因此限制为 1–12 个字母/数字/下划线
PREFIX_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,12}$")
# 备注长度上限（字符数），与主程序里站点备注的校验保持一致
NOTE_MAX = 60


class StationConfigMaker:

    """
    生成假人搬货的站点配置文件
    项目打包指令: pyinstaller packaging\\StationConfigMaker.spec --noconfirm
    """

    @staticmethod
    def get_user_input(data_type=float):

        """
        读取一行输入并按 data_type 转换，格式不符时提示后重新读取
        """

        # 转不成目标类型就一直重问（命令行工具没有“取消”这个概念）
        while True:
            try:
                return data_type(input())
            except ValueError:
                print("格式不正确，请重新输入...")

    @staticmethod
    def ask_dimension() -> str:

        """
        选择维度，返回 overworld / the_nether / the_end
        """

        print("请选择维度（1 = 主世界，2 = 下界，3 = 末地，例：1）：")
        while True:
            raw = input().strip()
            # 先按编号查（1/2/3）
            if raw in DIMENSIONS:
                return DIMENSIONS[raw][0]
            # 再逐个比对英文维度 id，允许直接输 overworld 这类写法
            for value in DIMENSIONS.values():
                if raw == value[0]:
                    return value[0]
            print("只能输入 1 / 2 / 3，或 overworld / the_nether / the_end：")

    @staticmethod
    def ask_station(existing: list) -> dict:

        """
        逐项读取一个站点；前缀重复时要求重新输入
        """

        print("请输入分组 tag（例：永夜岛工业区；可留空，不能包含空格）：")
        # 分组 tag 可以为空；非空时限制 32 字符且不能有空格/制表符
        while True:
            group = input().strip()
            if not group or (len(group) <= 32 and " " not in group and "\t" not in group):
                break
            print("分组 tag 不能包含空格，且不超过 32 个字符。")

        while True:
            print("请输入站点名称（例：混凝土工厂）：")
            name = input().strip()
            if not name:
                print("名称不能为空。")
                continue
            if len(name) > 64:
                print("名称不能超过 64 个字符。")
                continue
            break

        dimension = StationConfigMaker.ask_dimension()

        print("请输入 X 坐标（可带小数与负号，例：136）：")
        # 坐标单位是“格”（方块坐标），允许小数，方便对准发射器/落点
        x = StationConfigMaker.get_user_input()

        print("请输入 Y 坐标（可带小数，例：48）：")
        y = StationConfigMaker.get_user_input()

        print("请输入 Z 坐标（可带小数与负号，例：8）：")
        z = StationConfigMaker.get_user_input()

        # 前缀必须唯一：它会被拼进假人名，重复会让两个站点抢同一批假人
        used = {station["prefix"] for station in existing}
        while True:
            print("请输入站点前缀（2–4 个字符最佳，只能用字母/数字/下划线，例：con）：")
            prefix = input().strip()
            if not PREFIX_PATTERN.match(prefix):
                print("前缀只能用字母、数字、下划线，且不超过 12 个字符。")
                continue
            if prefix in used:
                print("这个前缀已经用过了，换一个（前缀会拼进假人名，必须唯一）。")
                continue
            break

        print("请输入备注（可留空，直接回车；最多 %d 个字符）：" % NOTE_MAX)
        while True:
            note = input().strip()
            if len(note) > NOTE_MAX:
                print("备注不能超过 %d 个字符，请重新输入：" % NOTE_MAX)
                continue
            break

        # id 直接用前缀：导出后站点标识稳定且唯一，主程序不用再生成一遍
        return {
            "id": prefix,
            "name": name,
            "group": group,
            "prefix": prefix,
            "dimension": dimension,
            "x": x,
            "y": y,
            "z": z,
            # 备注再截断一次：即使用户手改过输入，也不会超过主程序的长度限制
            "note": note[:NOTE_MAX],
        }

    @staticmethod
    def output_dir() -> str:

        """
        设置文件的写出目录：打包后取 exe 所在目录，源码运行时取本文件目录
        """

        # 打包后 sys.frozen 为 True：输出到 exe 旁边，用户一眼就能找到
        if getattr(sys, "frozen", False):
            return os.path.dirname(os.path.abspath(sys.executable))
        # 源码运行：输出到本文件所在目录，方便开发时查看生成结果
        return os.path.dirname(os.path.abspath(__file__))

    @staticmethod
    def write_file(stations: list, filename: str) -> str:

        """
        写出 JSON（4 空格缩进，保留中文），返回文件路径
        """

        # 顶层用 version 字段给格式升级留余地；stations 是站点数组
        payload = {"version": 1, "stations": stations}
        path = os.path.join(StationConfigMaker.output_dir(), filename)
        with open(path, "w", encoding="utf-8") as file:
            # ensure_ascii=False：中文站名保持可读，不会写成 \uXXXX 转义
            json.dump(payload, file, ensure_ascii=False, indent=4)
            # 末尾补一个换行，符合文本文件的惯例
            file.write("\n")
        print("站点配置文件已保存至 %s" % path)
        print("共 %d 个站点；在应用里打开「假人搬货 → 导入」选择该文件即可。" % len(stations))
        return path


if __name__ == "__main__":

    # 交互脚本：先展示说明，回车之后才开始逐台录入站点
    print(banner)
    print("如果您已经了解，请按下回车键......")
    input()

    # 逐台录入；已录入的站点会传进去用于前缀查重
    stations = []
    while True:
        station = StationConfigMaker.ask_station(stations)
        stations.append(station)
        print(
            "已添加：%s（%s，前缀 %s）"
            % (
                (station["group"] + "·" if station["group"] else "") + station["name"],
                DIMENSION_NAMES[station["dimension"]],
                station["prefix"],
            )
        )
        print("-" * 67)

        print("还要继续添加站点吗？（Y/N，例：Y）：")
        # 只有明确输入 y 才继续；直接回车或其它输入都结束录入
        if input().strip().lower() != "y":
            break

    print("请为站点配置文件命名（例：stations_永夜岛，无需写 .json）：")
    # 直接回车就用默认名 stations.json；用户自己写了后缀就不再重复添加
    filename = input().strip() or "stations"
    if not filename.endswith(".json"):
        filename += ".json"

    StationConfigMaker.write_file(stations, filename)
