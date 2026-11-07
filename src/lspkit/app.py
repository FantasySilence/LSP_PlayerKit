# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 应用启动与窗口           #
# =================================== #
# 本文件职责：把“数据目录、工具注册表、WebView 窗口、本地静态服务”拼装起来并启动。
# 进程内只做这一次启动装配；具体业务能力都由 Api / Registry 提供。

from __future__ import annotations

import argparse
import functools
import os
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import webview

from lspkit.api import Api
from lspkit.errors import AppError
from lspkit.paths import app_dir, icon_path, web_dir
from lspkit.platform import locator
from lspkit.platform.storage import Runtime
from lspkit.platform.store import Store
from lspkit.tools import build_registry

# 首次启动时的窗口尺寸（像素）；之后会以用户上次调整的大小为准
DEFAULT_SIZE = (1280, 820)
# 窗口允许缩到的最小尺寸，再小界面元素就挤在一起了
MIN_SIZE = (960, 640)


class _Handler(SimpleHTTPRequestHandler):
    """静态文件服务处理器：把 web/dist 里的前端文件提供给 WebView（只监听本机）。"""

    def end_headers(self) -> None:
        """统一加上禁用缓存的响应头，保证刷新后拿到的是最新前端代码。"""

        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args) -> None:  # 静默
        return


def _start_server(directory: Path) -> str:
    """在后台线程启动一个随机端口的本地 HTTP 服务，返回 index.html 的访问地址。"""

    handler = functools.partial(_Handler, directory=str(directory))
    # 端口写 0 表示让系统随机分配，避免和用户机器上其它程序抢端口
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    return f"http://127.0.0.1:{port}/index.html"


def _fatal(message: str, detail: str = "") -> None:
    """启动阶段的致命错误：弹 Windows 消息框；弹不出来就写到 stderr。"""

    text = message if not detail else f"{message}\n\n{detail}"
    try:
        import ctypes

        # 0x10 = MB_ICONERROR（红叉图标）。此时 WebView 还没起来，只能用系统对话框
        ctypes.windll.user32.MessageBoxW(None, text, "LSP PlayerKit", 0x10)
    except Exception:  # noqa: BLE001
        print(text, file=sys.stderr)


def _acquire_lock(directory: Path):
    """
    单实例锁：第二次启动以只读模式运行（此处只做提示，仍允许打开）.

    返回 (文件句柄, 是否第一个实例)；拿不到锁时仍返回句柄，但第二项为 False。
    """

    try:
        directory.mkdir(parents=True, exist_ok=True)
        lock_path = directory / ".lock"
        handle = open(lock_path, "a+")  # noqa: SIM115
        try:
            import msvcrt

            # LK_NBLCK = 非阻塞加锁：拿不到立刻抛 OSError，不会卡住启动
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            # 抢到锁后清空旧内容并写入当前进程号，方便排查是谁在占用
            handle.seek(0)
            handle.truncate()
            handle.write(str(os.getpid()))
            handle.flush()
            return handle, True
        except OSError:
            # 已有实例持锁：本次照常开窗口，只是提示“以只读方式打开”
            return handle, False
    except Exception:  # noqa: BLE001
        # 连锁文件都建不出来时不影响使用，直接当作第一个实例
        return None, True


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数；argv 为 None 时读 sys.argv（测试可以传入自己的列表）。"""

    parser = argparse.ArgumentParser(prog="LSP_PlayerKit")
    # --dev：前端改走 Vite 开发服务器（热更新），改前端时用
    parser.add_argument("--dev", action="store_true", help="使用 Vite 开发服务器")
    # --dev-url：开发服务器地址，可用环境变量覆盖，默认 Vite 的 5173 端口
    parser.add_argument("--dev-url", default=os.environ.get("LSPKIT_DEV_URL", "http://127.0.0.1:5173"))
    # --debug：打开 WebView 的开发者工具（F12 面板）
    parser.add_argument("--debug", action="store_true", help="打开 devtools")
    # --data-dir：临时指定数据目录，优先级高于所有配置文件
    parser.add_argument("--data-dir", default=None, help="自定义数据目录")
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> None:
    """应用主流程：解析参数 → 定位数据目录 → 建注册表 → 开窗口 → 进入 WebView 事件循环。"""

    args = _parse_args(argv)

    # 数据目录连兜底都不可写时无法继续，直接弹窗并退出
    try:
        location = locator.resolve(args.data_dir)
    except AppError as exc:
        _fatal(exc.message, exc.detail)
        return

    runtime = Runtime(
        location=location,
        store=Store(location.path),
        # WebView2 的缓存单独放 AppData，避免用户在自己的数据目录里看到一堆浏览器文件
        webview_dir=locator.appdata_dir() / "webview",
    )
    lock_handle, is_primary = _acquire_lock(location.path)

    # 注册表启动时一次建好，前端拿到的工具清单完全来自这里
    registry = build_registry()
    api = Api(runtime, registry)

    if args.dev:
        # 开发模式：前端由 Vite 提供（带热更新），不需要本地 dist
        url = args.dev_url
    else:
        dist = web_dir()
        if not (dist / "index.html").exists():
            _fatal(
                "前端资源缺失",
                f"未找到 {dist / 'index.html'}\n请先在 web/ 目录执行 npm run build。",
            )
            return
        # 用本地 HTTP 起静态服务（而不是 file://），前端路由与 fetch 才能正常工作
        url = _start_server(dist)

    prefs = runtime.store.load("app", {})
    window_cfg = prefs.get("window") or {}
    # state 是内存中的“当前窗口状态”，窗口关闭时再写回配置
    state = {
        "width": int(window_cfg.get("width") or DEFAULT_SIZE[0]),
        "height": int(window_cfg.get("height") or DEFAULT_SIZE[1]),
        "maximized": bool(window_cfg.get("maximized")),
    }

    window = webview.create_window(
        "LSP PlayerKit",
        url=url,
        # js_api 就是前端 window.pywebview.api 能调用到的对象
        js_api=api,
        width=state["width"],
        height=state["height"],
        maximized=state["maximized"],
        min_size=MIN_SIZE,
        # 与前端深色主题一致的底色，避免页面加载瞬间闪白
        background_color="#0b0f18",
        text_select=True,
    )
    runtime.window = window

    def _on_maximized() -> None:
        """窗口最大化时记下标记，避免把最大化后的尺寸当成普通尺寸保存。"""

        state["maximized"] = True

    def _on_restored() -> None:
        """窗口从最大化还原时清除标记。"""

        state["maximized"] = False

    def _on_resized(new_width: int, new_height: int) -> None:
        """普通缩放时更新内存里的尺寸；最大化状态下忽略，否则会存成全屏大小。"""

        if state["maximized"]:
            return
        if new_width and new_height:
            state["width"] = int(new_width)
            state["height"] = int(new_height)

    def _remember_window() -> None:
        """关窗时把窗口尺寸写回配置；写失败也不影响退出（异常直接吞掉）。"""

        try:
            current = runtime.store.load("app", {})
            current["window"] = {
                "width": state["width"],
                "height": state["height"],
                "maximized": state["maximized"],
            }
            runtime.store.save("app", current)
        except Exception:  # noqa: BLE001
            pass

    # 注册窗口事件；个别平台/版本没有这些事件，注册失败也不该阻止启动
    try:
        window.events.maximized += _on_maximized
        window.events.restored += _on_restored
        window.events.resized += _on_resized
        window.events.closed += _remember_window
    except Exception:  # noqa: BLE001
        pass

    if not is_primary:
        # 只做提示：第二个实例照常打开窗口，但两份界面读写的是同一份配置
        print("检测到另一个实例正在运行；本次以只读方式打开。", file=sys.stderr)

    icon = icon_path()
    start_kwargs = {
        "debug": args.debug,
        "private_mode": False,
        "storage_path": str(runtime.webview_dir),
    }
    if icon.exists():
        # 图标文件缺失时不传这个参数，让系统用默认图标
        start_kwargs["icon"] = str(icon)

    try:
        # 阻塞在这里直到窗口关闭，之后才执行 finally
        webview.start(**start_kwargs)
    except Exception as exc:  # noqa: BLE001
        _fatal(
            "无法启动 WebView",
            "请确认系统已安装 Microsoft Edge WebView2 Runtime。\n"
            f"{type(exc).__name__}: {exc}",
        )
    finally:
        # 退出时释放单实例锁，下次启动才能正常写入
        if lock_handle is not None:
            try:
                lock_handle.close()
            except Exception:  # noqa: BLE001
                pass
