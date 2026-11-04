# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-05                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Description: 边境炮配置信息记录      #
# =================================== #

# ------ 写在前面的信息 ------ #
banner = """

================================================================================================================================
  ____                _            _____                               _____             __ _       __  __       _             
 |  _ \              | |          / ____|                             / ____|           / _(_)     |  \/  |     | |            
 | |_) | ___  _ __ __| | ___ _ __| |     __ _ _ __  _ __   ___  _ __ | |     ___  _ __ | |_ _  __ _| \  / | __ _| | _____ _ __ 
 |  _ < / _ \| '__/ _` |/ _ \ '__| |    / _` | '_ \| '_ \ / _ \| '_ \| |    / _ \| '_ \|  _| |/ _` | |\/| |/ _` | |/ / _ \ '__|
 | |_) | (_) | | | (_| |  __/ |  | |___| (_| | | | | | | | (_) | | | | |___| (_) | | | | | | | (_| | |  | | (_| |   <  __/ |   
 |____/ \___/|_|  \__,_|\___|_|   \_____\__,_|_| |_|_| |_|\___/|_| |_|\_____\___/|_| |_|_| |_|\__, |_|  |_|\__,_|_|\_\___|_|   
                                                                                               __/ |                           
                                                                                              |___/                            
--------------------------------------------------------------------------------------------------------------------------------
  输入目的地名称、坐标、方向与三组 TNT 的小头 / 大头数量，
  输出排版好的配置文本，方便发公告、存档或复制到聊天框。

  Powered By 御河DE天街
  Github: https://github.com/FantasySilence/LSP_PlayerKit
================================================================================================================================
"""


class BorderCannonConfigMaker:

    """
    用于生成边界炮配置信息记录
    项目打包指令: pyinstaller packaging\\BorderCannonConfigMaker.spec --noconfirm
    """

    @staticmethod
    def make_config_info_for_border_cannon(config_info: dict) -> None:

        """
        config_info: 例如
        config_info = {
            "destination": "边境工业区总部", "coordinate": [3750000, 3750000],
            "direction": "001", 
            "first_TNT": {
                "small_head": 512, "big_head": 1
            }, 
            "second_TNT": {
                "small_head": 512, "big_head": 78
            }, "third_TNT": {
                "small_head": 0, "big_head": 0
            }
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
        print("第一个TNT数量: ")
        print(
            "小头: %d, 大头: x%d" % (
                config_info["first_TNT"]["small_head"], 
                config_info["first_TNT"]["big_head"]
            )
        )
        print("第二个TNT数量: ")
        print(
            "小头: %d, 大头: x%d" % (
                config_info["second_TNT"]["small_head"], 
                config_info["second_TNT"]["big_head"]
            )
        )
        print("第三个TNT数量: ")
        print(
            "小头: %d, 大头: x%d" % (
                config_info["third_TNT"]["small_head"], 
                config_info["third_TNT"]["big_head"]
            )
        )

        
if __name__ == "__main__":

    print(banner)
    print("如果您已经了解，请按下回车键......")
    input()

    while True:
        print("=" * 15)
        print("配置信息生成")
        print("=" * 15)
        print("输入目的地名称（例：边境工业区总部）：")
        destination = input()
        print("输入坐标(a, b)（例：(3750000, 3750000)，带括号与英文逗号）：")
        coordinate = list(eval(input()))
        print("输入方向（例：001）：")
        direction = input()
        print("输入第一个TNT配置信息：")
        print("小头数量（整数，例：512）：")
        first_small_head = int(input())
        print("大头数量（整数，例：1）：")
        first_big_head = int(input())
        first_TNT = {
            "small_head": first_small_head, "big_head": first_big_head
        }
        print("输入第二个TNT配置信息：")
        print("小头数量（整数，例：512）：")
        second_small_head = int(input())
        print("大头数量（整数，例：78）：")
        second_big_head = int(input())
        second_TNT = {
            "small_head": second_small_head, "big_head": second_big_head
        }
        print("输入第三个TNT配置信息：")
        print("小头数量（整数，例：0）：")
        third_small_head = int(input())
        print("大头数量（整数，例：0）：")
        third_big_head = int(input())
        third_TNT = {
            "small_head": third_small_head, "big_head": third_big_head
        }
        print("-" * 15)
        config_info = {
            "destination": destination, "coordinate": coordinate,
            "direction": direction, "first_TNT": first_TNT, 
            "second_TNT": second_TNT, "third_TNT": third_TNT
        }
        BorderCannonConfigMaker.make_config_info_for_border_cannon(config_info)
        print("-" * 15)
        print("是否继续(Y/N，例：N 退出)：")
        if input().lower() == "n":
            break
        else:
            continue
