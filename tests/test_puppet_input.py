# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 自动输入执行器（假 Transport） #
# =================================== #
# 测试层：platform.autoinput 的 CommandRunner（纯执行器，不依赖 Windows）。
# 策略：用假 Transport + 虚拟时钟记录每次按键/剪贴板调用，断言调用时序与重试语义；
# 批间确认用自定义闸门；全程不碰真实键盘、不真实 sleep。

from lspkit.platform.autoinput import (
    CommandRunner,
    InputConfig,
    WindowInfo,
)

WINDOW = WindowInfo(hwnd=1, title="Minecraft 1.21.1", pid=4321, klass="GLFW30")
# 假的窗口信息：只作为 Transport 的身份句柄，不指向真实窗口。


class FakeTransport:
    """记录每一次注入，虚拟时钟避免真实等待."""

    def __init__(self):
        self.calls: list = []
        self.time = 0.0
        self.hwnd = WINDOW.hwnd
        self.foreground_hwnd = WINDOW.hwnd
        self.responsive_results: list = []
        self.responsive_default = True
        self.clipboard = "SENTINEL"
        self.clipboard_ok = True
        self.keys_down: set = set()
        self.unsupported: list = []
    # calls 按发生顺序记录 ("tap"/"clip"/"probe"...)；time 是虚拟时钟，sleep 只推进它。
    # responsive_results 非空时按队列依次返回，用来精确编排「卡顿/恢复」的时机。

    def find_window(self, patterns, klass):
        self.calls.append(("find", tuple(patterns), klass))
        return WINDOW if self.hwnd else None

    def is_window(self, hwnd):
        return self.hwnd is not None and hwnd == self.hwnd

    def foreground(self):
        return self.foreground_hwnd

    def activate(self, hwnd):
        self.calls.append(("activate", hwnd))
        self.foreground_hwnd = hwnd
        return True

    def responsive(self, hwnd, timeout_ms):
        self.calls.append(("probe", timeout_ms))
        if self.responsive_results:
            return bool(self.responsive_results.pop(0))
        return self.responsive_default

    # 注入类方法只记录调用；返回值固定为成功，时序断言由 calls 完成。
    def key_down(self, key):
        self.calls.append(("key_down", key))
        return key in self.keys_down

    def tap(self, key, hold):
        self.calls.append(("tap", key))
        return True

    def chord(self, modifiers, key, hold):
        self.calls.append(("chord", "+".join(modifiers), key))
        return True

    def type_text(self, text, hold, gap):
        self.calls.append(("type", text))
        return list(self.unsupported)

    # 剪贴板用内存字符串模拟；初始 "SENTINEL" 用来验证「用完还原」。
    def clipboard_get(self):
        return self.clipboard

    def clipboard_set(self, text):
        self.calls.append(("clip", text))
        self.clipboard = text
        return self.clipboard_ok

    # 虚拟时钟：sleep 只把 time 往前推，测试因此可以瞬间跑完。
    def now(self):
        return self.time

    def sleep(self, seconds):
        self.time += max(seconds, 0.0)


def make_config(**kwargs) -> InputConfig:
    """构造测试用 InputConfig：关闭真实等待/焦点要求，保留回探与回车确认.

    align_ticks=True 让 _sleep 走 tick 对齐分支；具体用例可通过 kwargs 覆盖。
    """
    base = dict(
        start_delay=0,
        command_interval=0.1,
        align_ticks=True,
        require_focus=False,
        require_responsive=True,
        verify_after_input=True,
        restore_clipboard=False,
        confirm_enter=True,
        log_time=False,
    )
    base.update(kwargs)
    return InputConfig(**base)


def make_runner(fake, **kwargs):
    """用给定 Transport 建 CommandRunner，并把日志收集到 list 里返回.

    返回 (runner, logs)：logs 供断言「卡顿」「等待确认」等提示确实写给了用户。
    """
    logs: list = []
    runner = CommandRunner(config=make_config(**kwargs), transport=fake, logger=logs.append)
    return runner, logs


def test_paste_sequence():
    """验证粘贴模式的完整按键序列.

    输入：一条 /say hello，paste 模式，confirm_enter=True。
    期望：先按 t 开聊天栏，再 Ctrl+A / 写剪贴板 / Ctrl+V；回车前必须回探；
          最后按回车，且至少产生一条日志。
    """
    fake = FakeTransport()
    runner, logs = make_runner(fake)
    report = runner.run(["/say hello"])

    assert report.sent == 1
    assert not report.aborted
    assert next(call for call in fake.calls if call[0] == "tap") == ("tap", "t")
    # 第一次 tap 必须是 t：它负责打开/聚焦 MC 聊天输入行。
    kinds = [call[0] for call in fake.calls]
    assert ("chord", "ctrl", "a") in fake.calls
    assert ("clip", "/say hello") in fake.calls
    assert ("chord", "ctrl", "v") in fake.calls

    enter_index = next(i for i, call in enumerate(fake.calls) if call == ("tap", "enter"))
    # 回探（probe）必须排在回车之前：确认按键真的被窗口处理后再发送。
    assert kinds.index("probe") < enter_index, "回车之前必须先回探"
    assert [call for call in fake.calls if call[0] == "tap"][-1] == ("tap", "enter")
    assert logs


def test_hang_retry_does_not_send_corrupt_text():
    """验证输入期间卡顿时整条重来，不发送半截内容.

    输入：responsive 依次为 True/False/True/True，max_attempts=3，一条命令。
    期望：最终只发送 1 条；剪贴板被写两次（第一次作废）；第一次尝试不按回车。
    """
    fake = FakeTransport()
    fake.responsive_results = [True, False, True, True]
    # 第二次 responsive=False 命中「输入后回探」，第一次尝试到此为止、不发回车。
    runner, logs = make_runner(fake, max_attempts=3)
    report = runner.run(["/player bot_1 kill"])

    assert report.sent == 1
    assert len([call for call in fake.calls if call[0] == "clip"]) == 2, "卡顿后应整条重来"
    # 回车只应出现在重试后的完整尝试里；>=6 是对调用序列的下界保护。
    enters = [i for i, call in enumerate(fake.calls) if call == ("tap", "enter")]
    assert enters, "重试后最终要发送"
    assert min(enters) >= 6, "第一次尝试不能按回车"
    # 日志要明确告诉用户「卡顿后重来」，而不是静默重试。
    assert any("卡顿" in line for line in logs)


def test_abort_stops_remaining_commands():
    """验证 ESC 中断会停在当前命令之后.

    输入：三条命令；进度回调在第 1 条后把 esc 置为按下。
    期望：report.aborted=True，sent=1，进度只到 (1,3,"/a")。
    """
    fake = FakeTransport()
    runner, _ = make_runner(fake)
    progress: list = []

    def on_progress(index, total, command):
        progress.append((index, total, command))
        fake.keys_down.add("esc")

    runner._on_progress = on_progress
    report = runner.run(["/a", "/b", "/c"])

    assert report.aborted
    assert report.sent == 1
    assert progress == [(1, 3, "/a")]


def test_stop_before_start():
    """验证 start 之前调用 stop 会阻止任何发送.

    输入：先 runner.stop()，再 run(["/a"])。
    期望：aborted=True，sent=0。
    """
    fake = FakeTransport()
    runner, _ = make_runner(fake)
    runner.stop()
    report = runner.run(["/a"])
    assert report.aborted and report.sent == 0


def test_dry_run_never_touches_keyboard():
    """验证 dry-run 只走控制流，不产生任何按键/剪贴板调用.

    输入：dry_run=True，两条命令。
    期望：sent=2，且 calls 中没有 tap / chord / clip。
    """
    fake = FakeTransport()
    runner, _ = make_runner(fake, dry_run=True)
    report = runner.run(["/a", "/b"])
    assert report.sent == 2
    assert not [call for call in fake.calls if call[0] in ("tap", "chord", "clip")]


def test_type_mode_uses_no_clipboard():
    """验证逐字输入模式不使用剪贴板.

    输入：input_mode="type"，一条命令。
    期望：没有 chord / clip；type_text 收到完整命令。
    """
    fake = FakeTransport()
    runner, _ = make_runner(fake, input_mode="type")
    runner.run(["/say hi"])
    assert not [call for call in fake.calls if call[0] in ("chord", "clip")]
    assert ("type", "/say hi") in fake.calls


def test_focus_is_restored_before_each_command():
    """验证窗口失去焦点时会先激活再注入.

    输入：前台句柄初始为 99，require_focus=True，两条命令。
    期望：调用过 activate(1)，且前台最终回到假窗口 1。
    """
    fake = FakeTransport()
    fake.foreground_hwnd = 99
    runner, logs = make_runner(fake, require_focus=True)
    runner.run(["/a", "/b"])
    assert ("activate", 1) in fake.calls
    assert fake.foreground_hwnd == 1


def test_clipboard_is_restored():
    """验证用完剪贴板后恢复原内容.

    输入：初始剪贴板 "SENTINEL"，restore_clipboard=True。
    期望：结束后剪贴板仍是 "SENTINEL"，且最后一次剪贴板调用是还原。
    """
    fake = FakeTransport()
    runner, _ = make_runner(fake, restore_clipboard=True)
    runner.run(["/a"])
    assert fake.clipboard == "SENTINEL"
    assert fake.calls[-1] == ("clip", "SENTINEL")


def test_final_message_is_sent_after_commands():
    """验证全部命令发完后补发结束提示.

    输入：final_message="Operation completed successfully"。
    期望：命令只算 1 条（sent=1）；最后一次剪贴板写入是结束提示；
          回车次数 >=4（命令与结束提示各两次，confirm_enter=True）。
    """
    fake = FakeTransport()
    runner, logs = make_runner(fake, final_message="Operation completed successfully")
    report = runner.run(["/say hi"])

    assert report.sent == 1
    clips = [call[1] for call in fake.calls if call[0] == "clip"]
    assert clips[-1] == "Operation completed successfully"
    assert [call for call in fake.calls if call[0] == "tap"].count(("tap", "enter")) >= 4


def test_empty_commands_are_skipped():
    """验证空串/纯空白命令在准备阶段被丢弃.

    输入：["", "   ", "/a"]。
    期望：skipped=2、sent=1、total=1（total 只算清洗后的命令）。
    """
    fake = FakeTransport()
    runner, _ = make_runner(fake)
    report = runner.run(["", "   ", "/a"])
    assert report.skipped == 2
    assert report.sent == 1
    assert report.total == 1


def test_random_lag_never_sends_partial_commands():
    """验证随机卡顿下不会发出半截命令.

    输入：3 条命令、30 个固定随机种子，每个种子按 30% 概率模拟窗口无响应，
          max_attempts=3。
    期望：每个种子都发完 3 条；每次回车前的最后一次剪贴板内容与完整命令一致。
    """

    import random

    expected = ["/say one", "/say two", "/say three"]
    for seed in range(30):
        # 固定 30 个随机种子，保证失败可复现；概率 0.3 模拟「随机卡顿」。
        # 200 个响应结果足够覆盖 3 条命令 × 最多 3 次尝试 × 每次两次回探。
        rng = random.Random(seed)
        fake = FakeTransport()
        fake.responsive_results = [
            rng.random() > 0.3 for _ in range(200)
        ]
        runner, _ = make_runner(fake, max_attempts=3)
        report = runner.run(expected)

        assert report.sent == 3, (seed, report.summary())
        assert not report.aborted

        # 每个种子重跑一遍：只要有一次把半截内容按了回车，断言就会失败。
        index = 0
        last_clip = None
        for call in fake.calls:
            if call[0] == "clip":
                last_clip = call[1]
            elif call[0] == "tap" and call[1] == "enter" and last_clip is not None:
                assert last_clip == expected[index], (
                    seed,
                    index,
                    last_clip,
                    expected[index],
                )
                index += 1
                last_clip = None
        assert index == len(expected)


# ------ 批间确认：每批发完必须停下来等闸门 ------ #
class _OpenGate:
    """立刻放行，并记录被询问的次数."""

    def __init__(self):
        self.polls = 0

    def poll(self):
        self.polls += 1
        return True


class _ClosedGate:
    """永远不放行：用来验证等待期间收到 ESC 或 stop 时能立即退出."""
    def poll(self):
        return False


def test_batches_stop_between_chunks():
    """验证每批发完都会停一次，最后一批不停.

    输入：4 条命令、batch_size=2、闸门立即放行。
    期望：sent=4；闸门只被 poll 1 次（第 1 批末尾）；on_wait 收到 True/False 且批号 1/2。
    """
    fake = FakeTransport()
    gate = _OpenGate()
    waits: list = []
    logger: list = []
    runner = CommandRunner(
        config=make_config(),
        transport=fake,
        logger=logger.append,
        batch_size=2,
        batch_gate=gate,
        on_wait=lambda waiting, batch, batches: waits.append((waiting, batch, batches)),
    )

    report = runner.run(["/a", "/b", "/c", "/d"])

    assert report.sent == 4
    assert not report.aborted
    assert gate.polls == 1, "只在第 1 批末尾等一次，最后一批不等"
    # 4 条 / 每批 2 条 = 2 批，只在第 1 批末尾等待；第 2 批是最后一批，不再等。
    assert (True, 1, 2) in waits
    assert (False, 1, 2) in waits
    assert any("等待确认后继续下一批" in line for line in logger)


def test_single_batch_never_waits():
    """验证只有一批时不会触发批间等待.

    输入：2 条命令、batch_size=2。
    期望：sent=2，闸门 poll 次数为 0。
    """
    fake = FakeTransport()
    gate = _OpenGate()
    runner = CommandRunner(
        config=make_config(), transport=fake, batch_size=2, batch_gate=gate
    )
    report = runner.run(["/a", "/b"])
    assert report.sent == 2
    assert gate.polls == 0


def test_batch_wait_can_be_aborted_with_esc():
    """验证批间等待可以被 ESC 中断.

    输入：4 条命令、batch_size=2、闸门永不放行；第 2 条进度时按下 esc。
    期望：aborted=True，sent=2（第一批已发完，第二批不开始）。
    """
    fake = FakeTransport()
    runner = CommandRunner(
        config=make_config(),
        transport=fake,
        batch_size=2,
        batch_gate=_ClosedGate(),
    )

    def on_progress(index, total, command):
        if index == 2:
            fake.keys_down.add("esc")

    runner._on_progress = on_progress
    report = runner.run(["/a", "/b", "/c", "/d"])

    assert report.aborted
    assert report.sent == 2, "第二批不能开始"


def test_batch_wait_honours_stop():
    """验证批间等待会响应 runner.stop().

    输入：2 条命令、batch_size=1、闸门永不放行；第 1 条进度时调用 stop。
    期望：aborted=True，sent=1（停在第一批末尾）。
    """
    fake = FakeTransport()
    runner = CommandRunner(
        config=make_config(),
        transport=fake,
        batch_size=1,
        batch_gate=_ClosedGate(),
    )

    def on_progress(index, total, command):
        if index == 1:
            runner.stop()

    runner._on_progress = on_progress
    report = runner.run(["/a", "/b"])

    assert report.aborted
    assert report.sent == 1
