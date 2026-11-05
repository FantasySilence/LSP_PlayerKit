# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-06                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 真实注入测试用的「迷你聊天栏」 #
# =================================== #
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


class ChatStub:
    def __init__(self) -> None:
        self._lines: list = []
        self._queue: "queue.Queue" = queue.Queue()
        self._ready = threading.Event()
        self._root: tk.Tk | None = None
        self._entry: tk.Entry | None = None
        self._thread = threading.Thread(target=self._run, name="chat-stub", daemon=True)

    # ------------------------------ 对外 ------------------------------ #
    def start(self) -> "ChatStub":
        self._thread.start()
        if not self._ready.wait(10):
            raise RuntimeError("迷你聊天栏启动超时")
        return self

    def stop(self) -> None:
        try:
            self.call(lambda: self._root.destroy())
        except Exception:  # noqa: BLE001
            pass
        self._thread.join(timeout=3)

    def lines(self) -> list:
        return self.call(lambda: list(self._lines))

    def clear(self) -> None:
        self.call(lambda: self._lines.clear())

    def stall(self, seconds: float) -> None:
        """让 Tk 主线程阻塞指定秒数，模拟 Minecraft 卡顿."""

        def action() -> None:
            time.sleep(seconds)

        self.call(lambda: self._root.after(0, action), wait=False)

    def call(self, fn, wait: bool = True, timeout: float = 5.0):
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
        root = tk.Tk()
        root.title(TITLE)
        root.geometry("460x220+80+80")
        root.attributes("-topmost", True)
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
        root.bind("<KeyPress-t>", lambda _event: entry.focus_set())

        def poll() -> None:
            try:
                while True:
                    job = self._queue.get_nowait()
                    job()
            except queue.Empty:
                pass
            root.after(25, poll)

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
