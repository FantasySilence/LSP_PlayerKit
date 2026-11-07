# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 真实注入测试用的「迷你聊天栏」 #
# =================================== #
# 真实注入辅助层：用真实 Tk 窗口模拟 MC 聊天栏，供 test_puppet_win32 做端到端注入验证。
"""
一个 300 行的假 Minecraft：真实 Tk 窗口 + 聊天栏语义。

- 按 t 聚焦输入行（对应 MC 的聊天键）
- Ctrl+V 粘贴、Enter 收下这一行
- 可以注入卡顿（阻塞 Tk 线程），验证执行器的「输入后回探 + 整条重来」

只用于 tests/test_puppet_win32.py，默认不在 CI 里跑（需要交互桌面）。
"""

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk

TITLE = "Minecraft Stub"
WINDOW_CLASS = "TkTopLevel"
# 窗口类名要传给 Win32Transport；Tk 顶层窗口的类名是 TkTopLevel，
# 测试用它替代 Minecraft 的 GLFW30，从而在不启动游戏的情况下复用同一套查找逻辑。


class ChatStub:
    """在后台线程里持有一个真实 Tk 窗口，所有公开方法都切回 Tk 线程执行.

    窗口里只有一行输入框和一个列表：按 t 聚焦输入框（模拟 MC 聊天键），
    Enter 把非空文本收进列表（模拟聊天栏发送），供测试逐条核对。
    """
    def __init__(self) -> None:
        self._lines: list = []
        self._queue: "queue.Queue" = queue.Queue()
        self._ready = threading.Event()
        self._root: tk.Tk | None = None
        self._entry: tk.Entry | None = None
        # 队列把测试线程的闭包转交给 Tk 主线程；_ready 保证 start() 返回时窗口已映射。
        self._thread = threading.Thread(target=self._run, name="chat-stub", daemon=True)

    # ------------------------------ 对外 ------------------------------ #
    def start(self) -> "ChatStub":
        """启动 Tk 线程并等待窗口真正显示；10 秒未就绪视为环境不可用."""
        self._thread.start()
        if not self._ready.wait(10):
            raise RuntimeError("迷你聊天栏启动超时")
        return self

    def stop(self) -> None:
        """销毁窗口并等待线程退出；窗口已关闭时忽略异常，保证 fixture 清理不失败."""
        try:
            self.call(lambda: self._root.destroy())
        except Exception:  # noqa: BLE001
            pass
        self._thread.join(timeout=3)

    def lines(self) -> list:
        """返回聊天栏收到的完整行列表（副本，避免测试线程直接碰到内部 list）."""
        return self.call(lambda: list(self._lines))

    def clear(self) -> None:
        """清空聊天栏记录，便于同一次测试里分阶段断言."""
        self.call(lambda: self._lines.clear())

    def stall(self, seconds: float) -> None:
        """让 Tk 主线程阻塞指定秒数，模拟 Minecraft 卡顿."""

        def action() -> None:
            time.sleep(seconds)

        # wait=False：只把阻塞任务排进 Tk 事件队列，调用方（测试线程）立刻返回。
        self.call(lambda: self._root.after(0, action), wait=False)

    def call(self, fn, wait: bool = True, timeout: float = 5.0):
        """把 fn 投递到 Tk 线程执行.

        wait=True 时阻塞等待结果，超时抛 RuntimeError；fn 抛出的异常会原样带回调用方。
        这是测试线程与 Tk 主线程之间唯一的同步通道。
        """
        box: list = []
        done = threading.Event()

        def run() -> None:
            try:
                box.append(fn())
            except Exception as error:  # noqa: BLE001
                box.append(error)
            finally:
                done.set()

        self._queue.put(run)
        if not wait:
            return None
        if not done.wait(timeout):
            raise RuntimeError("迷你聊天栏无响应")
        if box and isinstance(box[0], Exception):
            raise box[0]
        return box[0] if box else None

    # ------------------------------ Tk ------------------------------ #
    def _run(self) -> None:
        """Tk 主线程主体：建窗口、绑定聊天键、轮询任务队列，最后进入 mainloop."""
        root = tk.Tk()
        root.title(TITLE)
        root.geometry("460x220+80+80")
        root.attributes("-topmost", True)
        # 置顶并抢焦点，避免测试注入的按键落到别的窗口。
        self._root = root

        entry = tk.Entry(root, width=64, font=("Consolas", 10))
        entry.pack(pady=(10, 6), padx=10, fill="x")
        self._entry = entry

        listbox = tk.Listbox(root, height=7, font=("Consolas", 9))
        listbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._listbox = listbox

        def on_return(_event) -> str:
            text = entry.get()
            entry.delete(0, "end")
            if text.strip():
                self._lines.append(text)
                listbox.insert("end", text)
            root.focus_set()
            return "break"

        entry.bind("<Return>", on_return)
        # 对齐 MC 聊天栏语义：t 聚焦输入行，Enter 收下一行非空文本。
        root.bind("<KeyPress-t>", lambda _event: entry.focus_set())

        def poll() -> None:
            try:
                while True:
                    job = self._queue.get_nowait()
                    job()
            except queue.Empty:
                pass
            root.after(25, poll)
        # 每 25ms 处理一次跨线程任务；stall 也通过这条队列排队。

        root.after(25, poll)
        root.focus_force()
        entry.focus_set()
        root.update()
        while not root.winfo_ismapped():
            root.update()
            time.sleep(0.02)
        self._ready.set()
        try:
            root.mainloop()
        finally:
            pass
