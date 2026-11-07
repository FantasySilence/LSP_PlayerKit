# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-05                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Description: 边境炮配置信息记录      #
# =================================== #
# 本文件职责：交互式命令行小工具，把边境炮的目的地 / 坐标 / 方向 / 三组 TNT 数量整理成文本。
# 不写文件，只把结果打印出来，方便直接复制进群公告或存档。

# ------ 写在前面的信息 ------ #
# banner 是启动时原样打印的说明（ASCII 标题 + 使用提示），不参与任何计算
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

    # 输出一律走 print：这个脚本的产物是“排版好的文本”，直接复制粘贴用，不返回给程序加工

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

        # 第一行只打印目的地名称，方便在聊天记录里一眼定位这是哪个边境炮的配置
        print(config_info["destination"])
        print(
            "坐标: %d, %d" % (
                config_info["coordinate"][0], config_info["coordinate"][1]
            )
        )
        print("配置信息: ")
        # 方向用 001/002 这类编号表示，脚本原样输出、不解释含义
        print("方向: %s" % config_info["direction"])
        print("第一个TNT数量: ")
        # 口径：小头 = 单个阵列铺的 TNT 数，大头 = 阵列的倍数（显示成 xN）
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

    # 交互脚本：先展示说明，回车之后才开始录入配置
    print(banner)
    print("如果您已经了解，请按下回车键......")
    input()

    # 一个循环就是一条完整记录：录完打印出来，再问是否继续
    while True:
        print("=" * 15)
        print("配置信息生成")
        print("=" * 15)
        print("输入目的地名称（例：边境工业区总部）：")
        destination = input()
        print("输入坐标(a, b)（例：(3750000, 3750000)，带括号与英文逗号）：")
        # eval 直接把 "(3750000, 3750000)" 当元组解析：本机自用脚本图省事，不校验内容
        coordinate = list(eval(input()))
        print("输入方向（例：001）：")
        direction = input()
        print("输入第一个TNT配置信息：")
        print("小头数量（整数，例：512）：")
        first_small_head = int(input())
        print("大头数量（整数，例：1）：")
        # 大头是“倍数”：实际用量 = 小头 × 大头（例：512 × 1）
        first_big_head = int(input())
        first_TNT = {
            "small_head": first_small_head, "big_head": first_big_head
        }
        print("输入第二个TNT配置信息：")
        print("小头数量（整数，例：512）：")
        # 第二、三组 TNT 与小头/大头口径完全相同，只是打到不同的阵列位置
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
        # 只有输入 n 才退出；其它任何输入（含直接回车）都继续下一轮
        if input().lower() == "n":
            break
        else:
            continue
