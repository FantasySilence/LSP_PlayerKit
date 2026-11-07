# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 真实 Win32 注入测试       #
#            （默认跳过，需交互桌面）  #
# =================================== #
# 测试层：platform.autoinput.Win32Transport 的真实端到端注入。
# 策略：启动真实 Tk 迷你聊天栏，用 SendInput 把命令打进输入框，再核对收到的行；
# 默认 skip（需要交互桌面，会短暂抢占焦点），只有 LSPKIT_GUI_TEST=1 且 Windows 才跑。

import os
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness.mc_chat_stub import WINDOW_CLASS, ChatStub  # noqa: E402

from lspkit.platform.autoinput import (  # noqa: E402
    CommandRunner,
    InputConfig,
    Win32Transport,
)

ENABLED = os.environ.get("LSPKIT_GUI_TEST") == "1" and sys.platform == "win32"
# 必须显式设置环境变量才启用：CI / 无桌面会话没有可激活的窗口，强跑会失败或抢焦点。

# win32gui 是自定义 marker；skipif 给出可操作的原因，而不是笼统的「平台不匹配」。
pytestmark = [
    pytest.mark.win32gui,
    pytest.mark.skipif(
        not ENABLED,
        reason="需要交互桌面：设置 LSPKIT_GUI_TEST=1 后手动运行（会短暂抢占焦点）",
    ),
]


def make_config(**kwargs) -> InputConfig:
    """测试用 InputConfig：目标窗口类换成 TkTopLevel，时序放宽到真实窗口能处理.

    command_interval/chat_open_wait/input_wait 都调到 0.15~0.2s，
    避免 Tk 事件循环来不及处理按键；max_attempts=3 与生产默认一致。
    """
    base = dict(
        window_class=WINDOW_CLASS,
        start_delay=0.0,
        require_focus=True,
        command_interval=0.15,
        chat_open_wait=0.2,
        input_wait=0.15,
        max_attempts=3,
        restore_clipboard=True,
        log_time=False,
    )
    base.update(kwargs)
    return InputConfig(**base)


@pytest.fixture()
def stub():
    """启动迷你聊天栏，测试结束后无论成败都 stop() 回收 Tk 线程."""
    chat = ChatStub().start()
    try:
        yield chat
    finally:
        chat.stop()


@pytest.fixture()
def transport(stub):
    """创建真实 Win32Transport，找到 stub 窗口并确保它在前台.

    最多等 5 秒拿焦点；拿到后再等 0.5 秒，让 Tk 完成首次布局与事件处理。
    """
    win = Win32Transport()
    info = win.find_window((), WINDOW_CLASS)
    # 按窗口类名查找，与生产代码识别 GLFW30/LWJGL 走同一条路径。
    assert info is not None, "没有找到测试窗口"

    deadline = time.time() + 5
    # SetForegroundWindow 可能被系统短暂拒绝，循环重试直到前台句柄匹配。
    while time.time() < deadline and win.foreground() != int(info.hwnd):
        win.activate(info.hwnd)
        time.sleep(0.2)
    assert win.foreground() == int(info.hwnd), "测试窗口没有拿到前台焦点"
    time.sleep(0.5)
    return win


def test_real_injection_roundtrip(transport, stub):
    """验证真实注入能把三条命令完整写进聊天栏.

    输入：/say、长 execute spawn、/player kill 各一条。
    期望：sent=3、未中断，且 stub 收到的行与输入逐字相同（顺序也一致）。
    """
    commands = [
        "/say hello",
        "/execute in minecraft:overworld run player bot_all_vil_1 spawn at 567 102 -595",
        "/player bot_all_vil_1 kill",
    ]
    runner = CommandRunner(config=make_config(), transport=transport)
    report = runner.run(commands)

    assert report.sent == 3
    assert not report.aborted
    assert stub.lines() == commands


def test_real_hang_is_detected_and_retried(transport, stub):
    """验证真实卡顿时执行器会整条重来，不留下半截命令.

    输入：一条 /say lag；执行到输入阶段时让 Tk 主线程阻塞 1.2 秒。
    期望：线程在 40 秒内结束、未中断；聊天栏最终只有一条完整的 "/say lag"。
    """
    runner = CommandRunner(config=make_config(), transport=transport)
    report_box: list = []
    worker = threading.Thread(
        target=lambda: report_box.append(runner.run(["/say lag"])), daemon=True
    )
    worker.start()

    # 让 Tk 主线程在粘贴前后卡住 1.2 秒：执行器应按「不可信」处理并整条重来
    time.sleep(0.32)
    # 0.32s 让执行器先进入粘贴/回探阶段，再注入卡顿，才能命中「输入后回探」。
    stub.stall(1.2)
    worker.join(timeout=40)

    assert report_box, "执行线程没有结束"
    report = report_box[0]
    assert not report.aborted
    # 只允许一条完整命令：重试不能把半截内容或重复内容留在聊天栏。
    assert stub.lines() == ["/say lag"], "重试后只应留下一条完整命令"


def test_real_esc_aborts(transport, stub):
    """验证真实 ESC 能在命令之间中断执行.

    输入：8 条命令、command_interval=0.5s；0.6s 后按住 ESC 0.3s。
    期望：线程结束、report.aborted=True，sent<8（不会把 8 条全发完）。
    """
    runner = CommandRunner(
        config=make_config(command_interval=0.5), transport=transport
    )
    report_box: list = []
    worker = threading.Thread(
        target=lambda: report_box.append(
            runner.run([f"/say {index}" for index in range(8)])
        ),
        daemon=True,
    )
    worker.start()
    time.sleep(0.6)
    transport.tap("esc", 0.3)
    worker.join(timeout=40)

    assert report_box, "执行线程没有结束"
    report = report_box[0]
    assert report.aborted
    assert report.sent < 8
