# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 应用启动与窗口           #
# =================================== #

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

DEFAULT_SIZE = (1280, 820)
MIN_SIZE = (960, 640)


class _Handler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args) -> None:  # 静默
        return


def _start_server(directory: Path) -> str:
    handler = functools.partial(_Handler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    return f"http://127.0.0.1:{port}/index.html"


def _fatal(message: str, detail: str = "") -> None:
    text = message if not detail else f"{message}\n\n{detail}"
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, "LSP PlayerKit", 0x10)
    except Exception:  # noqa: BLE001
        print(text, file=sys.stderr)


def _acquire_lock(directory: Path):
    """
    单实例锁：第二次启动以只读模式运行（此处只做提示，仍允许打开）.
    """

    try:
        directory.mkdir(parents=True, exist_ok=True)
        lock_path = directory / ".lock"
        handle = open(lock_path, "a+")  # noqa: SIM115
        try:
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            handle.seek(0)
            handle.truncate()
            handle.write(str(os.getpid()))
            handle.flush()
            return handle, True
        except OSError:
            return handle, False
    except Exception:  # noqa: BLE001
        return None, True


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="LSP_PlayerKit")
    parser.add_argument("--dev", action="store_true", help="使用 Vite 开发服务器")
    parser.add_argument("--dev-url", default=os.environ.get("LSPKIT_DEV_URL", "http://127.0.0.1:5173"))
    parser.add_argument("--debug", action="store_true", help="打开 devtools")
    parser.add_argument("--data-dir", default=None, help="自定义数据目录")
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    try:
        location = locator.resolve(args.data_dir)
    except AppError as exc:
        _fatal(exc.message, exc.detail)
        return

    runtime = Runtime(
        location=location,
        store=Store(location.path),
        webview_dir=locator.appdata_dir() / "webview",
    )
    lock_handle, is_primary = _acquire_lock(location.path)

    registry = build_registry()
    api = Api(runtime, registry)

    if args.dev:
        url = args.dev_url
    else:
        dist = web_dir()
        if not (dist / "index.html").exists():
            _fatal(
                "前端资源缺失",
                f"未找到 {dist / 'index.html'}\n请先在 web/ 目录执行 npm run build。",
            )
            return
        url = _start_server(dist)

    prefs = runtime.store.load("app", {})
    window_cfg = prefs.get("window") or {}
    state = {
        "width": int(window_cfg.get("width") or DEFAULT_SIZE[0]),
        "height": int(window_cfg.get("height") or DEFAULT_SIZE[1]),
        "maximized": bool(window_cfg.get("maximized")),
    }

    window = webview.create_window(
        "LSP PlayerKit",
        url=url,
        js_api=api,
        width=state["width"],
        height=state["height"],
        maximized=state["maximized"],
        min_size=MIN_SIZE,
        background_color="#0b0f18",
        text_select=True,
    )
    runtime.window = window

    def _on_maximized() -> None:
        state["maximized"] = True

    def _on_restored() -> None:
        state["maximized"] = False

    def _on_resized(new_width: int, new_height: int) -> None:
        if state["maximized"]:
            return
        if new_width and new_height:
            state["width"] = int(new_width)
            state["height"] = int(new_height)

    def _remember_window() -> None:
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

    try:
        window.events.maximized += _on_maximized
        window.events.restored += _on_restored
        window.events.resized += _on_resized
        window.events.closed += _remember_window
    except Exception:  # noqa: BLE001
        pass

    if not is_primary:
        print("检测到另一个实例正在运行；本次以只读方式打开。", file=sys.stderr)

    icon = icon_path()
    start_kwargs = {
        "debug": args.debug,
        "private_mode": False,
        "storage_path": str(runtime.webview_dir),
    }
    if icon.exists():
        start_kwargs["icon"] = str(icon)

    try:
        webview.start(**start_kwargs)
    except Exception as exc:  # noqa: BLE001
        _fatal(
            "无法启动 WebView",
            "请确认系统已安装 Microsoft Edge WebView2 Runtime。\n"
            f"{type(exc).__name__}: {exc}",
        )
    finally:
        if lock_handle is not None:
            try:
                lock_handle.close()
            except Exception:  # noqa: BLE001
                pass
