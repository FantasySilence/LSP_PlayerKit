# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-05                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Description: 珍珠炮主炮配置信息记录  #
# =================================== #

# ------ 写在前面的信息 ------ #
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

    @staticmethod
    def make_config_info_for_common_cannon(config_info: dict) -> None:

        """
        config_info: 例如
        config_info = {
            "destination": 湾雅, "coordinate": [887, -189],
            "direction": 东, "blue": 913, "red": 612
        }
        """

        print(config_info["destination"])
        print(
            "坐标: %d, %d" % (
                config_info["coordinate"][0], config_info["coordinate"][1]
            )
        )
        print("配置信息: ")
        print("方向: %s" % config_info["direction"])
        print("蓝色阵列TNT数量: %d" % config_info["blue"])
        print("红色阵列TNT数量: %d" % config_info["red"])


if __name__ == "__main__":

    print(banner)
    print("如果您已经了解，请按下回车键......")
    input()

    while True:
        print("=" * 15)
        print("配置信息生成")
        print("=" * 15)
        print("输入目的地名称（例：湾雅）：")
        destination = input()
        print("输入坐标(a, b)（例：(887, -189)，带括号与英文逗号）：")
        coordinate = list(eval(input()))
        print("输入方向（例：东）：")
        direction = input()
        print("输入蓝色阵列TNT数量（整数，例：913）：")
        blue = int(input())
        print("输入红色阵列TNT数量（整数，例：612）：")
        red = int(input())
        print("-" * 15)
        config_info = {
            "destination": destination, "coordinate": coordinate,
            "direction": direction, "blue": blue, "red": red
        }
        MainCannonConfigInfoMaker.make_config_info_for_common_cannon(config_info)
        print("-" * 15)
        print("是否继续(Y/N，例：N 退出)：")
        if input().lower() == "n":
            break
        else:
            continue
