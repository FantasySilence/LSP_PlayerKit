# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 真实 Win32 注入测试       #
#            （默认跳过，需交互桌面）  #
# =================================== #

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

pytestmark = [
    pytest.mark.win32gui,
    pytest.mark.skipif(
        not ENABLED,
        reason="需要交互桌面：设置 LSPKIT_GUI_TEST=1 后手动运行（会短暂抢占焦点）",
    ),
]


def make_config(**kwargs) -> InputConfig:
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
    chat = ChatStub().start()
    try:
        yield chat
    finally:
        chat.stop()


@pytest.fixture()
def transport(stub):
    win = Win32Transport()
    info = win.find_window((), WINDOW_CLASS)
    assert info is not None, "没有找到测试窗口"

    deadline = time.time() + 5
    while time.time() < deadline and win.foreground() != int(info.hwnd):
        win.activate(info.hwnd)
        time.sleep(0.2)
    assert win.foreground() == int(info.hwnd), "测试窗口没有拿到前台焦点"
    time.sleep(0.5)
    return win


def test_real_injection_roundtrip(transport, stub):
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
    runner = CommandRunner(config=make_config(), transport=transport)
    report_box: list = []
    worker = threading.Thread(
        target=lambda: report_box.append(runner.run(["/say lag"])), daemon=True
    )
    worker.start()

    # 让 Tk 主线程在粘贴前后卡住 1.2 秒：执行器应按「不可信」处理并整条重来
    time.sleep(0.32)
    stub.stall(1.2)
    worker.join(timeout=40)

    assert report_box, "执行线程没有结束"
    report = report_box[0]
    assert not report.aborted
    assert stub.lines() == ["/say lag"], "重试后只应留下一条完整命令"


def test_real_esc_aborts(transport, stub):
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
