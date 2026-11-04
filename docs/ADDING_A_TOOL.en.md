# Adding a tool

This guide walks through the whole flow — backend to frontend — using a **simple math calculator**: enter two numbers, pick an operator, get a result and a small history list.

> Convention: the tool id is identical in the folder name, manifest, view folder and i18n file names. This guide uses `calc`.
>
> `calc` is only an example and is not shipped in the app; use your own id when following along.

---

## 0. Project structure (for developers)

The app is a "Python shell + Vue frontend" pair talking over a small JSON-RPC bridge. Learn the layers first, then add a tool.

```text
LSP_PlayerKit/
├─ main.py                     entry: puts src/ on sys.path, then starts the app
├─ src/lspkit/
│  ├─ app.py                   window, local static server, window state
│  ├─ api.py                   the only JS ↔ Python facade, {ok, data|error} envelope
│  ├─ paths.py                 resource / data folder resolution (dev, frozen, portable)
│  ├─ platform/                business-agnostic layer
│  │  ├─ locator.py            data folder resolution and read-only fallback
│  │  ├─ store.py              atomic JSON writes, backup rotation
│  │  ├─ schema.py             settings field descriptors (validation + form + defaults)
│  │  ├─ registry.py           tool registry, action dispatch, Context
│  │  ├─ storage.py            data folder switching, bundle import/export
│  │  └─ params.py             request parameter validation
│  └─ tools/
│     ├─ pearl/                pearl cannon (full example)
│     ├─ border/               border cannon (full example)
│     ├─ material/             material converter (pure core/ plus dialogs)
│     └─ _template/            new-tool scaffold
├─ web/
│  ├─ src/
│  │  ├─ App.vue               shell: rail, command bar, settings, about
│  │  ├─ platform/             bridge / i18n / settings / theme / toast
│  │  ├─ shell/                SettingsDrawer, AboutDialog
│  │  ├─ ui/                   shared components: DataTable, CompassRose, ToastHost
│  │  ├─ tools/<id>/View.vue   tool page (lazily loaded by id)
│  │  └─ i18n/                 shell strings (tool strings live in tools/<id>/i18n/)
│  └─ dist/                    build output, committed; running needs no Node
├─ resources/                  icons, docs, version.json (bundled into the exe)
├─ tests/                      golden snapshots, API contract, architecture boundaries
├─ README_img/                 README screenshots
└─ packaging/                  PyInstaller spec
```

One call looks like this:

```text
View.vue
  └─ callTool('calc', 'evaluate', { a: 2, b: 3, op: 'add' })
       └─ window.pywebview.api.tool_call(tool, action, payload)
            └─ api.Api.tool_call → Registry.call
                 └─ tools/calc/actions.py: evaluate_action(payload, ctx)
                      ├─ ctx.settings('calc') reads this tool's settings
                      └─ core/calc.py pure calculation
                 ← { ok: true, data: { expression, result } }
```

Three layering rules:

- `tools/<id>` depends only on `platform` and its own folder — **never imports another tool**
- `platform` contains no business logic or magic numbers
- `actions.py` only validates input and assembles output; algorithms live in `core/`, which does no IO (no files, no settings)

## 1. Copy the scaffold

```powershell
Copy-Item src\lspkit\tools\_template src\lspkit\tools\calc -Recurse
```

Delete `__pycache__` after copying, then fill in the four placeholder files:

```text
src/lspkit/tools/calc/
├─ __init__.py       exports MANIFEST / HANDLERS / LEGACY
├─ manifest.py       tool declaration (id, icon, actions, columns)
├─ schema.py         settings fields
├─ defaults.py       factory defaults
├─ actions.py        public actions
├─ legacy.py         legacy settings migration (identity if none)
├─ constants.py      tool-specific constants (optional)
└─ core/             pure calculation (optional but recommended)
   ├─ __init__.py
   └─ calc.py
```

Create `web/src/tools/calc/` by hand with at least `View.vue` and three i18n files.

## 2. Backend: defaults and settings

One "decimal places" setting is enough for the demo.

`defaults.py`:

```python
DEFAULT_SETTINGS = {
    "decimals": 2,
}
```

`schema.py`:

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
                    0,        # minimum
                    8,        # maximum
                    1,        # step
                    unit="位",
                ),
            ],
        ),
    ],
)
```

`Field` takes `key, label, type, default, min, max, step, digits, unit, options, hint`; `label` is an i18n key, not literal text. Changing this file regenerates the settings drawer form — no UI code needed.

## 3. Backend: pure calculation

`core/calc.py` reads no settings and raises no `AppError`; it only does math:

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

Do not `import lspkit.platform`, `os`, `pathlib` or `json` in `core/` — `tests/test_boundaries.py` scans for this and fails the build.

## 4. Backend: actions

`actions.py` validates, reads settings, calls `core` and assembles the result:

```python
from lspkit.errors import AppError
from lspkit.platform import params

from .core.calc import OPERATORS, evaluate


def evaluate_action(payload: dict, ctx) -> dict:
    settings = ctx.settings("calc")

    a = params.number(payload, "a", label="first number")
    b = params.number(payload, "b", label="second number")
    op = params.choice(payload, "op", tuple(OPERATORS), default="add")

    try:
        value = evaluate(a, b, op)
    except ZeroDivisionError:
        raise AppError("DIVIDE_BY_ZERO", "The divisor cannot be 0") from None

    digits = int(settings["decimals"])
    return {
        "expression": f"{a:g} {OPERATORS[op]} {b:g}",
        "result": round(value, digits),
        "op": op,
    }
```

Notes:

- `params.*` raises an `AppError` with a stable code for missing or malformed input; the frontend receives `{ok: false, error}` instead of a traceback.
- Use `AppError(code, user_message)` for expected failures; keep codes uppercase and stable.
- Return JSON-native types (`int / float / str / bool / list / dict`), never numpy scalars.

## 5. Backend: manifest and registration

`manifest.py`:

```python
from lspkit.platform.registry import ToolManifest

from .actions import evaluate_action
from .legacy import convert
from .schema import SCHEMA

MANIFEST = ToolManifest(
    id="calc",
    name_key="calc.name",
    description_key="calc.description",
    icon="spark",          # see ICONS in App.vue
    order=40,              # rail order: pearl 10 / border 20 / material 30
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

`__init__.py`:

```python
from .manifest import HANDLERS, LEGACY, MANIFEST

__all__ = ["MANIFEST", "HANDLERS", "LEGACY"]
```

`legacy.py` (identity when there is no legacy format):

```python
def convert(raw: dict) -> dict:
    return raw
```

Finally register one line in `src/lspkit/tools/__init__.py`:

```python
from . import border, calc, material, pearl

registry.register(calc.MANIFEST, calc.HANDLERS, calc.LEGACY)
```

The rail button, page title and settings drawer are all generated from the manifest; the frontend only provides `View.vue`.

## 6. Frontend: the view

`web/src/tools/calc/View.vue`:

```vue
<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { callTool } from '../../platform/bridge'
import { t } from '../../platform/i18n'
import { loadSettings } from '../../platform/settings'
import { notifyError } from '../../platform/toast'
import type { ToolDef } from '../../platform/types'
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

Notes:

- `callTool(tool, action, payload)` returns the `data` part directly.
- Reuse `.panel`, `.field`, `.btn`, `.input`, `.mono` from `base.css` so theme switching works for free.
- Only components shared by several tools and free of business meaning belong in `web/src/ui/`; tool-specific ones stay under `web/src/tools/calc/`.

## 7. Frontend: translations

`web/src/tools/calc/i18n/zh_CN.json`:

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

Copy the same keys into `zh_TW.json` and `en.json` and translate. Tool dictionaries are merged automatically by `import.meta.glob('../tools/*/i18n/*.json')`; missing keys fall back to Simplified Chinese.

## 8. Tests

Add a contract test to `tests/test_bridge.py`:

```python
def test_calc_evaluate(api):
    result = api.tool_call("calc", "evaluate", {"a": 2, "b": 3, "op": "add"})
    assert result["ok"] is True
    assert result["data"]["result"] == 5

    bad = api.tool_call("calc", "evaluate", {"a": 1, "b": 0, "op": "div"})
    assert bad["ok"] is False
    assert bad["error"]["code"] == "DIVIDE_BY_ZERO"
```

Also add it to the tool list in `tests/test_boundaries.py`:

```python
TOOL_IDS = ("pearl", "border", "material", "calc")
```

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests
```

## 9. Checklist

- [ ] The new tool appears in the rail, with translated title, description, buttons and columns
- [ ] The settings drawer renders `schema.py`, and values survive a restart
- [ ] Invalid `tool_call` input returns an error envelope instead of raising
- [ ] `tools/calc` imports no other tool
- [ ] `core/` (if any) does no disk IO and imports neither `store` nor `platform`
- [ ] The icon name exists in `App.vue`'s `ICONS`
- [ ] `pytest` is green and `npm run build` passes
- [ ] Optionally add a screenshot and a README section for the new tool

## 10. Conventions and boundaries

- **No imports between tools**: `pearl`, `border` and `material` each own their constants and algorithms; a new tool does the same. Shared code goes into `platform`.
- **Constants**: physics/algorithm constants go in `constants.py`; user-tunable values go in `schema.py` + `defaults.py`. Do not mix them.
- **Pure calculation**: algorithms live in `core/`, depending only on the standard library and their own constants; actions read parameters, settings and assemble the result.
- **Shared components stay business-agnostic**: only put a component in `web/src/ui/` when several tools use it.
- **Expected errors**: use `AppError` with a stable code and a user-facing message; never leak a traceback to the frontend.

## 11. Common extension points

| Goal | What to change |
|---|---|
| Add an action (e.g. modulo) | New function in `actions.py` + `actions` and `HANDLERS` in `manifest.py` + a button |
| Add a setting | Only `schema.py` (and `defaults.py`); the drawer is generated |
| Add a result column | Emit the field from `core/` + add it to `columns` in `manifest.py` |
| Add a language | Copy `web/src/i18n/zh_CN.json` to `<lang>.json`; same for tool strings |
| Read or save a file | Use the platform helpers `file_open_text` / `file_save_text` instead of your own dialogs |
| Change the tool icon | `icon` in `manifest.py` plus a matching path in `App.vue`'s `ICONS` |
