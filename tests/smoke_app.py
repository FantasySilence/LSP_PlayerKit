# =================================== #
# @Author: Fantasy_Silence            #
# @Time: 2026-11-04                   #
# @IDE: Visual Studio Code & PyCharm  #
# @Python: 3.9.7                      #
# =================================== #
# @Descript: 界面冒烟脚本             #
# =================================== #
# 用法：.venv\\Scripts\\python.exe tests\\smoke_app.py
# 这是手动冒烟脚本，不是 pytest 用例（文件名不以 test_ 开头，不会被收集）：
# 真正启动 pywebview 窗口，依次点击五个工具并打印 DOM 观察值，供人工比对。
# 需要桌面环境；运行：.venv\Scripts\python.exe tests\smoke_app.py

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
    """启动临时数据目录 + 本地 Web 服务，创建窗口并执行 check 脚本.

    所有文件对话框都被下面的假实现替换，因此无需人工选择文件；
    check 结束后销毁窗口，webview.start 返回，脚本退出。
    """
    data_dir = Path(tempfile.mkdtemp(prefix="lspkit-smoke-"))
    runtime = Runtime(
        location=Location(path=data_dir, source="default", writable=True),
        store=Store(data_dir),
        webview_dir=data_dir / "webview",
    )
    api = Api(runtime, build_registry())
    url = _start_server(web_dir())

    # 用假文件替换原生对话框，便于无人工干预地验证导入流程
    # 4766/1219/1158 只是冒烟演示数据，与测试快照无关，也不做数值断言。
    material_text = [
        '"Item","Total","Missing","Available"\n'
        '"白色染色玻璃",4766,4766,0\n'
        '"侦测器",1219,1219,0\n'
        '"箱子",1158,1158,0'
    ]
    Api.file_open_text = lambda self: {
        "path": "debug.csv",
        "name": "material_list.csv",
        "text": material_text[0],
    }
    saved = {}

    def fake_save(self, filename, content, directory=""):
        """替换 Api.file_save_text：记录文件名/内容长度/目录，返回假路径，不弹保存框."""
        saved["name"] = filename
        saved["size"] = len(content)
        saved["directory"] = directory
        return {"path": filename}

    Api.file_save_text = fake_save

    window = webview.create_window("smoke", url=url, js_api=api, width=1280, height=820)
    runtime.window = window

    def report(target, key: str, script: str) -> None:
        """在页面里执行一段 JS 并把结果以 JSON 打印；JS 出错只打印错误，不中断流程."""
        try:
            print(f"{key}:", json.dumps(target.evaluate_js(script), ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001
            print(f"{key}: EVAL ERROR {type(exc).__name__}: {exc}")

    def check(target) -> None:
        """等首屏加载后依次操作五个工具，打印各阶段的 DOM 观察值.

        这里没有断言：输出是给人看的冒烟结果。任何 JS 异常都会被捕获并打印
        SMOKE ERROR，最后销毁窗口。
        """
        time.sleep(4)
        # 等 WebView 完成加载与首屏渲染；具体时长依赖机器，冒烟脚本容忍固定等待。
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
            # 点「计算」按钮，等结果表格与解码面板渲染。
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

            target.evaluate_js("document.querySelectorAll('.secondary-actions .btn')[0].click()")
            time.sleep(0.8)
            report(
                target,
                "PEARL_SAVE_DEFAULT",
                "({toast: (document.querySelector('.toast.success') || {}).innerText || '',"
                " buttons: document.querySelectorAll('.secondary-actions .btn').length})",
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
            # ------ 边境炮 ------ #

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

            target.evaluate_js("document.querySelectorAll('.secondary-actions .btn')[0].click()")
            time.sleep(0.8)
            report(
                target,
                "BORDER_SAVE_DEFAULT",
                "({toast: (document.querySelector('.toast.success') || {}).innerText || '',"
                " buttons: document.querySelectorAll('.secondary-actions .btn').length})",
            )
            # ------ 材料换算 ------ #

            target.evaluate_js("document.querySelectorAll('.rail-item')[2].click()")
            time.sleep(1.2)
            target.evaluate_js("document.querySelector('.import-btn').click()")
            time.sleep(2)
            report(
                target,
                "MATERIAL_IMPORT",
                "({listRows: document.querySelectorAll('.list-row').length,"
                " first: ((document.querySelector('.list-row') || {children: []}).children[1] || {}).innerText,"
                " firstCount: ((document.querySelector('.list-row') || {children: []}).children[3] || {}).innerText,"
                " rows: document.querySelectorAll('.data-table tbody tr').length,"
                " stats: Array.from(document.querySelectorAll('.stat-value')).map((e) => e.innerText),"
                " stack: (document.querySelector('.segmented button.active') || {}).innerText,"
                " toast: (document.querySelector('.toast.success') || {}).innerText || '',"
                " align: getComputedStyle(document.querySelector('.data-table th')).textAlign})",
            )

            target.evaluate_js(
                "document.querySelectorAll('.list-row input[type=checkbox]')[0].click();"
                "document.querySelectorAll('.list-row input[type=checkbox]')[1].click();"
            )
            time.sleep(0.4)
            target.evaluate_js(
                "(function () {"
                "  const select = document.querySelector('.batch-select');"
                "  select.value = '1';"
                "  select.dispatchEvent(new Event('change', {bubbles: true}));"
                "})()"
            )
            time.sleep(0.3)
            target.evaluate_js("document.querySelector('.batch .btn').click()")
            time.sleep(1.8)
            report(
                target,
                "MATERIAL_BATCH",
                "({picked: document.querySelectorAll('.list-row.picked').length,"
                " chips: Array.from(document.querySelectorAll('.stack-chip')).slice(0, 3).map((e) => e.innerText),"
                " cells: Array.from(document.querySelector('.data-table tbody tr').children).map((c) => c.innerText)})",
            )

            target.evaluate_js("document.querySelectorAll('.stack-filter button')[3].click()")
            time.sleep(0.6)
            report(
                target,
                "MATERIAL_FILTER",
                "({rows: document.querySelectorAll('.data-table tbody tr').length,"
                " stacks: Array.from(document.querySelectorAll('.data-table tbody tr td:nth-child(2)')).map((c) => c.innerText)})",
            )

            target.evaluate_js("document.querySelectorAll('.stack-filter button')[0].click()")
            time.sleep(0.6)
            target.evaluate_js("document.querySelectorAll('.data-table th')[2].click()")
            time.sleep(0.6)
            report(
                target,
                "MATERIAL_SORT",
                "({rows: document.querySelectorAll('.data-table tbody tr').length,"
                " arrow: (document.querySelector('.sort-arrow') || {}).innerText,"
                " firstCount: (document.querySelector('.data-table tbody tr td:nth-child(3)') || {}).innerText})",
            )

            target.evaluate_js("document.querySelector('.sort-btn').click()")
            time.sleep(0.5)
            report(
                target,
                "MATERIAL_LIST_SORT",
                "({arrow: (document.querySelector('.sort-btn .arrow') || {}).innerText,"
                " firstCount: ((document.querySelector('.list-row') || {children: []}).children[3] || {}).innerText})",
            )

            target.evaluate_js("document.querySelectorAll('.actions .btn')[1].click()")
            time.sleep(3)
            report(
                target,
                "MATERIAL_PACK",
                "({open: !!document.querySelector('.packing'),"
                " cards: document.querySelectorAll('.box-card').length,"
                " listItems: document.querySelectorAll('.box-index-item').length,"
                " detail: !!document.querySelector('.box-detail'),"
                " summary: (document.querySelector('.packing-summary') || {}).innerText})",
            )
            target.evaluate_js(
                "const items = document.querySelectorAll('.box-index-item');"
                "if (items.length > 1) items[1].click()"
            )
            time.sleep(0.6)
            report(
                target,
                "MATERIAL_PACK_SELECT",
                "({active: (document.querySelector('.box-index-item.active') || {}).innerText || '',"
                " entries: document.querySelectorAll('.detail-list .pack-entry').length,"
                " head: (document.querySelector('.detail-head .box-no') || {}).innerText || ''})",
            )
            target.evaluate_js("document.querySelector('.packing-foot .btn.primary').click()")
            time.sleep(0.8)

            target.evaluate_js(
                "document.querySelectorAll('.list-row input[type=checkbox]')[0].click();"
                "document.querySelectorAll('.list-row input[type=checkbox]')[1].click();"
            )
            time.sleep(0.4)
            target.evaluate_js("document.querySelectorAll('.batch .btn')[1].click()")
            time.sleep(1.8)
            report(
                target,
                "MATERIAL_IGNORE",
                "({ignored: document.querySelectorAll('.list-row.ignored').length,"
                " panelRows: document.querySelectorAll('.ignored-row').length,"
                " selected: (document.querySelector('.list-head') || {}).innerText || '',"
                " rows: document.querySelectorAll('.data-table tbody tr').length})",
            )
            target.evaluate_js("document.querySelector('.ignored-head .sort-btn').click()")
            time.sleep(1.8)
            report(
                target,
                "MATERIAL_RESTORE",
                "({ignored: document.querySelectorAll('.list-row.ignored').length,"
                " rows: document.querySelectorAll('.data-table tbody tr').length})",
            )

            target.evaluate_js(
                "(function () {"
                "  const input = document.querySelector('.search-input');"
                "  input.focus();"
                "  input.value = '箱';"
                "  input.dispatchEvent(new Event('input', {bubbles: true}));"
                "})()"
            )
            time.sleep(0.6)
            report(
                target,
                "MATERIAL_SEARCH",
                "({rows: document.querySelectorAll('.list-row').length,"
                " suggestions: document.querySelectorAll('.suggestion').length,"
                " first: (document.querySelector('.suggestion-name') || {}).innerText || ''})",
            )
            target.evaluate_js(
                "(function () {"
                "  const input = document.querySelector('.search-input');"
                "  input.value = '';"
                "  input.dispatchEvent(new Event('input', {bubbles: true}));"
                "  input.blur();"
                "})()"
            )
            time.sleep(0.5)

            target.evaluate_js("document.querySelector('.settings-btn').click()")
            time.sleep(1.2)
            report(
                target,
                "MATERIAL_SETTINGS",
                "({groups: document.querySelectorAll('.drawer .group').length,"
                " textInputs: document.querySelectorAll('.drawer input[type=text]').length,"
                " pick: (document.querySelector('.path-field .btn') || {}).innerText || ''})",
            )
            target.evaluate_js(
                "window.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape'}))"
            )
            time.sleep(0.6)

            report(
                target,
                "MATERIAL_EXPORT_DIR",
                "({placeholder: (document.querySelectorAll('.export-input')[1] || {}).placeholder || ''})",
            )
            target.evaluate_js(
                "(function () {"
                "  const input = document.querySelectorAll('.export-input')[1];"
                "  input.value = 'D:\\\\smoke_out';"
                "  input.dispatchEvent(new Event('input', {bubbles: true}));"
                "  input.dispatchEvent(new Event('change', {bubbles: true}));"
                "})()"
            )
            time.sleep(1)

            target.evaluate_js(
                "(function () {"
                "  const input = document.querySelector('.export-input');"
                "  input.value = 'my_plan.csv';"
                "  input.dispatchEvent(new Event('input', {bubbles: true}));"
                "})()"
            )
            time.sleep(0.3)
            target.evaluate_js("document.querySelectorAll('.actions .btn')[2].click()")
            time.sleep(0.8)
            print("MATERIAL_EXPORT:", json.dumps(saved, ensure_ascii=False))

            target.evaluate_js(
                "(function () {"
                "  const input = document.querySelector('.export-input');"
                "  input.value = '';"
                "  input.dispatchEvent(new Event('input', {bubbles: true}));"
                "})()"
            )
            time.sleep(0.3)
            target.evaluate_js("document.querySelectorAll('.actions .btn')[2].click()")
            time.sleep(0.8)
            print("MATERIAL_EXPORT_DEFAULT:", json.dumps(saved, ensure_ascii=False))

            material_text[0] = "no numbers here"
            target.evaluate_js("document.querySelector('.import-btn').click()")
            time.sleep(1.2)
            report(
                target,
                "MATERIAL_BAD_FILE",
                "({toast: (document.querySelector('.toast.error') || {}).innerText || '',"
                " rows: document.querySelectorAll('.data-table tbody tr').length})",
            )
            # ------ 设置与关于 ------ #

            target.evaluate_js("document.querySelectorAll('.rail-item')[0].click()")
            time.sleep(1.2)

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
