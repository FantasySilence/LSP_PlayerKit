# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-05                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Description: 珍珠炮技术参数生成器    #
# =================================== #
# 本文件职责：交互式命令行小工具，把 /log projectiles full 的实测数据换算成珍珠炮设置 JSON。
# 产出的 JSON 由主程序的「珍珠炮」工具导入，字段结构见 build_settings()。

import os
import sys
import json
from typing import Type, TypeVar


# ------ 写在前面的信息 ------ #
# banner 是启动时原样打印的说明（ASCII 标题 + 使用提示），不参与任何计算
banner = """

===========================================================================================================
  _____                _  _____             __ _        _____                           _             
 |  __ \              | |/ ____|           / _(_)      / ____|                         | |            
 | |__) |__  __ _ _ __| | |     ___  _ __ | |_ _  __ _| |  __  ___ _ __   ___ _ __ __ _| |_ ___  _ __ 
 |  ___/ _ \/ _` | '__| | |    / _ \| '_ \|  _| |/ _` | | |_ |/ _ \ '_ \ / _ \ '__/ _` | __/ _ \| '__|
 | |  |  __/ (_| | |  | | |___| (_) | | | | | | | (_| | |__| |  __/ | | |  __/ | | (_| | || (_) | |   
 |_|   \___|\__,_|_|  |_|\_____\___/|_| |_|_| |_|\__, |\_____|\___|_| |_|\___|_|  \__,_|\__\___/|_|   
                                                  __/ |                                               
                                                 |___/                                                

                                                 
-----------------------------------------------------------------------------------------------------------
Powered By 御河DE天街
Github: https://github.com/FantasySilence/LSP_PlayerKit

欢迎使用珍珠炮技术参数JSON文件生成器。
使用这个生成器生成的JSON文件将作为珍珠炮配置器的设置文件，配置时导入即可
请确保在使用本生成器前，您的MC客户端能够在游戏中获取 /log projectiles full 指令的信息
===========================================================================================================
"""

# 泛型占位：让 get_user_input() 的返回值类型与传入的 data_type 保持一致
datatype = TypeVar('datatype')


class ConfigGenerator:

    """
    用于生成珍珠炮技术参数 JSON 设置文件
    由 /log projectiles full 的实测数据反推珍珠的 XZ 轴与 Y 轴动量
    项目打包指令: pyinstaller packaging\\ConfigGenerator.spec --noconfirm
    """

    @staticmethod
    def get_user_input(data_type: Type[datatype] = float) -> datatype:

        """
        读取一行输入并按 data_type 转换，格式不符时提示后重新读取
        """

        # 命令行工具没有“取消”，只能一直重问，直到用户给出能转换的值
        while True:
            try:
                return data_type(input())
            except ValueError:
                print("格式不正确，请重新输入...")

    @staticmethod
    def build_settings(config_info: dict) -> dict:

        """
        config_info: 例如
        config_info = {
            "is_eject": True, "max_tnt": 3640, "max_tnt_unit": 512,
            "x_init": -31.9375, "z_init": -8.0625,
            "flat": {
                "XZ_MOTION": 0.6025678975452006, "Y_MOTION": 1.204,
                "Y_INIT_MOTION": 0.0, "Y_INIT_POSITION": 64.0
            },
            "eject": {
                "XZ_MOTION": 0.6025678975452006, "Y_MOTION": 1.2,
                "Y_INIT_MOTION": -0.1, "Y_INIT_POSITION": 66.0
            }
        }
        """

        # 键名必须与主程序「珍珠炮」工具的设置 schema 一致，否则导入时识别不到
        settings = {
            "IS_EJECTION_AVAILABLE": config_info["is_eject"],
            "MAX_TNT": config_info["max_tnt"],
            "MAX_TNT_UNIT": config_info["max_tnt_unit"],
            "XZ_INIT_POSITION": {
                "X": config_info["x_init"],
                "Z": config_info["z_init"]
            },
            "MOTION_FOR_FLAT_FIRE": config_info["flat"]
        }
        # 没有抛射能力的炮不写抛射段，免得主程序读到一堆无意义的 0
        if config_info["is_eject"]:
            settings["MOTION_FOR_EJECTIONS"] = config_info["eject"]
        return settings

    @staticmethod
    def output_dir() -> str:

        """
        设置文件的写出目录：打包后取 exe 所在目录，源码运行时取本文件目录
        """

        if getattr(sys, "frozen", False):
            return os.path.dirname(os.path.abspath(sys.executable))
        return os.path.dirname(os.path.abspath(__file__))

    @staticmethod
    def make_config_file(config_info: dict, config_name: str) -> str:

        """
        写出 JSON 设置文件（4 空格缩进），返回文件路径
        """

        settings = ConfigGenerator.build_settings(config_info)
        # 文件名由用户输入后直接拼到输出目录下（本工具只在本机自用，不做额外路径校验）
        file_path = os.path.join(ConfigGenerator.output_dir(), config_name)
        with open(file_path, "w") as f:
            json.dump(settings, f, indent=4)
        print("配置文件已保存至 %s" % file_path)
        return file_path


if __name__ == "__main__":

    # 交互脚本：先展示说明，回车之后才开始逐项询问
    print(banner)
    print("如果您已经了解，请按下回车键......")
    input()

    print("请输入炮口的X坐标（可带小数与负号，例：-31.9375）：")
    x_init = ConfigGenerator.get_user_input()

    print("请输入炮口的Z坐标（可带小数与负号，例：-8.0625）：")
    z_init = ConfigGenerator.get_user_input()

    print("请输入您的珍珠炮单边最大TNT数量（整数，例：3640）：")
    # MAX_TNT 是单侧炮口能承受的最大 TNT 数，主程序用它反推需要多少阵列
    max_tnt = ConfigGenerator.get_user_input(int)

    print("请输入您的珍珠炮单个阵列的最大TNT数（整数，例：512）：")
    # MAX_TNT_UNIT 是“单个阵列”的上限，主程序用它把材料拆成若干个阵列
    max_tnt_unit = ConfigGenerator.get_user_input(int)

    print("请输入您的珍珠炮是否具有抛射的功能(Y/N，例：Y)：")
    # 只有输入 y（不区分大小写）才算“有抛射功能”，其它输入一律当作没有
    is_eject = input().lower() == "y"
    print()

    # ------ 平射模式的实测数据 ------ #
    # 先测“0 个 TNT”的基准：拿到开炮瞬间的 Y 位置与 Y 初速度，后面要减掉它们
    print("接下来请为您的珍珠炮配置0个TNT，并在MC中输入指令 /log projectiles full ")
    print("珍珠落地后，找到开炮的时刻，读取log信息...")
    print("-" * 67)
    if is_eject:
        print("首先将珍珠炮设置为平射模式，丢出珍珠...")

    print("请输入炮口的Y坐标（可带小数，例：64.0）：")
    y_init_f = ConfigGenerator.get_user_input()

    print("请输入开炮时刻珍珠的Y轴动量（可带小数与负号，例：0.0）：")
    # 单位是“格/tick”；向上为正、向下为负，这就是开炮瞬间的 Y 初速度
    y_init_motion_f = ConfigGenerator.get_user_input()

    # 再测“1 个 TNT”：与上面的基准相减，就得到单个 TNT 贡献的动量
    print("接下来，接下来请为您的珍珠炮配置1个TNT")
    print("请输入1个TNT赋予珍珠的XZ轴动量大小（正数，例：0.6025678975452006）：")
    xz_motion_f = ConfigGenerator.get_user_input()

    print("请输入1个TNT配置下珍珠的Y轴动量大小（可带小数，例：1.204）：")
    y1_motion_f = ConfigGenerator.get_user_input()

    flat = {
        # XZ 轴动量：1 个 TNT 直接给出的水平速度（单位：格/tick）
        "XZ_MOTION": xz_motion_f,
        # Y_MOTION 是“1 个 TNT 带来的净增量”：实测总动量减去开炮瞬间的初速度
        "Y_MOTION": y1_motion_f - y_init_motion_f,
        "Y_INIT_MOTION": y_init_motion_f,
        "Y_INIT_POSITION": y_init_f
    }

    print("-" * 67)
    print()

    # ------ 抛射模式的实测数据 ------ #
    # 只有具备抛射能力的炮才需要第二组数据；没有就留空字典
    eject = {}
    if is_eject:
        print("然后将珍珠炮设置为抛射模式并配置0个TNT...")

        print("请输入炮口的Y坐标（可带小数，例：66.0）：")
        y_init_e = ConfigGenerator.get_user_input()

        print("请输入开炮时刻珍珠的Y轴动量（可带小数与负号，例：-0.1）：")
        y_init_motion_e = ConfigGenerator.get_user_input()

        print("接下来，接下来请为您的珍珠炮配置1个TNT")
        # 与平射同理：先测 0 个 TNT 的基准，再测 1 个 TNT，两者相减得到净增量
        print("请输入1个TNT赋予珍珠的XZ轴动量大小（正数，例：0.6025678975452006）：")
        xz_motion_e = ConfigGenerator.get_user_input()

        print("请输入1个TNT配置下珍珠的Y轴动量大小（可带小数，例：1.1）：")
        y1_motion_e = ConfigGenerator.get_user_input()

        eject = {
            # 与平射相同：XZ 轴动量由 1 个 TNT 直接给出（格/tick）
            "XZ_MOTION": xz_motion_e,
            # 同样取“实测总动量 - 开炮瞬间初速度”，得到 1 个 TNT 的净增量
            "Y_MOTION": y1_motion_e - y_init_motion_e,
            "Y_INIT_MOTION": y_init_motion_e,
            "Y_INIT_POSITION": y_init_e
        }

        print("-" * 67)
        print()

    print("请为您的珍珠炮配置文件命名（例：pearl_-31.9375_-8.0625，无需写 .json）：")
    # 用户只输名字，这里统一补 .json 后缀（不做非法字符校验，本机自用）
    config_name = input() + ".json"

    config_info = {
        "is_eject": is_eject, "max_tnt": max_tnt, "max_tnt_unit": max_tnt_unit,
        "x_init": x_init, "z_init": z_init, "flat": flat, "eject": eject
    }
    ConfigGenerator.make_config_file(config_info, config_name)
