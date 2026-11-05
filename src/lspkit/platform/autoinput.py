# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 向目标窗口注入文本         #
#            （Windows 能力，可替换 Transport 测试） #
# =================================== #
"""
把一批文本逐条打进 Minecraft 聊天栏。

设计要点
========
1. 执行器不直接调用 ctypes：全部经由 Transport 协议，测试里换成记录器即可
   在无 Windows、无游戏的环境下断言每一步时序。
2. 抗卡顿三板斧（沿用 LSP-AutoPuppet 的结论）：
   * 所有功能键按住 key_hold（默认 120ms ≈ 2.4 tick）再抬起，避免「按下+抬起
     在同一帧被合并」导致按键丢失；
   * 指令用剪贴板粘贴（Ctrl+A 后 Ctrl+V）而不是逐字输入，80 个字符压缩成
     两次组合键；
   * 按回车之前回探一次窗口是否还在处理消息，卡顿期间写进输入框的内容不可信，
     此时不发回车、等恢复后整条重来。
3. 窗口用 SetForegroundWindow + AttachThreadInput 精确激活，不依赖 alt+tab。
4. 中断用 GetAsyncKeyState 轮询 ESC，不装全局键盘钩子。
"""

from __future__ import annotations

import ctypes
import math
import sys
import time
from dataclasses import dataclass
from typing import Callable, Optional, Protocol, Sequence

__all__ = [
    "CommandRunner",
    "InputConfig",
    "RunReport",
    "Win32Transport",
    "WindowInfo",
    "diagnose",
    "is_supported",
]

IS_WINDOWS = sys.platform == "win32"

# ------ Minecraft 一个游戏刻 = 50ms，等待时间往它对齐 ------ #
TICK = 0.05


# =================================== #
# @Section: 数据结构                   #
# =================================== #
@dataclass
class WindowInfo:
    hwnd: int
    title: str
    pid: int
    klass: str


@dataclass
class InputConfig:
    """自动输入的全部时序 / 策略参数."""

    window_title_patterns: Sequence[str] = ("minecraft", "我的世界")
    window_class: str = "GLFW30,LWJGL"
    require_focus: bool = True
    focus_timeout: float = 6.0
    start_delay: float = 3.0

    key_hold: float = 0.12
    chord_hold: float = 0.12
    char_hold: float = 0.012
    char_gap: float = 0.010

    input_mode: str = "paste"  # paste | type
    clear_before_paste: bool = True
    confirm_enter: bool = True
    enter_gap: float = 0.08

    chat_open_wait: float = 0.20
    input_wait: float = 0.12
    command_interval: float = 1.0
    align_ticks: bool = True

    require_responsive: bool = True
    responsive_timeout_ms: int = 400
    verify_after_input: bool = True
    post_input_probe_ms: int = 200
    max_attempts: int = 3
    max_hung_wait: float = 20.0
    adaptive_pacing: bool = True
    max_lag_factor: float = 4.0

    abort_key: str = "esc"
    dry_run: bool = False
    restore_clipboard: bool = True
    max_command_length: int = 256
    final_message: Optional[str] = None
    log_time: bool = True


@dataclass
class RunReport:
    total: int = 0
    sent: int = 0
    skipped: int = 0
    aborted: bool = False
    elapsed: float = 0.0
    lag_factor: float = 1.0
    last_index: int = 0
    error: str = ""

    def summary(self) -> str:
        state = "已中断" if self.aborted else "已完成"
        if self.error:
            state = "出错"
        return (
            f"{state}：计划 {self.total} 条，实际发送 {self.sent} 条，"
            f"跳过 {self.skipped} 条，用时 {self.elapsed:.1f}s，"
            f"卡顿系数 {self.lag_factor:.2f}"
        )


class _Aborted(Exception):
    """内部使用：中断信号."""


# =================================== #
# @Section: Transport 协议             #
# =================================== #
class Transport(Protocol):
    def find_window(self, patterns: Sequence[str], klass: str) -> WindowInfo | None: ...

    def is_window(self, hwnd: int) -> bool: ...

    def foreground(self) -> int: ...

    def activate(self, hwnd: int) -> bool: ...

    def responsive(self, hwnd: int, timeout_ms: int) -> bool: ...

    def key_down(self, key: str) -> bool: ...

    def tap(self, key: str, hold: float) -> bool: ...

    def chord(self, modifiers: Sequence[str], key: str, hold: float) -> bool: ...

    def type_text(self, text: str, hold: float, gap: float) -> list: ...

    def clipboard_get(self) -> Optional[str]: ...

    def clipboard_set(self, text: str) -> bool: ...

    def now(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


# =================================== #
# @Section: 执行器                     #
# =================================== #
class CommandRunner:
    """把命令列表逐条打进目标窗口（可在测试中替换 Transport）."""

    def __init__(
        self,
        config: InputConfig | None = None,
        transport: Transport | None = None,
        logger: Callable[[str], None] | None = None,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> None:
        self.config = config or InputConfig()
        self._transport = transport
        self._logger = logger
        self._on_progress = on_progress
        self._stop = False
        self._hwnd: Optional[int] = None
        self._lag_factor = 1.0

    # ------------------------------ 对外 ------------------------------ #
    def stop(self) -> None:
        self._stop = True

    def run(self, commands: Sequence[str]) -> RunReport:
        report = RunReport()
        prepared = self._prepare(commands, report)
        report.total = len(prepared)
        start = self._transport_now()

        try:
            if not prepared:
                self._log("没有可执行的命令")
                return report
            self._log(
                f"准备执行 {len(prepared)} 条命令（{self.config.input_mode} 模式）"
            )
            if not self.config.dry_run:
                if self.config.restore_clipboard:
                    self._saved_clipboard = self._transport_safe_clipboard()
                self._prepare_session()
            else:
                self._log("dry-run：只记录将要输入的命令，不会真的按键")

            for index, command in enumerate(prepared, 1):
                if self._abort_requested():
                    raise _Aborted()
                self._send_one(command)
                report.sent += 1
                report.last_index = index
                self._log(f"[{index}/{len(prepared)}] {command}")
                if self._on_progress:
                    self._on_progress(index, len(prepared), command)

            if self.config.final_message:
                self._send_one(self.config.final_message)

        except _Aborted:
            report.aborted = True
            self._log("已中断")
        except Exception as error:  # noqa: BLE001 - 自动化线程必须兜底
            report.aborted = True
            report.error = f"{type(error).__name__}: {error}"
            self._log(f"执行出错：{report.error}")
        finally:
            if not self.config.dry_run:
                self._restore_clipboard()
            report.elapsed = self._transport_now() - start
            report.lag_factor = self._lag_factor
            self._log(report.summary())

        return report

    # ------------------------------ 准备 ------------------------------ #
    def _prepare(self, commands: Sequence[str], report: RunReport) -> list:
        prepared: list = []
        for raw in commands or []:
            command = "" if raw is None else str(raw)
            command = command.replace("\r", " ").replace("\n", " ").strip()
            command = command.lstrip("\ufeff")
            if not command:
                report.skipped += 1
                continue
            if len(command) > self.config.max_command_length:
                self._log(
                    f"告警：命令长度 {len(command)} 超过 Minecraft 输入框上限 "
                    f"{self.config.max_command_length}：{command[:60]}…"
                )
            prepared.append(command)
        return prepared

    def _prepare_session(self) -> None:
        if self.config.start_delay > 0:
            self._log(
                f"请在 {self.config.start_delay:.0f} 秒内保持游戏窗口化，"
                "不要打开背包 / 箱子 / ESC 菜单"
            )
            self._wait_abort_key_released()
            self._sleep(self.config.start_delay, align=False)
        else:
            self._wait_abort_key_released()
        if not self._ensure_focus():
            raise RuntimeError(
                "未能把 Minecraft 窗口切到前台，已中止；请确认游戏正在运行"
            )

    # ------------------------------ 单条 ------------------------------ #
    def _send_one(self, command: str) -> None:
        attempts = max(1, int(self.config.max_attempts))
        for attempt in range(1, attempts + 1):
            if not self._ensure_focus():
                raise RuntimeError("游戏窗口失去焦点且无法切回，已中止")
            if self.config.dry_run:
                self._sleep(self.config.command_interval)
                return
            if not self._wait_ready():
                raise _Aborted()

            self._transport.tap("t", self.config.key_hold)
            self._sleep(self.config.chat_open_wait)

            if self.config.input_mode == "paste":
                self._paste(command)
            else:
                unsupported = self._transport.type_text(
                    command, self.config.char_hold, self.config.char_gap
                )
                if unsupported:
                    self._log(
                        "当前键盘布局无法输入这些字符，已跳过：" + "".join(unsupported)
                    )

            suspect = self.config.verify_after_input and not self._input_dispatched()
            if suspect and attempt < attempts:
                self._log(
                    f"输入期间检测到卡顿，本次不发回车，恢复后重来"
                    f"（第 {attempt}/{attempts} 次）"
                )
                continue
            if suspect:
                self._log(f"重试 {attempts} 次仍在卡顿，按现状发送")

            self._sleep(self.config.input_wait)
            self._transport.tap("enter", self.config.key_hold)
            if self.config.confirm_enter:
                self._sleep(self.config.enter_gap)
                self._transport.tap("enter", self.config.key_hold)
            self._sleep(self.config.command_interval)
            return

    def _paste(self, text: str) -> None:
        if self.config.clear_before_paste:
            self._transport.chord(["ctrl"], "a", self.config.chord_hold)
            self._sleep(0.06, align=False)
        if not self._transport.clipboard_set(text):
            self._log("写剪贴板失败，本次回退为逐字符输入")
            self._transport.type_text(text, self.config.char_hold, self.config.char_gap)
            return
        if not self._transport.chord(["ctrl"], "v", self.config.chord_hold):
            self._log("Ctrl+V 注入失败（请检查是否以管理员身份运行）")

    # ------------------------------ 焦点 / 卡顿 ------------------------------ #
    def _ensure_focus(self) -> bool:
        if self.config.dry_run:
            return True
        hwnd = self._hwnd
        if not hwnd or not self._transport.is_window(hwnd):
            info = self._transport.find_window(
                self.config.window_title_patterns, self.config.window_class
            )
            if info is None:
                self._log("没有找到 Minecraft 窗口（可用「诊断」查看窗口列表）")
                self._hwnd = None
                return not self.config.require_focus
            self._hwnd = info.hwnd
            self._log(f"已锁定游戏窗口：{info.title}（PID {info.pid}）")

        if not self.config.require_focus:
            return True
        if self._transport.foreground() == self._hwnd:
            return True

        self._log("游戏窗口不在前台，正在切换…")
        deadline = self._transport_now() + max(self.config.focus_timeout, 0.5)
        while self._transport_now() < deadline:
            if self._abort_requested():
                return False
            if self._transport.activate(self._hwnd) or (
                self._transport.foreground() == self._hwnd
            ):
                self._sleep(0.15, align=False)
                return True
            self._transport.sleep(0.1)
        return self._transport.foreground() == self._hwnd

    def _wait_ready(self) -> bool:
        if not self.config.require_responsive or not self._hwnd:
            return True
        if self._transport.responsive(self._hwnd, self.config.responsive_timeout_ms):
            return True

        self._log("检测到游戏卡顿，暂停注入，等它恢复…")
        deadline = self._transport_now() + self.config.max_hung_wait
        while self._transport_now() < deadline:
            if self._abort_requested():
                return False
            self._transport.sleep(0.1)
            if self._transport.responsive(
                self._hwnd, self.config.responsive_timeout_ms
            ):
                self._log("游戏已恢复响应，继续执行")
                self._lag_factor = min(
                    self._lag_factor * 1.3, self.config.max_lag_factor
                )
                return True
        self._log(
            f"游戏卡顿超过 {self.config.max_hung_wait:.0f}s，仍按原顺序继续"
        )
        return True

    def _input_dispatched(self) -> bool:
        if not self._hwnd:
            return True
        return self._transport.responsive(self._hwnd, self.config.post_input_probe_ms)

    # ------------------------------ 时序 ------------------------------ #
    def _sleep(
        self,
        seconds: float,
        align: bool | None = None,
        scale: bool = True,
        allow_abort: bool = True,
    ) -> float:
        if seconds <= 0:
            return 0.0
        target = seconds * (self._lag_factor if scale else 1.0)
        use_align = self.config.align_ticks if align is None else align
        if use_align:
            target = math.ceil(round(target / TICK, 6)) * TICK

        start = self._transport_now()
        deadline = start + target
        while True:
            if allow_abort and self._abort_requested():
                raise _Aborted()
            remain = deadline - self._transport_now()
            if remain <= 0:
                break
            self._transport.sleep(min(remain, 0.05))

        elapsed = self._transport_now() - start
        if self.config.adaptive_pacing:
            if elapsed > target * 1.5 + 0.02:
                self._lag_factor = min(
                    self._lag_factor * 1.15, self.config.max_lag_factor
                )
            elif self._lag_factor > 1.0:
                self._lag_factor = max(1.0, self._lag_factor * 0.98)
        return elapsed

    def _abort_requested(self) -> bool:
        if self._stop:
            return True
        key = self.config.abort_key
        if not key:
            return False
        return self._transport.key_down(key)

    def _wait_abort_key_released(self, timeout: float = 3.0) -> None:
        key = self.config.abort_key
        if not key or not self._transport.key_down(key):
            return
        self._log(f"检测到 {key.upper()} 还按着，等它松开…")
        deadline = self._transport_now() + timeout
        while self._transport.key_down(key) and self._transport_now() < deadline:
            self._transport.sleep(0.2)

    # ------------------------------ 剪贴板 / 工具 ------------------------------ #
    def _transport_now(self) -> float:
        return self._get_transport().now()

    def _get_transport(self) -> Transport:
        if self._transport is None:
            self._transport = Win32Transport()
        return self._transport

    def _transport_safe_clipboard(self) -> Optional[str]:
        try:
            return self._get_transport().clipboard_get()
        except Exception:  # noqa: BLE001
            return None

    def _restore_clipboard(self) -> None:
        saved = getattr(self, "_saved_clipboard", None)
        if self.config.restore_clipboard and saved is not None:
            try:
                if self._get_transport().clipboard_set(saved):
                    self._log("已还原原有剪贴板内容")
            except Exception:  # noqa: BLE001
                pass
        self._saved_clipboard = None

    def _log(self, message: str) -> None:
        text = (
            f"[自动输入 {time.strftime('%H:%M:%S')}] {message}"
            if self.config.log_time
            else f"[自动输入] {message}"
        )
        if self._logger:
            self._logger(text)


# =================================== #
# @Section: Win32 实现                 #
# =================================== #
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MAPVK_VK_TO_VSC = 0
SW_RESTORE = 9
WM_NULL = 0x0000
SMTO_BLOCK = 0x0001
SMTO_ABORTIFHUNG = 0x0002
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_TAB = 0x09
VK_SPACE = 0x20

VK_MAP = {
    "enter": VK_RETURN,
    "return": VK_RETURN,
    "esc": VK_ESCAPE,
    "escape": VK_ESCAPE,
    "shift": VK_SHIFT,
    "ctrl": VK_CONTROL,
    "control": VK_CONTROL,
    "alt": VK_MENU,
    "tab": VK_TAB,
    "space": VK_SPACE,
}


if IS_WINDOWS:
    from ctypes import wintypes

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [
            ("ki", KEYBDINPUT),
            ("mi", MOUSEINPUT),
            ("hi", HARDWAREINPUT),
        ]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("union",)
        _fields_ = [("type", wintypes.DWORD), ("union", _INPUTUNION)]

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def is_supported() -> bool:
    return IS_WINDOWS


class Win32Transport:
    """真实注入：SendInput + 窗口激活 + 消息泵探测 + 剪贴板."""

    def __init__(self) -> None:
        if not IS_WINDOWS:
            raise RuntimeError("键鼠注入仅支持 Windows")
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        _configure_user32(self._user32)
        _configure_kernel32(self._kernel32)

    # ------ 窗口 ------ #
    def find_window(self, patterns: Sequence[str], klass: str) -> WindowInfo | None:
        """
        只按窗口类名认游戏窗口（GLFW30 / LWJGL）.

        不能只按标题认：启动器（HMCL / PCL）的标题里也有 Minecraft，
        把命令打进启动器毫无意义，而且会抢走焦点。
        """

        allowed = {item.strip() for item in str(klass or "").split(",") if item.strip()}
        hits: list = []

        @WNDENUMPROC
        def callback(hwnd, _lparam):
            if not self._user32.IsWindowVisible(hwnd):
                return True
            cls = _window_class(self._user32, hwnd)
            if cls not in allowed:
                return True
            title = _window_text(self._user32, hwnd)
            if not title:
                return True
            pid = wintypes.DWORD()
            self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            hits.append(WindowInfo(int(hwnd), title, int(pid.value), cls))
            return True

        try:
            self._user32.EnumWindows(callback, 0)
        except Exception:  # noqa: BLE001
            return None
        if not hits:
            return None

        lowered = [str(p).lower() for p in patterns]
        hits.sort(
            key=lambda item: (
                not any(p in item.title.lower() for p in lowered),
                len(item.title),
            )
        )
        return hits[0]

    def title_matches(self, patterns: Sequence[str]) -> list:
        """仅用于诊断：标题里带 minecraft 的窗口（通常是启动器，不是游戏）."""

        lowered = [str(p).lower() for p in patterns]
        hits: list = []

        @WNDENUMPROC
        def callback(hwnd, _lparam):
            if not self._user32.IsWindowVisible(hwnd):
                return True
            title = _window_text(self._user32, hwnd)
            if title and any(p in title.lower() for p in lowered):
                cls = _window_class(self._user32, hwnd)
                pid = wintypes.DWORD()
                self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                hits.append(WindowInfo(int(hwnd), title, int(pid.value), cls))
            return True

        try:
            self._user32.EnumWindows(callback, 0)
        except Exception:  # noqa: BLE001
            return []
        return hits

    def is_window(self, hwnd: int) -> bool:
        return bool(self._user32.IsWindow(hwnd))

    def foreground(self) -> int:
        return int(self._user32.GetForegroundWindow())

    def activate(self, hwnd: int) -> bool:
        user32 = self._user32
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        target_thread = user32.GetWindowThreadProcessId(hwnd, None)
        current_thread = self._kernel32.GetCurrentThreadId()
        foreground = user32.GetForegroundWindow()
        foreground_thread = (
            user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
        )
        attached: list = []
        for thread in {int(target_thread), int(foreground_thread)}:
            if thread and thread != current_thread:
                if user32.AttachThreadInput(current_thread, thread, True):
                    attached.append(thread)
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
        finally:
            for thread in attached:
                user32.AttachThreadInput(current_thread, thread, False)
        time.sleep(0.05)
        return int(user32.GetForegroundWindow()) == int(hwnd)

    def responsive(self, hwnd: int, timeout_ms: int) -> bool:
        result = ctypes.c_size_t(0)
        flags = SMTO_BLOCK | SMTO_ABORTIFHUNG
        ok = self._user32.SendMessageTimeoutW(
            hwnd, WM_NULL, 0, 0, flags, max(int(timeout_ms), 1), ctypes.byref(result)
        )
        return bool(ok)

    # ------ 按键 ------ #
    def key_down(self, key: str) -> bool:
        vk = _resolve_vk(key)
        if vk is None:
            return False
        return bool(self._user32.GetAsyncKeyState(vk) & 0x8000)

    def tap(self, key: str, hold: float) -> bool:
        vk = _resolve_vk(key)
        if vk is None:
            return False
        self._send(vk, False)
        time.sleep(max(hold, 0.005))
        self._send(vk, True)
        return True

    def chord(self, modifiers: Sequence[str], key: str, hold: float) -> bool:
        keys = [vk for vk in (_resolve_vk(item) for item in modifiers) if vk is not None]
        target = _resolve_vk(key)
        if target is None:
            return False
        for vk in keys:
            self._send(vk, False)
        self._send(target, False)
        time.sleep(max(hold, 0.005))
        self._send(target, True)
        for vk in reversed(keys):
            self._send(vk, True)
        return True

    def type_text(self, text: str, hold: float, gap: float) -> list:
        unsupported: list = []
        for char in text:
            res = self._user32.VkKeyScanW(char)
            if res == -1:
                unsupported.append(char)
                continue
            vk = res & 0xFF
            shift = bool((res >> 8) & 0x01)
            if shift:
                self._send(VK_SHIFT, False)
            self._send(vk, False)
            time.sleep(max(hold, 0.002))
            self._send(vk, True)
            if shift:
                self._send(VK_SHIFT, True)
            time.sleep(max(gap, 0.002))
        return unsupported

    def _send(self, vk: int, up: bool) -> None:
        scan = self._user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0)
        item = INPUT()
        item.type = INPUT_KEYBOARD
        item.union = _INPUTUNION(ki=KEYBDINPUT(0, scan, flags, 0, 0))
        self._user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(INPUT))

    # ------ 剪贴板 ------ #
    def clipboard_ok(self) -> bool:
        """只检查剪贴板能否打开，不写入任何内容."""

        if not _open_clipboard(self._user32):
            return False
        self._user32.CloseClipboard()
        return True

    def clipboard_get(self) -> Optional[str]:
        user32 = self._user32
        if not _open_clipboard(user32):
            return None
        try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return None
            pointer = self._kernel32.GlobalLock(handle)
            if not pointer:
                return None
            try:
                return ctypes.wstring_at(pointer)
            finally:
                self._kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()

    def clipboard_set(self, text: str) -> bool:
        user32 = self._user32
        kernel32 = self._kernel32
        data = text.encode("utf-16-le") + b"\x00\x00"
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            return False
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return False
        try:
            ctypes.memmove(pointer, data, len(data))
        finally:
            kernel32.GlobalUnlock(handle)

        if not _open_clipboard(user32):
            kernel32.GlobalFree(handle)
            return False
        try:
            user32.EmptyClipboard()
            if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                return False
            return True
        finally:
            user32.CloseClipboard()

    # ------ 时间 ------ #
    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(max(seconds, 0.0))


def _resolve_vk(key: str) -> int | None:
    text = str(key or "").strip().lower()
    if text in VK_MAP:
        return VK_MAP[text]
    if len(text) == 1 and text.isalnum():
        return ord(text.upper())
    return None


def _configure_user32(user32) -> None:
    """64 位下 HWND / HANDLE 必须显式声明类型，否则会被截成 32 位."""

    from ctypes import wintypes

    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.VkKeyScanW.argtypes = [ctypes.c_wchar]
    user32.VkKeyScanW.restype = ctypes.c_short
    user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
    user32.MapVirtualKeyW.restype = wintypes.UINT

    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.BringWindowToTop.restype = wintypes.BOOL
    user32.SetFocus.argtypes = [wintypes.HWND]
    user32.SetFocus.restype = wintypes.HWND
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.AttachThreadInput.restype = wintypes.BOOL
    user32.SendMessageTimeoutW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    user32.SendMessageTimeoutW.restype = ctypes.c_size_t

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE


def _configure_kernel32(kernel32) -> None:
    from ctypes import wintypes

    kernel32.GetCurrentThreadId.argtypes = []
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL


def _window_text(user32, hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def _window_class(user32, hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, 256)
    return buffer.value


def _open_clipboard(user32, attempts: int = 12, delay: float = 0.03) -> bool:
    for _ in range(max(attempts, 1)):
        if user32.OpenClipboard(None):
            return True
        time.sleep(delay)
    return False


# =================================== #
# @Section: 环境诊断                   #
# =================================== #
def diagnose() -> list:
    """
    只读自检：窗口、焦点、管理员、剪贴板、输入框上限.

    不注入任何按键；返回 [{id, ok, detail}].
    """

    checks: list = []

    def add(check_id: str, ok: bool | None, detail: str = "") -> None:
        checks.append({"id": check_id, "ok": ok, "detail": detail})

    if not IS_WINDOWS:
        add("platform", False, "当前系统不是 Windows，执行模式不可用")
        return checks

    add("platform", True, sys.platform)
    try:
        transport = Win32Transport()
    except Exception as error:  # noqa: BLE001
        add("transport", False, str(error))
        return checks
    add("transport", True, "SendInput 可用")

    info = transport.find_window(("minecraft", "我的世界"), "GLFW30,LWJGL")
    if info is not None:
        add("window", True, f"{info.title}（PID {info.pid}）")
    else:
        detail = "没有找到游戏窗口（GLFW30 / LWJGL）"
        others = transport.title_matches(("minecraft", "我的世界"))
        if others:
            names = "、".join(item.title for item in others[:3])
            detail += f"；标题里带 Minecraft 的是：{names}（通常是启动器，不是游戏窗口）"
        add("window", False, detail)

    if info is not None:
        add(
            "foreground",
            transport.foreground() == info.hwnd,
            "游戏当前在前台" if transport.foreground() == info.hwnd else "游戏不在前台（执行时会自动切换）",
        )
        add(
            "responsive",
            transport.responsive(info.hwnd, 400),
            "主线程响应正常",
        )
        add(
            "clipboard",
            transport.clipboard_ok(),
            "剪贴板可访问（执行时会临时占用并还原）",
        )

    try:
        elevated = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        elevated = False
    add(
        "admin",
        None,
        "以管理员身份运行" if elevated else "普通权限；若游戏以管理员启动，请同样以管理员运行本应用",
    )
    return checks
