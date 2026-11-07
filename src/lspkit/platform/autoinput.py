# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 向目标窗口注入文本         #
#            （Windows 能力，可替换 Transport 测试） #
# =================================== #
# 本文件职责：把一批“已经生成好的指令”安全地送进 Minecraft 聊天栏。
# 不参与任何业务计算：业务层只交出字符串列表，焦点 / 时序 / 卡顿容错都在这里处理。
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

# Windows 上才有 ctypes.WinDLL / SendInput；其它系统只可能走 dry-run 或直接报错
IS_WINDOWS = sys.platform == "win32"

# ------ Minecraft 一个游戏刻 = 50ms，等待时间往它对齐 ------ #
# 对齐到整 tick 的原因：游戏只在 tick 边界处理输入，半 tick 的等待可能白等
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

    # 单位说明：除 *timeout_ms / *probe_ms 是毫秒外，其余时间参数单位都是秒
    # 窗口识别：标题只用于排序和展示，真正认窗口靠窗口类名
    window_title_patterns: Sequence[str] = ("minecraft", "我的世界")
    # 逗号分隔的候选类名；GLFW30 / LWJGL 是 Minecraft 使用的窗口类名
    window_class: str = "GLFW30,LWJGL"
    # 是否强制把游戏切到前台；关掉后按键可能被别的窗口吃掉
    require_focus: bool = True
    # 秒：切前台的最长等待，超时就放弃本次注入
    focus_timeout: float = 6.0
    # 秒：正式注入前的缓冲，留给玩家切窗口 / 松开鼠标
    start_delay: float = 3.0

    # 秒：功能键按住的时长；120ms ≈ 2.4 tick，太短会被游戏合并掉这次按键
    key_hold: float = 0.12
    # 秒：组合键（如 Ctrl+V）按住的时长
    chord_hold: float = 0.12
    # 秒：逐字符输入时单个字符按住的时长
    char_hold: float = 0.012
    # 秒：逐字符输入时两个字符之间的间隔
    char_gap: float = 0.010

    input_mode: str = "paste"  # paste | type
    # 粘贴前先 Ctrl+A 全选，清掉聊天框里的残留内容
    clear_before_paste: bool = True
    # 回车后是否再补一次回车确认（某些版本/服务器需要两次才真正发送）
    confirm_enter: bool = True
    # 秒：两次回车之间的间隔
    enter_gap: float = 0.08

    # 秒：按 T 打开聊天栏后，等它真正出现的时间
    chat_open_wait: float = 0.20
    # 秒：输入完成到按回车之间的缓冲
    input_wait: float = 0.12
    # 秒：两条指令之间的间隔，留出时间让游戏/服务器处理完上一条
    command_interval: float = 1.0
    # 是否把等待时间向上取整到 50ms 的整数倍（对齐游戏 tick）
    align_ticks: bool = True

    # 是否在注入前先探测窗口是否卡死
    require_responsive: bool = True
    # 毫秒：探测窗口响应的超时（发一个空消息，超时没回应就算卡顿）
    responsive_timeout_ms: int = 400
    # 是否在输入后回探一次，确认按键真的被处理了
    verify_after_input: bool = True
    # 毫秒：输入后回探的超时
    post_input_probe_ms: int = 200
    # 单条指令最多尝试几次（内容不可信时整条重来）
    max_attempts: int = 3
    # 秒：卡顿后最多等多久，超时就按原顺序继续
    max_hung_wait: float = 20.0
    # 是否根据实际耗时自动放大后续等待（卡得越狠，等得越久）
    adaptive_pacing: bool = True
    # 自动放大的上限倍数，避免一次卡顿把整个节奏拖到不可用
    max_lag_factor: float = 4.0

    # 中断键：注入过程中按住它会立刻停止（默认 ESC）
    abort_key: str = "esc"
    # 只演练不按键：日志照写，方便先确认要发什么
    dry_run: bool = False
    # 结束后把用户原本的剪贴板内容还原
    restore_clipboard: bool = True
    # 单条指令长度告警阈值（Minecraft 聊天输入框上限是 256 字符）
    max_command_length: int = 256
    # 全部发完后再补发的一条指令（通常是结束提示），None 表示不发
    final_message: Optional[str] = None
    # 日志行是否带时间戳
    log_time: bool = True


@dataclass
class RunReport:
    """一次批量注入的结果汇总，界面用它展示“发了几条、用了多久、卡不卡”。

    字段口径：total 计划条数、sent 实发条数、skipped 清洗时丢弃的条数、
    elapsed 秒、lag_factor 卡顿系数（>1 表示已自动放慢）、last_index 最后发送序号（从 1 起）。
    """

    total: int = 0
    sent: int = 0
    skipped: int = 0
    aborted: bool = False
    elapsed: float = 0.0
    lag_factor: float = 1.0
    last_index: int = 0
    error: str = ""

    def summary(self) -> str:
        """生成一行中文总结（状态、条数、耗时、卡顿系数），写进日志给用户看。"""

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
    """注入通道的抽象接口：执行器只依赖这些方法，测试里换成假实现就行。

    真实实现是 Win32Transport；测试用的记录器可以断言每一步的调用时序。
    """

    # 按标题模式 + 窗口类名找游戏窗口；找不到返回 None
    def find_window(self, patterns: Sequence[str], klass: str) -> WindowInfo | None: ...

    # 该句柄是否仍指向一个存在的窗口（窗口关掉后旧句柄会失效）
    def is_window(self, hwnd: int) -> bool: ...

    # 当前前台窗口的句柄
    def foreground(self) -> int: ...

    # 把窗口切到前台；返回是否成功
    def activate(self, hwnd: int) -> bool: ...

    # 在 timeout_ms 内窗口是否响应消息（用发空消息的方式探测卡顿）
    def responsive(self, hwnd: int, timeout_ms: int) -> bool: ...

    # 该键当前是否处于按下状态（用于轮询 ESC 中断）
    def key_down(self, key: str) -> bool: ...

    # 按一下再松开；hold 是按住的秒数
    def tap(self, key: str, hold: float) -> bool: ...

    # 组合键：先按住全部修饰键，再按主键，最后逆序松开修饰键
    def chord(self, modifiers: Sequence[str], key: str, hold: float) -> bool: ...

    # 逐字符输入；返回当前键盘布局打不出来的字符列表
    def type_text(self, text: str, hold: float, gap: float) -> list: ...

    # 读剪贴板文本；打不开剪贴板时返回 None
    def clipboard_get(self) -> Optional[str]: ...

    # 把文本写入剪贴板；成功返回 True
    def clipboard_set(self, text: str) -> bool: ...

    # 单调时钟（秒），不受系统时间被调整的影响
    def now(self) -> float: ...

    # 等待指定秒数（测试实现里可以什么都不做）
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
        batch_size: int = 0,
        batch_gate: object | None = None,
        on_wait: Callable[[bool, int, int], None] | None = None,
    ) -> None:
        """
        batch_size > 0 时每发完这么多条就停下，等 batch_gate 放行：
        闸门只需提供 ``poll() -> bool``（返回 True 表示继续下一批）。
        on_wait(waiting, batch, batches) 用于把「正在等确认」同步给界面。
        """

        self.config = config or InputConfig()
        # transport 为 None 时，第一次真正用到才创建 Win32Transport（测试里可以一直不创建）
        self._transport = transport
        self._logger = logger
        # 进度回调：每发完一条就通知界面 (序号, 总数, 指令内容)
        self._on_progress = on_progress
        # 负数 / None 一律当 0，表示“不分批”
        self._batch_size = max(int(batch_size or 0), 0)
        self._batch_gate = batch_gate
        self._on_wait = on_wait
        # stop() 置位后，所有等待循环都会尽快退出
        self._stop = False
        # 已锁定的游戏窗口句柄；None 表示还没找到
        self._hwnd: Optional[int] = None
        # 卡顿系数：>1 表示后续等待会自动变长
        self._lag_factor = 1.0

    # ------------------------------ 对外 ------------------------------ #
    def stop(self) -> None:
        """请求停止：置位后，正在等待或循环中的注入流程会尽快退出。"""

        self._stop = True

    def run(self, commands: Sequence[str]) -> RunReport:
        """按顺序注入整批指令，返回运行报告（发送条数、耗时、卡顿系数等）。"""

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
                    # 先存一份用户原来的剪贴板，结束后还原，避免污染用户内容
                    self._saved_clipboard = self._transport_safe_clipboard()
                self._prepare_session()
            else:
                self._log("dry-run：只记录将要输入的命令，不会真的按键")

            total = len(prepared)
            # 分批数向上取整：例如 10 条、每批 3 条 -> 4 批
            batches = (
                math.ceil(total / float(self._batch_size)) if self._batch_size else 1
            )
            for index, command in enumerate(prepared, 1):
                # 每发一条前都检查一次中断，保证 ESC 的响应足够快
                if self._abort_requested():
                    raise _Aborted()
                self._send_one(command)
                report.sent += 1
                report.last_index = index
                self._log(f"[{index}/{total}] {command}")
                if self._on_progress:
                    self._on_progress(index, total, command)
                # 正好是一批的结尾且后面还有命令，就停下来等界面确认
                if self._batch_size and index % self._batch_size == 0 and index < total:
                    if not self._wait_batch(index // self._batch_size, batches):
                        raise _Aborted()

            if self.config.final_message:
                # 结束语也走同一条注入流程，失败会抛异常并被下面的兜底接住
                self._send_one(self.config.final_message)

        except _Aborted:
            # 中断属于“正常结束”，用独立的 _Aborted 区分，避免被当成意外错误
            report.aborted = True
            self._log("已中断")
        except Exception as error:  # noqa: BLE001 - 自动化线程必须兜底
            report.aborted = True
            report.error = f"{type(error).__name__}: {error}"
            self._log(f"执行出错：{report.error}")
        finally:
            # 无论成功、失败还是中断，都要还原剪贴板并结算耗时
            if not self.config.dry_run:
                self._restore_clipboard()
            report.elapsed = self._transport_now() - start
            report.lag_factor = self._lag_factor
            self._log(report.summary())

        return report

    # ------------------------------ 准备 ------------------------------ #
    def _prepare(self, commands: Sequence[str], report: RunReport) -> list:
        """清洗待发指令：统一成单行文本、丢掉空串，并把跳过的条数记进报告。"""

        prepared: list = []
        for raw in commands or []:
            command = "" if raw is None else str(raw)
            # 聊天栏只能输入单行：换行统一换成空格，否则回车会提前把指令发出去
            command = command.replace("\r", " ").replace("\n", " ").strip()
            # 去掉 UTF-8 BOM，否则游戏里会多出一个看不见的字符
            command = command.lstrip("\ufeff")
            if not command:
                report.skipped += 1
                continue
            # 超长只告警不截断：截断会把指令发错，交给用户自己处理更安全
            if len(command) > self.config.max_command_length:
                self._log(
                    f"告警：命令长度 {len(command)} 超过 Minecraft 输入框上限 "
                    f"{self.config.max_command_length}：{command[:60]}…"
                )
            prepared.append(command)
        return prepared

    def _prepare_session(self) -> None:
        """会话准备：等倒计时、等中断键松开，再把游戏窗口切到前台。"""

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

    # ------------------------------ 批间闸门 ------------------------------ #
    def _wait_batch(self, batch: int, batches: int) -> bool:
        """
        一批发完后停在原地，等界面点「继续」；返回 False 表示被中断.

        等待期间仍然轮询 ESC 与 stop()，所以暂停中也能中断。
        """

        if self._on_wait is not None:
            self._on_wait(True, batch, batches)
        self._log(f"第 {batch}/{batches} 批已完成，等待确认后继续下一批")
        try:
            while True:
                if self._abort_requested():
                    self._log("等待确认时收到中断")
                    return False
                if self._batch_gate is not None and self._batch_gate.poll():
                    self._log(f"已确认，继续第 {batch + 1}/{batches} 批")
                    return True
                self._get_transport().sleep(0.1)
        finally:
            if self._on_wait is not None:
                self._on_wait(False, batch, batches)

    # ------------------------------ 单条 ------------------------------ #
    def _send_one(self, command: str) -> None:
        """把一条指令打进聊天栏；检测到卡顿时整条重试，最多 max_attempts 次。"""

        attempts = max(1, int(self.config.max_attempts))
        for attempt in range(1, attempts + 1):
            if not self._ensure_focus():
                raise RuntimeError("游戏窗口失去焦点且无法切回，已中止")
            if self.config.dry_run:
                # 演练模式：只按正常节奏空等，让日志时序和真实执行保持一致
                self._sleep(self.config.command_interval)
                return
            if not self._wait_ready():
                raise _Aborted()

            # 按 T 打开聊天栏，再等它真正弹出来
            self._transport.tap("t", self.config.key_hold)
            self._sleep(self.config.chat_open_wait)

            if self.config.input_mode == "paste":
                # 默认走剪贴板：一次粘贴代替几十次按键，被卡顿打断的概率更小
                self._paste(command)
            else:
                unsupported = self._transport.type_text(
                    command, self.config.char_hold, self.config.char_gap
                )
                if unsupported:
                    self._log(
                        "当前键盘布局无法输入这些字符，已跳过：" + "".join(unsupported)
                    )

            # 回探一次窗口：还在卡说明写进输入框的内容不可信，这次不能按回车
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
                # 再补一次回车：实测有些情况下第一次回车只确认了输入框，并没有发送
                self._sleep(self.config.enter_gap)
                self._transport.tap("enter", self.config.key_hold)
            self._sleep(self.config.command_interval)
            return

    def _paste(self, text: str) -> None:
        """用剪贴板粘贴来输入文本：先 Ctrl+A 清空，再写剪贴板并 Ctrl+V。"""

        if self.config.clear_before_paste:
            # Ctrl+A 全选后粘贴会被整段替换，等于清掉了聊天框里的残留内容
            self._transport.chord(["ctrl"], "a", self.config.chord_hold)
            # 60ms 给游戏处理全选；这里不对齐 tick，因为它不属于关键时序
            self._sleep(0.06, align=False)
        if not self._transport.clipboard_set(text):
            # 剪贴板被别的程序占用时退化成逐字符输入：慢，但至少还能发出去
            self._log("写剪贴板失败，本次回退为逐字符输入")
            self._transport.type_text(text, self.config.char_hold, self.config.char_gap)
            return
        if not self._transport.chord(["ctrl"], "v", self.config.chord_hold):
            self._log("Ctrl+V 注入失败（请检查是否以管理员身份运行）")

    # ------------------------------ 焦点 / 卡顿 ------------------------------ #
    def _ensure_focus(self) -> bool:
        """确保游戏窗口在前台：必要时重新找窗口并激活，返回是否还能继续。"""

        if self.config.dry_run:
            return True
        hwnd = self._hwnd
        # 句柄失效（窗口被关掉 / 游戏重启）时重新找一次
        if not hwnd or not self._transport.is_window(hwnd):
            info = self._transport.find_window(
                self.config.window_title_patterns, self.config.window_class
            )
            if info is None:
                self._log("没有找到 Minecraft 窗口（可用「诊断」查看窗口列表）")
                self._hwnd = None
                # 不强制前台时可以“盲发”；强制前台时这里必须报失败
                return not self.config.require_focus
            self._hwnd = info.hwnd
            self._log(f"已锁定游戏窗口：{info.title}（PID {info.pid}）")

        if not self.config.require_focus:
            return True
        if self._transport.foreground() == self._hwnd:
            return True

        self._log("游戏窗口不在前台，正在切换…")
        # 至少给 0.5s：即使 focus_timeout 被配成 0，也要真的尝试一次
        deadline = self._transport_now() + max(self.config.focus_timeout, 0.5)
        while self._transport_now() < deadline:
            if self._abort_requested():
                return False
            # 有的系统要连点几次才能真的把窗口顶到前台，所以放在循环里重试
            if self._transport.activate(self._hwnd) or (
                self._transport.foreground() == self._hwnd
            ):
                # 再等 150ms 让焦点事件派发完，避免紧随其后的按键丢失
                self._sleep(0.15, align=False)
                return True
            self._transport.sleep(0.1)
        return self._transport.foreground() == self._hwnd

    def _wait_ready(self) -> bool:
        """等窗口恢复响应：卡顿时原地等，恢复后把卡顿系数放大一档。

        返回 False 表示等待期间被中断（ESC 或 stop()）。
        """

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
                # 刚卡过一次说明机器/游戏确实吃力：把后续等待整体放慢，上限 4 倍
                self._lag_factor = min(
                    self._lag_factor * 1.3, self.config.max_lag_factor
                )
                return True
        self._log(
            f"游戏卡顿超过 {self.config.max_hung_wait:.0f}s，仍按原顺序继续"
        )
        return True

    def _input_dispatched(self) -> bool:
        """输入后回探：窗口在 post_input_probe_ms 内响应，说明按键已经被处理。"""

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
        """可中断的等待，返回实际耗时（秒）。

        seconds: 期望秒数；align 为 None 时按配置决定是否对齐到 tick；
        scale=True 时乘上卡顿系数；allow_abort=True 时等待中按 ESC 会抛 _Aborted。
        """

        if seconds <= 0:
            return 0.0
        # 卡顿系数 >1 时整体放慢：游戏越卡，给它的处理时间就该越长
        target = seconds * (self._lag_factor if scale else 1.0)
        use_align = self.config.align_ticks if align is None else align
        if use_align:
            # 向上取整到整 tick：宁可多等一点，也不要“差一点点没到下一个 tick”
            target = math.ceil(round(target / TICK, 6)) * TICK

        start = self._transport_now()
        deadline = start + target
        while True:
            if allow_abort and self._abort_requested():
                raise _Aborted()
            remain = deadline - self._transport_now()
            if remain <= 0:
                break
            # 分段睡：每次最多 50ms，保证 ESC / stop() 能被及时发现
            self._transport.sleep(min(remain, 0.05))

        elapsed = self._transport_now() - start
        if self.config.adaptive_pacing:
            if elapsed > target * 1.5 + 0.02:
                # 实际耗时明显超预期：说明系统调度不过来，后续放慢 15%
                self._lag_factor = min(
                    self._lag_factor * 1.15, self.config.max_lag_factor
                )
            elif self._lag_factor > 1.0:
                # 睡得很准时：每次收回 2%，慢慢回到 1.0，避免系数来回抖动
                self._lag_factor = max(1.0, self._lag_factor * 0.98)
        return elapsed

    def _abort_requested(self) -> bool:
        """是否应该中断：stop() 已置位，或者中断键正被按住。"""

        if self._stop:
            return True
        key = self.config.abort_key
        if not key:
            return False
        return self._transport.key_down(key)

    def _wait_abort_key_released(self, timeout: float = 3.0) -> None:
        """开始注入前确认中断键已松开，避免玩家还按着 ESC 就被立刻中断。"""

        key = self.config.abort_key
        if not key or not self._transport.key_down(key):
            return
        self._log(f"检测到 {key.upper()} 还按着，等它松开…")
        # 最多等 timeout 秒，超时就继续（不能因为玩家按着键就永远不启动）
        deadline = self._transport_now() + timeout
        while self._transport.key_down(key) and self._transport_now() < deadline:
            self._transport.sleep(0.2)

    # ------------------------------ 剪贴板 / 工具 ------------------------------ #
    def _transport_now(self) -> float:
        """当前时间（秒），统一从 Transport 取，测试里可以换成假时钟。"""

        return self._get_transport().now()

    def _get_transport(self) -> Transport:
        """首次使用时才创建真实的 Win32Transport 实例（测试传入假实现时不会走到这里）。"""

        if self._transport is None:
            self._transport = Win32Transport()
        return self._transport

    def _transport_safe_clipboard(self) -> Optional[str]:
        """尽力读一份剪贴板内容，任何异常都当作“没读到”（返回 None）。"""

        try:
            return self._get_transport().clipboard_get()
        except Exception:  # noqa: BLE001
            return None

    def _restore_clipboard(self) -> None:
        """把开始时保存的剪贴板内容写回去；没保存过就什么也不做。"""

        saved = getattr(self, "_saved_clipboard", None)
        if self.config.restore_clipboard and saved is not None:
            try:
                if self._get_transport().clipboard_set(saved):
                    self._log("已还原原有剪贴板内容")
            except Exception:  # noqa: BLE001
                pass
        # 无论还原成功与否都清掉，避免下一轮误用上一轮的旧内容
        self._saved_clipboard = None

    def _log(self, message: str) -> None:
        """写一行日志：统一加 [自动输入] 前缀，按配置决定是否带时间。"""

        text = (
            f"[自动输入 {time.strftime('%H:%M:%S')}] {message}"
            if self.config.log_time
            else f"[自动输入] {message}"
        )
        # 没传 logger 时静默丢弃（测试 / 无界面场景）
        if self._logger:
            self._logger(text)


# =================================== #
# @Section: Win32 实现                 #
# =================================== #
# 以下都是 Win32 API 常量，数值取自 Windows SDK 头文件；不要凭感觉修改
# SendInput 的事件类型：1 = 键盘事件（另有鼠标 / 硬件事件）
INPUT_KEYBOARD = 1
# KEYEVENTF_* 是 SendInput 的行为标志位，按位或组合使用
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
# MapVirtualKeyW 的转换类型：0 = 虚拟键码 → 扫描码
MAPVK_VK_TO_VSC = 0
# ShowWindow 参数：还原一个被最小化的窗口
SW_RESTORE = 9
# 空窗口消息：只用来探测“窗口还在不在处理消息”，不会改变窗口状态
WM_NULL = 0x0000
# SendMessageTimeout 标志：SMTO_BLOCK 先阻塞再发，SMTO_ABORTIFHUNG 目标挂起就立即返回
SMTO_BLOCK = 0x0001
SMTO_ABORTIFHUNG = 0x0002
# 剪贴板相关：CF_UNICODETEXT = Unicode 文本格式，GMEM_MOVEABLE = 可移动的全局内存块
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

# 常用虚拟键码（VK_*），数值来自 Win32 定义
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_SHIFT = 0x10
VK_CONTROL = 0x11
# Alt 键在 Win32 里叫 VK_MENU（菜单键）
VK_MENU = 0x12
VK_TAB = 0x09
VK_SPACE = 0x20

# 名字 → 虚拟键码：让配置里的 "esc" / "ctrl" 这类字符串能被 _resolve_vk() 转成数值
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


# 下面这些结构体必须与 Windows SDK 里的布局逐字段一致，SendInput 才能正确解释内存
if IS_WINDOWS:
    from ctypes import wintypes

    class KEYBDINPUT(ctypes.Structure):
        """SendInput 的键盘事件：wScan 是扫描码，dwFlags 说明按下/抬起以及是否按扫描码发送。"""

        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class MOUSEINPUT(ctypes.Structure):
        """鼠标事件结构；本项目只发键盘事件，它作为联合体成员占位，保证 INPUT 布局正确。"""

        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        """硬件事件结构；同样只是联合体的合法成员，本项目不会构造它。"""

        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class _INPUTUNION(ctypes.Union):
        """三种输入的联合体：同一块内存按 type 解释成键盘 / 鼠标 / 硬件事件。"""

        _fields_ = [
            ("ki", KEYBDINPUT),
            ("mi", MOUSEINPUT),
            ("hi", HARDWAREINPUT),
        ]

    class INPUT(ctypes.Structure):
        """SendInput 的入参：type 决定 union 里哪一份有效（本项目固定用 ki）。"""

        _anonymous_ = ("union",)
        _fields_ = [("type", wintypes.DWORD), ("union", _INPUTUNION)]

    # EnumWindows 的回调类型：返回 True 表示继续枚举下一个窗口
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def is_supported() -> bool:
    """当前平台是否支持真实键鼠注入（只有 Windows 支持）。"""

    return IS_WINDOWS


class Win32Transport:
    """真实注入：SendInput + 窗口激活 + 消息泵探测 + 剪贴板."""

    def __init__(self) -> None:
        """加载 user32 / kernel32，并为每个用到的 API 声明参数类型。"""

        if not IS_WINDOWS:
            raise RuntimeError("键鼠注入仅支持 Windows")
        # use_last_error=True：出错时可用 ctypes.get_last_error() 取到 Windows 错误码
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

        # 逗号分隔的类名转成集合；比较时区分大小写（Win32 类名本身就是大小写敏感的）
        allowed = {item.strip() for item in str(klass or "").split(",") if item.strip()}
        hits: list = []

        # 枚举所有顶层窗口；回调返回 True 表示继续枚举下一个
        @WNDENUMPROC
        def callback(hwnd, _lparam):
            # 只看可见窗口：隐藏在托盘或隐藏的辅助窗口不可能是游戏主窗口
            if not self._user32.IsWindowVisible(hwnd):
                return True
            cls = _window_class(self._user32, hwnd)
            if cls not in allowed:
                return True
            title = _window_text(self._user32, hwnd)
            if not title:
                return True
            # 取进程 ID 只是为了日志/诊断能对上任务管理器里的进程
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

        # 排序规则：标题命中关键词的优先（False 排在 True 前），其次标题更短的优先
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
            # 这里故意不按类名过滤：诊断就是要把“标题像游戏”的启动器也列出来
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
        """句柄是否仍然有效（窗口关闭后旧句柄会失效，需要重新找窗口）。"""

        return bool(self._user32.IsWindow(hwnd))

    def foreground(self) -> int:
        """当前前台窗口的句柄。"""

        return int(self._user32.GetForegroundWindow())

    def activate(self, hwnd: int) -> bool:
        """把窗口切到前台：先还原最小化，再临时附加输入线程抢焦点。返回是否成功。"""

        user32 = self._user32
        # 最小化的窗口不能直接被 SetForegroundWindow，必须先还原
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        # AttachThreadInput 要求双方线程都不忙，所以把目标线程和当前前台线程都挂上
        target_thread = user32.GetWindowThreadProcessId(hwnd, None)
        current_thread = self._kernel32.GetCurrentThreadId()
        foreground = user32.GetForegroundWindow()
        foreground_thread = (
            user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
        )
        attached: list = []
        # 用集合去重：目标线程有时正好就是当前前台线程
        for thread in {int(target_thread), int(foreground_thread)}:
            if thread and thread != current_thread:
                if user32.AttachThreadInput(current_thread, thread, True):
                    attached.append(thread)
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
        finally:
            # 无论成功与否都必须解挂，否则会影响后续所有窗口操作
            for thread in attached:
                user32.AttachThreadInput(current_thread, thread, False)
        # 给系统 50ms 完成焦点切换，再核对一次实际结果
        time.sleep(0.05)
        return int(user32.GetForegroundWindow()) == int(hwnd)

    def responsive(self, hwnd: int, timeout_ms: int) -> bool:
        """在 timeout_ms 内给窗口发一个空消息；能返回就说明它还在处理消息（没卡死）。"""

        result = ctypes.c_size_t(0)
        # ABORTIFHUNG：目标线程已挂起就立刻失败，不必等满整个超时
        flags = SMTO_BLOCK | SMTO_ABORTIFHUNG
        ok = self._user32.SendMessageTimeoutW(
            hwnd, WM_NULL, 0, 0, flags, max(int(timeout_ms), 1), ctypes.byref(result)
        )
        return bool(ok)

    # ------ 按键 ------ #
    def key_down(self, key: str) -> bool:
        """该键当前是否被按住（GetAsyncKeyState 的最高位为 1 表示按下）。"""

        vk = _resolve_vk(key)
        if vk is None:
            return False
        return bool(self._user32.GetAsyncKeyState(vk) & 0x8000)

    def tap(self, key: str, hold: float) -> bool:
        """按下 → 保持 hold 秒 → 抬起；hold 至少 5ms，太短系统会把事件合并掉。"""

        vk = _resolve_vk(key)
        if vk is None:
            return False
        self._send(vk, False)
        time.sleep(max(hold, 0.005))
        self._send(vk, True)
        return True

    def chord(self, modifiers: Sequence[str], key: str, hold: float) -> bool:
        """组合键：按住全部修饰键 → 按主键 → 松开主键 → 逆序松开修饰键。"""

        # 认不出来的修饰键直接跳过（配置里写错名字时不至于整段失效）
        keys = [vk for vk in (_resolve_vk(item) for item in modifiers) if vk is not None]
        target = _resolve_vk(key)
        if target is None:
            return False
        for vk in keys:
            self._send(vk, False)
        self._send(target, False)
        time.sleep(max(hold, 0.005))
        self._send(target, True)
        # 逆序松开修饰键，符合真实键盘的操作顺序
        for vk in reversed(keys):
            self._send(vk, True)
        return True

    def type_text(self, text: str, hold: float, gap: float) -> list:
        """逐字符模拟输入，返回当前键盘布局打不出来的字符列表。

        VkKeyScanW 把字符映射成“虚拟键码 + 是否需要 Shift”；映射不了（返回 -1）
        的字符（例如中文）会被收集起来，交给调用方提示用户。
        """

        unsupported: list = []
        for char in text:
            res = self._user32.VkKeyScanW(char)
            if res == -1:
                unsupported.append(char)
                continue
            # 低字节是虚拟键码，bit0 表示这个字符需要配合 Shift
            vk = res & 0xFF
            shift = bool((res >> 8) & 0x01)
            if shift:
                self._send(VK_SHIFT, False)
            self._send(vk, False)
            time.sleep(max(hold, 0.002))
            self._send(vk, True)
            if shift:
                self._send(VK_SHIFT, True)
            # 字符之间留出间隔，太快会被输入法或游戏丢掉
            time.sleep(max(gap, 0.002))
        return unsupported

    def _send(self, vk: int, up: bool) -> None:
        """发送一次键盘事件：虚拟键码转扫描码，up 决定是按下还是抬起。"""

        scan = self._user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
        # 用扫描码而不是虚拟键码：游戏（尤其 GLFW）对扫描码的处理更可靠
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
        # 能打开就要立刻关闭：剪贴板是独占资源，一直占着会让别的程序失败
        self._user32.CloseClipboard()
        return True

    def clipboard_get(self) -> Optional[str]:
        """读剪贴板里的 Unicode 文本；没有文本或打不开剪贴板时返回 None。"""

        user32 = self._user32
        if not _open_clipboard(user32):
            return None
        try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return None
            # 剪贴板数据在全局内存里，必须先 GlobalLock 拿到本进程可读的指针
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
        """把文本写入剪贴板；成功返回 True。"""

        user32 = self._user32
        kernel32 = self._kernel32
        # 末尾补 NUL：Windows 剪贴板要求 UTF-16 字符串以两个 0 字节结尾
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
            # 打不开剪贴板就把刚分配的内存还回去，避免泄漏
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
        """单调时钟（秒）：不受用户调整系统时间影响，适合计算时间间隔。"""

        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        """睡指定秒数；负数按 0 处理（time.sleep 不接受负数）。"""

        time.sleep(max(seconds, 0.0))


def _resolve_vk(key: str) -> int | None:
    """把 "esc" / "ctrl" / "t" 这样的名字转成 Win32 虚拟键码；认不出来返回 None。"""

    text = str(key or "").strip().lower()
    if text in VK_MAP:
        return VK_MAP[text]
    # 单个字母/数字直接用 ASCII 码；转大写是因为 Win32 的字母键码就是大写形式
    if len(text) == 1 and text.isalnum():
        return ord(text.upper())
    return None


def _configure_user32(user32) -> None:
    """64 位下 HWND / HANDLE 必须显式声明类型，否则会被截成 32 位."""

    from ctypes import wintypes

    # 键盘注入相关：发送输入、查按键状态、字符→键码、键码→扫描码
    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.VkKeyScanW.argtypes = [ctypes.c_wchar]
    user32.VkKeyScanW.restype = ctypes.c_short
    user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
    user32.MapVirtualKeyW.restype = wintypes.UINT

    # 窗口查询 / 激活相关：句柄有效性、是否最小化、前台是谁、枚举窗口
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

    # 剪贴板相关：打开/关闭剪贴板、清空、读写文本数据
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
    """声明 kernel32 里用到的函数签名（全局内存与线程 ID），同样是为了 64 位安全。"""

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
    """读窗口标题；没有标题（或读取失败）时返回空字符串。"""

    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    # +1 是给结尾的 NUL 留位置（Win32 的字符串长度不包含终止符）
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def _window_class(user32, hwnd: int) -> str:
    """读窗口类名（如 GLFW30），这是识别“是不是游戏窗口”的关键依据。"""

    # 256 是 Win32 对类名长度的约定上限，足够覆盖真实窗口
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, 256)
    return buffer.value


def _open_clipboard(user32, attempts: int = 12, delay: float = 0.03) -> bool:
    """重试打开剪贴板：被别的程序短暂占用时等一会儿再试，全部失败返回 False。"""

    # 默认最多试 12 次、每次隔 30ms（共约 0.36s），足够躲开一次短暂占用
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
        """追加一项检查结果；ok 为 None 表示“只提示、不判失败”。"""

        checks.append({"id": check_id, "ok": ok, "detail": detail})

    if not IS_WINDOWS:
        add("platform", False, "当前系统不是 Windows，执行模式不可用")
        return checks

    add("platform", True, sys.platform)
    # 传输层建不起来（例如非 Windows 或 ctypes 加载失败）就没法继续查后面的项
    try:
        transport = Win32Transport()
    except Exception as error:  # noqa: BLE001
        add("transport", False, str(error))
        return checks
    add("transport", True, "SendInput 可用")

    # 只按类名找窗口；找不到时顺手列一下“标题像 Minecraft”的窗口，方便判断是不是只开了启动器
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
        # 前台/响应/剪贴板只描述“当前状态”：不在前台不算失败，执行时本来就会自动切
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

    # 是否管理员只作提示（ok=None）：普通权限多数情况可用，但游戏若以管理员运行则必须同级
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
