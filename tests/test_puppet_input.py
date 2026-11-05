# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 自动输入执行器（假 Transport） #
# =================================== #

from lspkit.platform.autoinput import (
    CommandRunner,
    InputConfig,
    WindowInfo,
)

WINDOW = WindowInfo(hwnd=1, title="Minecraft 1.21.1", pid=4321, klass="GLFW30")


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

    def clipboard_get(self):
        return self.clipboard

    def clipboard_set(self, text):
        self.calls.append(("clip", text))
        self.clipboard = text
        return self.clipboard_ok

    def now(self):
        return self.time

    def sleep(self, seconds):
        self.time += max(seconds, 0.0)


def make_config(**kwargs) -> InputConfig:
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
    logs: list = []
    runner = CommandRunner(config=make_config(**kwargs), transport=fake, logger=logs.append)
    return runner, logs


def test_paste_sequence():
    fake = FakeTransport()
    runner, logs = make_runner(fake)
    report = runner.run(["/say hello"])

    assert report.sent == 1
    assert not report.aborted
    assert next(call for call in fake.calls if call[0] == "tap") == ("tap", "t")
    kinds = [call[0] for call in fake.calls]
    assert ("chord", "ctrl", "a") in fake.calls
    assert ("clip", "/say hello") in fake.calls
    assert ("chord", "ctrl", "v") in fake.calls

    enter_index = next(i for i, call in enumerate(fake.calls) if call == ("tap", "enter"))
    assert kinds.index("probe") < enter_index, "回车之前必须先回探"
    assert [call for call in fake.calls if call[0] == "tap"][-1] == ("tap", "enter")
    assert logs


def test_hang_retry_does_not_send_corrupt_text():
    fake = FakeTransport()
    fake.responsive_results = [True, False, True, True]
    runner, logs = make_runner(fake, max_attempts=3)
    report = runner.run(["/player bot_1 kill"])

    assert report.sent == 1
    assert len([call for call in fake.calls if call[0] == "clip"]) == 2, "卡顿后应整条重来"
    enters = [i for i, call in enumerate(fake.calls) if call == ("tap", "enter")]
    assert enters, "重试后最终要发送"
    assert min(enters) >= 6, "第一次尝试不能按回车"
    assert any("卡顿" in line for line in logs)


def test_abort_stops_remaining_commands():
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
    fake = FakeTransport()
    runner, _ = make_runner(fake)
    runner.stop()
    report = runner.run(["/a"])
    assert report.aborted and report.sent == 0


def test_dry_run_never_touches_keyboard():
    fake = FakeTransport()
    runner, _ = make_runner(fake, dry_run=True)
    report = runner.run(["/a", "/b"])
    assert report.sent == 2
    assert not [call for call in fake.calls if call[0] in ("tap", "chord", "clip")]


def test_type_mode_uses_no_clipboard():
    fake = FakeTransport()
    runner, _ = make_runner(fake, input_mode="type")
    runner.run(["/say hi"])
    assert not [call for call in fake.calls if call[0] in ("chord", "clip")]
    assert ("type", "/say hi") in fake.calls


def test_focus_is_restored_before_each_command():
    fake = FakeTransport()
    fake.foreground_hwnd = 99
    runner, logs = make_runner(fake, require_focus=True)
    runner.run(["/a", "/b"])
    assert ("activate", 1) in fake.calls
    assert fake.foreground_hwnd == 1


def test_clipboard_is_restored():
    fake = FakeTransport()
    runner, _ = make_runner(fake, restore_clipboard=True)
    runner.run(["/a"])
    assert fake.clipboard == "SENTINEL"
    assert fake.calls[-1] == ("clip", "SENTINEL")


def test_final_message_is_sent_after_commands():
    fake = FakeTransport()
    runner, logs = make_runner(fake, final_message="Operation completed successfully")
    report = runner.run(["/say hi"])

    assert report.sent == 1
    clips = [call[1] for call in fake.calls if call[0] == "clip"]
    assert clips[-1] == "Operation completed successfully"
    assert [call for call in fake.calls if call[0] == "tap"].count(("tap", "enter")) >= 4


def test_empty_commands_are_skipped():
    fake = FakeTransport()
    runner, _ = make_runner(fake)
    report = runner.run(["", "   ", "/a"])
    assert report.skipped == 2
    assert report.sent == 1
    assert report.total == 1


def test_random_lag_never_sends_partial_commands():
    """随机卡顿下：每次回车前的内容必须与预期命令逐字节一致."""

    import random

    expected = ["/say one", "/say two", "/say three"]
    for seed in range(30):
        rng = random.Random(seed)
        fake = FakeTransport()
        fake.responsive_results = [
            rng.random() > 0.3 for _ in range(200)
        ]
        runner, _ = make_runner(fake, max_attempts=3)
        report = runner.run(expected)

        assert report.sent == 3, (seed, report.summary())
        assert not report.aborted

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
