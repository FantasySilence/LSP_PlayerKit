# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 界面冒烟脚本             #
# =================================== #
# 用法：.venv\\Scripts\\python.exe tests\\smoke_app.py

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import webview  # noqa: E402

from lspkit.api import Api  # noqa: E402
from lspkit.app import _start_server  # noqa: E402
from lspkit.paths import web_dir  # noqa: E402
from lspkit.platform.locator import Location  # noqa: E402
from lspkit.platform.storage import Runtime  # noqa: E402
from lspkit.platform.store import Store  # noqa: E402
from lspkit.tools import build_registry  # noqa: E402


def main() -> None:
    data_dir = Path(tempfile.mkdtemp(prefix="lspkit-smoke-"))
    runtime = Runtime(
        location=Location(path=data_dir, source="default", writable=True),
        store=Store(data_dir),
        webview_dir=data_dir / "webview",
    )
    api = Api(runtime, build_registry())
    url = _start_server(web_dir())
    window = webview.create_window("smoke", url=url, js_api=api, width=1280, height=820)
    runtime.window = window

    def report(target, key: str, script: str) -> None:
        try:
            print(f"{key}:", json.dumps(target.evaluate_js(script), ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001
            print(f"{key}: EVAL ERROR {type(exc).__name__}: {exc}")

    def check(target) -> None:
        time.sleep(4)
        try:
            report(
                target,
                "BOOT",
                "({rails: document.querySelectorAll('.rail-item').length,"
                " boot: !!document.querySelector('.boot'),"
                " panels: document.querySelectorAll('.panel').length,"
                " api: window.pywebview ? 'ok' : 'missing'})",
            )

            target.evaluate_js("document.querySelector('.actions .primary').click()")
            time.sleep(2.5)
            report(
                target,
                "PEARL_CALC",
                "({rows: document.querySelectorAll('.data-table tbody tr').length,"
                " decode: Array.from(document.querySelectorAll('.decode-value')).map((e) => e.innerText),"
                " selected: document.querySelectorAll('.data-table tbody tr.active').length,"
                " direction: (document.querySelector('.panel-head .muted') || {}).innerText,"
                " thAlign: getComputedStyle(document.querySelector('.data-table th.num')).textAlign,"
                " firstTick: document.querySelector('.data-table tbody tr td:nth-child(2)').innerText,"
                " arrows: document.querySelectorAll('.sort-arrow').length,"
                " needle: (document.querySelector('.rose g') || {}).getAttribute"
                "   ? document.querySelector('.rose g').getAttribute('style') : ''})",
            )

            target.evaluate_js("document.querySelectorAll('.data-table th')[0].click()")
            time.sleep(0.4)
            report(
                target,
                "SORT_BY_ERROR",
                "((function () {"
                "  const rows = Array.from(document.querySelectorAll('.data-table tbody tr'));"
                "  const values = rows.map((row) => parseFloat(row.children[0].innerText));"
                "  return { first: values[0], min: Math.min.apply(null, values),"
                "           arrows: document.querySelectorAll('.sort-arrow').length };"
                "})())",
            )

            selected_ticks = target.evaluate_js(
                "document.querySelector('.data-table tbody tr.active td:nth-child(2)').innerText"
            )
            target.evaluate_js("document.querySelectorAll('.actions .btn')[1].click()")
            time.sleep(1.5)
            trace_info = target.evaluate_js(
                "({traceTab: (document.querySelector('.tab.active') || {}).innerText,"
                " traceRows: document.querySelectorAll('.trace-panel tbody tr').length,"
                " targets: document.querySelectorAll('.trace-panel tbody tr.target').length,"
                " targetTick: ((document.querySelector('.trace-panel tbody tr.target')"
                "   || {children: []}).children[0] || {}).innerText,"
                " chartGone: !document.querySelector('.chart canvas')})"
            )
            trace_info["selectedTicks"] = selected_ticks
            trace_info["match"] = str(trace_info.get("targetTick")) == str(selected_ticks)
            print("PEARL_TRACE:", json.dumps(trace_info, ensure_ascii=False))

            target.evaluate_js("document.querySelectorAll('.rail-item')[1].click()")
            time.sleep(1.5)
            # 默认 1200gt 在旧算法下没有非负解，改用 400gt 验证解码面板
            target.evaluate_js(
                "const inputs = document.querySelectorAll('.panel input');"
                "const time = inputs[6];"
                "time.value = '400';"
                "time.dispatchEvent(new Event('input', {bubbles: true}));"
            )
            target.evaluate_js("document.querySelector('.actions .primary').click()")
            time.sleep(2.5)
            report(
                target,
                "BORDER_CALC",
                "({rows: document.querySelectorAll('.data-table tbody tr').length,"
                " landing: (document.querySelector('.landing') || {}).innerText,"
                " detail: !!document.querySelector('.detail'),"
                " cards: document.querySelectorAll('.detail-card').length,"
                " valid: !!document.querySelector('.detail .mono'),"
                " title: (document.querySelector('.titles strong') || {}).innerText})",
            )

            target.evaluate_js("document.querySelector('.settings-btn').click()")
            time.sleep(1)
            report(
                target,
                "SETTINGS_DRAWER",
                "({open: !!document.querySelector('.drawer'),"
                " tabs: document.querySelectorAll('.drawer .tab').length,"
                " fields: document.querySelectorAll('.drawer .field').length})",
            )

            target.evaluate_js(
                "const input = document.querySelector('.drawer input[type=number]');"
                "input.value = '4210';"
                "input.dispatchEvent(new Event('input', {bubbles: true}));"
                "document.querySelector('.drawer-actions .primary').click();"
            )
            time.sleep(1.2)
            report(
                target,
                "SETTINGS_SAVE",
                "({toast: (document.querySelector('.toast.success') || {}).innerText || '',"
                " value: document.querySelector('.drawer input[type=number]').value})",
            )

            target.evaluate_js("document.querySelector('.cmd-actions .btn.ghost').click()")
            time.sleep(0.5)
            report(
                target,
                "THEME_TOGGLE",
                "({theme: document.documentElement.dataset.theme})",
            )

            target.evaluate_js(
                "window.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape'}))"
            )
            time.sleep(0.3)
            target.evaluate_js("document.querySelector('.rail-item:last-child').click()")
            time.sleep(0.6)
            report(
                target,
                "ABOUT",
                "({open: !!document.querySelector('.about'),"
                " version: (document.querySelector('.about .version') || {}).innerText,"
                " coming: !!document.querySelector('.rail-item.coming')})",
            )
        except Exception as exc:  # noqa: BLE001
            print("SMOKE ERROR:", type(exc).__name__, exc)
        finally:
            target.destroy()

    webview.start(
        check,
        window,
        debug=False,
        private_mode=False,
        storage_path=str(runtime.webview_dir),
    )


if __name__ == "__main__":
    main()
