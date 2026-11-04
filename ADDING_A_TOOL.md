# 新增工具说明

这份文档以「简单的数学计算器」为例，完整走一遍从后端到前端的接入流程：输入两个数、选一个运算符，算出结果并留下历史记录。

> 约定：工具 id 在目录名、manifest、视图目录、i18n 文件名里保持一致，这里统一用 `calc`。
>
> 文档里的 `calc` 只是示例，不会真的出现在应用里；照着做时请换成你自己的 id。

---

## 0. 项目结构（开发者向）

应用是「Python 外壳 + Vue 前端」，两边通过一条 JSON-RPC 通信。先认识一下分层，再动手加工具。

```text
LSP_PlayerKit/
├─ main.py                     入口：把 src/ 加入 sys.path 后启动
├─ src/lspkit/
│  ├─ app.py                   窗口、本地静态服务、窗口状态持久化
│  ├─ api.py                   JS ↔ Python 的唯一门面，统一 {ok, data|error} 信封
│  ├─ paths.py                 资源 / 数据目录解析（开发、打包、便携）
│  ├─ platform/                与业务无关的公共层
│  │  ├─ locator.py            数据目录解析与只读回退
│  │  ├─ store.py              JSON 原子写、备份轮转
│  │  ├─ schema.py             设置字段描述符（校验 + 表单 + 默认值）
│  │  ├─ registry.py           工具注册表、动作分发、Context
│  │  ├─ storage.py            数据目录切换、配置包导入导出
│  │  └─ params.py             请求参数校验
│  └─ tools/
│     ├─ pearl/                珍珠炮工具（完整示例）
│     ├─ border/               边境炮工具（完整示例）
│     ├─ material/             材料换算工具（带纯计算 core/ 与弹窗）
│     └─ _template/            新工具脚手架
├─ web/
│  ├─ src/
│  │  ├─ App.vue               外壳：左轨、命令栏、设置入口、关于
│  │  ├─ platform/             bridge / i18n / settings / theme / toast
│  │  ├─ shell/                SettingsDrawer、AboutDialog
│  │  ├─ ui/                   通用组件：DataTable、CompassRose、ToastHost
│  │  ├─ tools/<id>/View.vue   工具页面（外壳按 id 懒加载）
│  │  └─ i18n/                 外壳文案（工具文案在各自 tools/<id>/i18n/）
│  └─ dist/                    构建产物，已提交；运行不依赖 Node
├─ resources/                  图标、文档、version.json（打包进 exe）
├─ tests/                      golden 快照、API 契约、架构边界
├─ README_img/                 README 截图
└─ packaging/                  PyInstaller spec
```

一次调用的链路：

```text
View.vue
  └─ callTool('calc', 'evaluate', { a: 2, b: 3, op: 'add' })
       └─ window.pywebview.api.tool_call(tool, action, payload)
            └─ api.Api.tool_call → Registry.call
                 └─ tools/calc/actions.py：evaluate_action(payload, ctx)
                      ├─ ctx.settings('calc') 读取该工具的设置
                      └─ core/calc.py 纯函数计算
                 ← { ok: true, data: { expression, result } }
```

三条分层规则：

- `tools/<id>` 只依赖 `platform` 与自己的目录，**不 import 其他工具**
- `platform` 不含任何业务逻辑或魔法数字
- `actions.py` 只做参数校验与返回值组装；算法放 `core/`，且 `core/` 不碰 IO（不读文件、不读设置）

## 1. 复制脚手架

```powershell
Copy-Item src\lspkit\tools\_template src\lspkit\tools\calc -Recurse
```

复制后先删掉 `__pycache__`，再把四个占位文件改成你自己的内容。目录结构：

```text
src/lspkit/tools/calc/
├─ __init__.py       导出 MANIFEST / HANDLERS / LEGACY
├─ manifest.py       工具声明（id、图标、动作、结果列）
├─ schema.py         设置字段
├─ defaults.py       出厂默认值
├─ actions.py        对外动作
├─ legacy.py         旧配置迁移（没有历史格式就原样返回）
├─ constants.py      工具专用常量（可选）
└─ core/             纯计算（可选，但建议有）
   ├─ __init__.py
   └─ calc.py
```

前端手动新建 `web/src/tools/calc/`，至少包含 `View.vue` 和 `i18n/` 三个词条文件。

## 2. 后端：默认值与设置

一个「保留几位小数」的设置就够演示了。

`defaults.py`：

```python
DEFAULT_SETTINGS = {
    "decimals": 2,
}
```

`schema.py`：

```python
from lspkit.platform.schema import Field, Group, SettingsSchema

from .defaults import DEFAULT_SETTINGS as D

SCHEMA = SettingsSchema(
    version=1,
    groups=[
        Group(
            "basic",
            "calc.settings.basic",
            [
                Field(
                    "decimals",
                    "calc.field.decimals",
                    "int",
                    D["decimals"],
                    0,        # 最小值
                    8,        # 最大值
                    1,        # 步进
                    unit="位",
                ),
            ],
        ),
    ],
)
```

`Field` 的参数顺序是 `key, label, type, default, min, max, step, digits, unit, options, hint`；`label` 是 i18n key，不是写死的文案。改这里会自动生成设置抽屉里的表单，不需要写任何 UI 代码。

## 3. 后端：纯计算

`core/calc.py` 不读设置、不抛 `AppError`，只做数学：

```python
OPERATORS = {
    "add": "+",
    "sub": "-",
    "mul": "×",
    "div": "÷",
}


def evaluate(a: float, b: float, op: str) -> float:
    if op == "add":
        return a + b
    if op == "sub":
        return a - b
    if op == "mul":
        return a * b
    if op == "div":
        if b == 0:
            raise ZeroDivisionError("divide by zero")
        return a / b
    raise ValueError(f"unknown operator: {op}")
```

`core/` 里不要 `import lspkit.platform`，也不要 import `os` / `pathlib` / `json`——`tests/test_boundaries.py` 会扫描并让违规的提交失败。

## 4. 后端：动作

`actions.py` 负责校验、读设置、调用 `core`、组装返回值：

```python
from lspkit.errors import AppError
from lspkit.platform import params

from .core.calc import OPERATORS, evaluate


def evaluate_action(payload: dict, ctx) -> dict:
    settings = ctx.settings("calc")

    a = params.number(payload, "a", label="第一个数")
    b = params.number(payload, "b", label="第二个数")
    op = params.choice(payload, "op", tuple(OPERATORS), default="add")

    try:
        value = evaluate(a, b, op)
    except ZeroDivisionError:
        raise AppError("DIVIDE_BY_ZERO", "除数不能为 0") from None

    digits = int(settings["decimals"])
    return {
        "expression": f"{a:g} {OPERATORS[op]} {b:g}",
        "result": round(value, digits),
        "op": op,
    }
```

要点：

- 参数缺失或类型不对时，`params.*` 会抛带错误码的 `AppError`，前端会收到 `{ok: false, error}` 而不是 traceback。
- 可预期的错误用 `AppError(错误码, 提示文案)`；错误码建议全大写、稳定不变。
- 返回值必须是 JSON 原生类型（`int / float / str / bool / list / dict`），不要返回 numpy 标量。

## 5. 后端：manifest 与注册

`manifest.py`：

```python
from lspkit.platform.registry import ToolManifest

from .actions import evaluate_action
from .legacy import convert
from .schema import SCHEMA

MANIFEST = ToolManifest(
    id="calc",
    name_key="calc.name",
    description_key="calc.description",
    icon="spark",          # 见 App.vue 里的 ICONS
    order=40,              # 左轨排序：pearl 10 / border 20 / material 30
    version="1.0.0",
    schema=SCHEMA,
    actions=[
        {"id": "evaluate", "labelKey": "calc.action.evaluate"},
    ],
    columns=[
        {"key": "expression", "nameKey": "calc.col.expression", "type": "string"},
        {"key": "result", "nameKey": "calc.col.result", "type": "float", "digits": 4},
    ],
)

HANDLERS = {"evaluate": evaluate_action}

LEGACY = convert
```

`__init__.py`：

```python
from .manifest import HANDLERS, LEGACY, MANIFEST

__all__ = ["MANIFEST", "HANDLERS", "LEGACY"]
```

`legacy.py`（没有旧格式时原样返回）：

```python
def convert(raw: dict) -> dict:
    return raw
```

最后在 `src/lspkit/tools/__init__.py` 注册一行：

```python
from . import border, calc, material, pearl

registry.register(calc.MANIFEST, calc.HANDLERS, calc.LEGACY)
```

左轨按钮、页面标题、设置抽屉都会由 manifest 自动生成，前端只需要提供 `View.vue`。

## 6. 前端：视图

`web/src/tools/calc/View.vue`：

```vue
<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { callTool } from '../../platform/bridge'
import { t } from '../../platform/i18n'
import { loadSettings } from '../../platform/settings'
import { notifyError } from '../../platform/toast'
import type { ColumnDef, ToolDef } from '../../platform/types'
import DataTable from '../../ui/DataTable.vue'

const props = defineProps<{ tool: ToolDef }>()

const a = ref<number | string>(2)
const b = ref<number | string>(3)
const op = ref('add')
const expression = ref('')
const result = ref<number | null>(null)
const history = ref<Record<string, any>[]>([])
const busy = ref(false)

const OP_OPTIONS = ['add', 'sub', 'mul', 'div']

async function evaluate() {
  busy.value = true
  try {
    const data = await callTool<{ expression: string; result: number }>(
      props.tool.id,
      'evaluate',
      { a: Number(a.value), b: Number(b.value), op: op.value },
    )
    expression.value = data.expression
    result.value = data.result
    history.value = [{ ...data }, ...history.value].slice(0, 20)
  } catch (error) {
    notifyError(error)
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  try {
    await loadSettings(props.tool.id)
  } catch (error) {
    notifyError(error)
  }
})
</script>

<template>
  <div class="workbench">
    <section class="panel">
      <div class="panel-head">{{ t('calc.panel.input') }}</div>
      <div class="panel-body">
        <div class="field-row">
          <div class="field">
            <label class="field-label">{{ t('calc.field.a') }}</label>
            <input v-model.number="a" class="input mono" type="number" />
          </div>
          <div class="field">
            <label class="field-label">{{ t('calc.field.b') }}</label>
            <input v-model.number="b" class="input mono" type="number" />
          </div>
        </div>

        <div class="field">
          <label class="field-label">{{ t('calc.field.op') }}</label>
          <select v-model="op" class="input">
            <option v-for="item in OP_OPTIONS" :key="item" :value="item">
              {{ t(`calc.op.${item}`) }}
            </option>
          </select>
        </div>

        <div class="actions">
          <button class="btn primary" :disabled="busy" @click="evaluate">
            {{ t('calc.action.evaluate') }}
          </button>
        </div>

        <div v-if="result !== null" class="answer">
          <span class="mono">{{ expression }}</span>
          <strong class="mono">= {{ result }}</strong>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head">{{ t('calc.panel.history') }}</div>
      <div class="result-body">
        <DataTable :columns="tool.columns" :rows="history" :selected="null" />
      </div>
    </section>
  </div>
</template>

<style scoped>
.workbench {
  height: 100%;
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr);
  gap: 14px;
  min-height: 0;
}

.actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

.actions .primary {
  flex: 1;
}

.answer {
  margin-top: 14px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface-2);
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.result-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
</style>
```

说明：

- `callTool(tool, action, payload)` 是唯一的前端调用方式，返回值已经是 `data` 部分。
- 样式尽量复用 `base.css` 里的 `.panel`、`.field`、`.btn`、`.input`、`.mono`，主题切换会自动生效。
- 只有多个工具都会用、且不含业务语义的组件才放进 `web/src/ui/`；专属组件放 `web/src/tools/calc/`。

## 7. 前端：翻译

`web/src/tools/calc/i18n/zh_CN.json`：

```json
{
  "calc.name": "数学计算器",
  "calc.description": "两个数加、减、乘、除",
  "calc.panel.input": "输入",
  "calc.panel.history": "历史记录",
  "calc.field.a": "第一个数",
  "calc.field.b": "第二个数",
  "calc.field.op": "运算符",
  "calc.field.decimals": "保留小数位",
  "calc.settings.basic": "基础",
  "calc.op.add": "加",
  "calc.op.sub": "减",
  "calc.op.mul": "乘",
  "calc.op.div": "除",
  "calc.action.evaluate": "计算",
  "calc.col.expression": "算式",
  "calc.col.result": "结果"
}
```

`zh_TW.json`、`en.json` 复制同样的键并翻译即可。工具的词条会被 `import.meta.glob('../tools/*/i18n/*.json')` 自动合并，缺键时回退到简体中文。

## 8. 测试

`tests/test_bridge.py` 里加一条契约测试：

```python
def test_calc_evaluate(api):
    result = api.tool_call("calc", "evaluate", {"a": 2, "b": 3, "op": "add"})
    assert result["ok"] is True
    assert result["data"]["result"] == 5

    bad = api.tool_call("calc", "evaluate", {"a": 1, "b": 0, "op": "div"})
    assert bad["ok"] is False
    assert bad["error"]["code"] == "DIVIDE_BY_ZERO"
```

再把它加进 `tests/test_boundaries.py` 的工具列表，确认新工具不 import 其他工具：

```python
TOOL_IDS = ("pearl", "border", "material", "calc")
```

跑：

```powershell
.venv\Scripts\python.exe -m pytest tests
```

## 9. 检查清单

- [ ] 左轨出现新工具，标题、描述、按钮、表格都有三语词条
- [ ] 设置抽屉能渲染 `schema.py` 里的字段，保存后重启仍生效
- [ ] `tool_call` 传非法参数时返回错误信封，而不是抛异常
- [ ] `tools/calc` 没有 import 其他工具
- [ ] `core/`（如果有）不读写磁盘、不 import `store` / `platform`
- [ ] 新增的图标名已在 `App.vue` 的 `ICONS` 里存在
- [ ] `pytest` 全绿，前端 `npm run build` 通过
- [ ] 需要的话补一张 README 截图，并在 README 的工具章节里加一段

## 10. 约定与边界

- **工具之间零 import**：`pearl`、`border`、`material` 各有一套常量与算法，新工具也一样；共用代码只能放 `platform`。
- **常量分母**：物理参数放 `constants.py`，可被用户调整的放 `schema.py` + `defaults.py`，不要混用。
- **纯计算**：算法放 `core/`，只依赖标准库与自己的常量；动作层负责取参数、读设置、组装返回值。
- **通用组件不认业务**：只有多个工具都会用的组件才放 `web/src/ui/`，专属组件放工具自己的目录。
- **错误可预期**：业务错误用 `AppError`，带稳定错误码和给用户看的文案；不要抛带 traceback 的异常到前端。

## 11. 常见扩展点

| 想做的事 | 改哪里 |
|---|---|
| 加一个新动作（如「取余」） | `actions.py` 加函数 + `manifest.py` 的 `actions` + `HANDLERS` + 前端按钮 |
| 加一个设置项 | 只改 `schema.py`（和 `defaults.py`），设置抽屉自动生成 |
| 结果表加一列 | `core/` 输出新字段 + `manifest.py` 的 `columns` |
| 加一种语言 | 复制 `web/src/i18n/zh_CN.json` 为 `<lang>.json`，工具词条同理 |
| 读取/保存文件 | 用平台层的 `file_open_text` / `file_save_text`，不要自己弹对话框 |
| 换工具图标 | `manifest.py` 的 `icon` + 在 `App.vue` 的 `ICONS` 里加对应 path |
