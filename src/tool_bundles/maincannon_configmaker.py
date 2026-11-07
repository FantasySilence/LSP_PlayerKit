# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-05                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Description: 珍珠炮主炮配置信息记录  #
# =================================== #
# 本文件职责：交互式命令行小工具，把一次炮击的目的地 / 坐标 / 方向 / TNT 数量整理成文本。
# 不写文件，只把结果打印出来，方便直接复制进群公告或存档。

# ------ 写在前面的信息 ------ #
# banner 是启动时原样打印的说明（ASCII 标题 + 使用提示），不参与任何计算
banner = """

========================================================================================================================
  __  __       _        _____                               _____             __ _       __  __       _             
 |  \/  |     (_)      / ____|                             / ____|           / _(_)     |  \/  |     | |            
 | \  / | __ _ _ _ __ | |     __ _ _ __  _ __   ___  _ __ | |     ___  _ __ | |_ _  __ _| \  / | __ _| | _____ _ __ 
 | |\/| |/ _` | | '_ \| |    / _` | '_ \| '_ \ / _ \| '_ \| |    / _ \| '_ \|  _| |/ _` | |\/| |/ _` | |/ / _ \ '__|
 | |  | | (_| | | | | | |___| (_| | | | | | | | (_) | | | | |___| (_) | | | | | | | (_| | |  | | (_| |   <  __/ |   
 |_|  |_|\__,_|_|_| |_|\_____\__,_|_| |_|_| |_|\___/|_| |_|\_____\___/|_| |_|_| |_|\__, |_|  |_|\__,_|_|\_\___|_|   
                                                                                    __/ |                           
                                                                                   |___/                            
------------------------------------------------------------------------------------------------------------------------
  输入目的地名称、坐标、方向与蓝色 / 红色阵列 TNT 数量，
  输出排版好的配置文本，方便发公告、存档或复制到聊天框。

  Powered By 御河DE天街
  Github: https://github.com/FantasySilence/LSP_PlayerKit
========================================================================================================================
"""


class MainCannonConfigInfoMaker:

    """
    用于生成珍珠炮主炮配置信息记录
    项目打包指令: pyinstaller packaging\\MainCannonConfigMaker.spec --noconfirm
    """

    # 输出一律走 print：这个脚本的产物是“排版好的文本”，直接复制粘贴用，不返回给程序加工

    @staticmethod
    def make_config_info_for_common_cannon(config_info: dict) -> None:

        """
        config_info: 例如
        config_info = {
            "destination": 湾雅, "coordinate": [887, -189],
            "direction": 东, "blue": 913, "red": 612
        }
        """

        # 第一行只打印目的地名称，方便在聊天记录里一眼定位这是哪门炮的配置
        print(config_info["destination"])
        # %d 按整数输出坐标（脚本约定坐标就是整数格）
        print(
            "坐标: %d, %d" % (
                config_info["coordinate"][0], config_info["coordinate"][1]
            )
        )
        print("配置信息: ")
        # 方向既可能是 东/南/西/北，也可能是 001 这类编号，脚本原样输出、不解释含义
        print("方向: %s" % config_info["direction"])
        print("蓝色阵列TNT数量: %d" % config_info["blue"])
        print("红色阵列TNT数量: %d" % config_info["red"])


if __name__ == "__main__":

    # 交互脚本：先展示说明，回车之后才开始录入配置
    print(banner)
    print("如果您已经了解，请按下回车键......")
    input()

    # 一个循环就是一条完整记录：录完打印出来，再问是否继续
    while True:
        print("=" * 15)
        print("配置信息生成")
        print("=" * 15)
        print("输入目的地名称（例：湾雅）：")
        destination = input()
        print("输入坐标(a, b)（例：(887, -189)，带括号与英文逗号）：")
        # eval 直接把 "(887, -189)" 当元组解析：本机自用脚本图省事，不校验输入内容
        coordinate = list(eval(input()))
        print("输入方向（例：东）：")
        direction = input()
        print("输入蓝色阵列TNT数量（整数，例：913）：")
        blue = int(input())
        print("输入红色阵列TNT数量（整数，例：612）：")
        # 蓝/红对应炮的两侧阵列，数量直接照抄游戏里数出来的 TNT 个数
        red = int(input())
        print("-" * 15)
        config_info = {
            "destination": destination, "coordinate": coordinate,
            "direction": direction, "blue": blue, "red": red
        }
        MainCannonConfigInfoMaker.make_config_info_for_common_cannon(config_info)
        print("-" * 15)
        print("是否继续(Y/N，例：N 退出)：")
        # 只有输入 n 才退出；其它任何输入（含直接回车）都继续下一轮
        if input().lower() == "n":
            break
        else:
            continue
