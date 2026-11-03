# Adding a tool

This guide walks through adding a **Material Converter** end to end, from backend to frontend.

Goal: enter an item count and convert it into shulker boxes / stacks / items, shown as a result table.

> Convention: the tool id is shared by the folder name, the manifest, the view folder and the i18n filenames. We use `material` throughout.

---

## 0. Project layout (for developers)

The app is a Python shell plus a Vue frontend, connected by one JSON-RPC channel. Learn the layers before adding a tool.

```text
LSP_PlayerKit/
├─ main.py                     entry point: puts src/ on sys.path, then starts
├─ src/lspkit/
│  ├─ app.py                   window, local static server, window state
│  ├─ api.py                   the only JS ↔ Python facade, {ok, data|error} envelope
│  ├─ paths.py                 resource / data path resolution (dev, frozen, portable)
│  ├─ platform/                business-agnostic infrastructure
│  │  ├─ locator.py            data folder resolution and read-only fallback
│  │  ├─ store.py              atomic JSON writes, backup rotation
│  │  ├─ schema.py             settings field descriptors (validation + form + defaults)
│  │  ├─ registry.py           tool registry, action dispatch, Context
│  │  ├─ storage.py            data folder switching, bundle import/export
│  │  └─ params.py             request parameter validation
│  └─ tools/
│     ├─ pearl/                pearl cannon tool (full example)
│     ├─ border/               border cannon tool (full example)
│     └─ _template/            scaffold for new tools
├─ web/
│  ├─ src/
│  │  ├─ App.vue               shell: rail, command bar, settings, about
│  │  ├─ platform/             bridge / i18n / settings / theme / toast
│  │  ├─ shell/                SettingsDrawer, AboutDialog
│  │  ├─ ui/                   generic components: DataTable, CompassRose, ToastHost
│  │  ├─ tools/<id>/View.vue   tool page (lazy-loaded by id)
│  │  └─ i18n/                 shell strings (tool strings live in tool folders)
│  └─ dist/                    build output, committed; running does not need Node
├─ resources/                  icons, docs, version.json (bundled into the exe)
├─ tests/                      golden snapshots, API contracts, architecture boundaries
├─ README_img/                 README screenshots
└─ packaging/                  PyInstaller spec
```

One call, end to end:

```text
View.vue
  └─ callTool('material', 'convert', payload)
       └─ window.pywebview.api.tool_call(tool, action, payload)
            └─ api.Api.tool_call → Registry.call
                 └─ tools/material/actions.py: convert_action(payload, ctx)
                      └─ ctx.settings('material') reads this tool's settings
                 ← {ok: true, data}
```

Three rules:

- `tools/<id>` depends only on `platform` and its own folder — **never import another tool**
- `platform` contains no physics constants and no business logic
- `actions.py` validates and shapes results; algorithms belong in `core/`, which never touches IO

## 1. Copy the scaffold

```powershell
Copy-Item src\lspkit\tools\_template src\lspkit\tools\material -Recurse
```

Create the frontend folders by hand:

```
src/lspkit/tools/material/
├─ __init__.py       exports MANIFEST / HANDLERS / LEGACY
├─ manifest.py       tool declaration
├─ schema.py         settings fields
├─ defaults.py       factory defaults
├─ actions.py        public actions
├─ legacy.py         legacy config migration (pass-through when there is none)
└─ constants.py      tool-specific constants (optional)

web/src/tools/material/
├─ View.vue          tool page
└─ i18n/
   ├─ zh_CN.json
   ├─ zh_TW.json
   └─ en.json
```

## 2. Backend — defaults and schema

`defaults.py`:

```python
DEFAULT_SETTINGS = {
    "stackSize": 64,      # items per stack
    "shulkerSlots": 27,   # slots per shulker box
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
            "material.settings.basic",
            [
                Field("stackSize", "material.field.stackSize", "int", D["stackSize"], 1, 64, 1, unit="items/slot"),
                Field("shulkerSlots", "material.field.shulkerSlots", "int", D["shulkerSlots"], 1, 27, 1, unit="slots/box"),
            ],
        ),
    ],
)
```

The field definition drives validation, defaults and the settings drawer form. No UI code needed when it changes.

## 3. Backend — actions

`actions.py`:

```python
from lspkit.platform import params


def convert_action(payload: dict, ctx) -> dict:
    settings = ctx.settings("material")
    count = params.integer(payload, "count", minimum=0, maximum=1_000_000_000, label="Item count")

    per_shulker = settings["stackSize"] * settings["shulkerSlots"]
    shulkers, rest = divmod(count, per_shulker)
    stacks, items = divmod(rest, settings["stackSize"])

    return {
        "count": count,
        "shulkers": shulkers,
        "stacks": stacks,
        "items": items,
        "perShulker": per_shulker,
    }
```

Return JSON-native values (`int/float/str/bool/list/dict`); never numpy scalars.

## 4. Backend — manifest and registration

`manifest.py`:

```python
from lspkit.platform.registry import ToolManifest

from .actions import convert_action
from .legacy import convert
from .schema import SCHEMA

MANIFEST = ToolManifest(
    id="material",
    name_key="material.name",
    description_key="material.description",
    icon="box",
    order=30,
    version="1.0.0",
    schema=SCHEMA,
    actions=[{"id": "convert", "labelKey": "material.action.convert"}],
    columns=[
        {"key": "shulkers", "nameKey": "material.col.shulkers", "type": "int"},
        {"key": "stacks", "nameKey": "material.col.stacks", "type": "int"},
        {"key": "items", "nameKey": "material.col.items", "type": "int"},
    ],
)

HANDLERS = {"convert": convert_action}

LEGACY = convert
```

`__init__.py`:

```python
from .manifest import HANDLERS, LEGACY, MANIFEST

__all__ = ["MANIFEST", "HANDLERS", "LEGACY"]
```

`legacy.py` (pass-through when there is no legacy format):

```python
def convert(raw: dict) -> dict:
    return raw
```

Register the tool with one line in `src/lspkit/tools/__init__.py`:

```python
from . import border, material, pearl

registry.register(material.MANIFEST, material.HANDLERS, material.LEGACY)
```

## 5. Frontend — view

`web/src/tools/material/View.vue`:

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

const count = ref<number | string>(1793)
const rows = ref<Record<string, any>[]>([])
const busy = ref(false)

async function convert() {
  busy.value = true
  try {
    const result = await callTool<Record<string, any>>(
      props.tool.id,
      'convert',
      { count: Number(count.value) },
    )
    rows.value = [result]
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
      <div class="panel-head">{{ t('material.panel.input') }}</div>
      <div class="panel-body">
        <div class="field">
          <label class="field-label">{{ t('material.field.count') }}</label>
          <input v-model.number="count" class="input mono" type="number" min="0" />
        </div>
        <div class="actions">
          <button class="btn primary" :disabled="busy" @click="convert">
            {{ t('material.action.convert') }}
          </button>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head">{{ t('material.panel.result') }}</div>
      <div class="result-body">
        <DataTable :columns="tool.columns" :rows="rows" :selected="null" />
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
}

.result-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
</style>
```

The rail button, page title and settings drawer are generated from the backend manifest; the frontend only supplies `View.vue`.

## 6. Frontend — translations

`web/src/tools/material/i18n/en.json`:

```json
{
  "material.name": "Material Converter",
  "material.description": "Convert item counts into shulker boxes / stacks / items",
  "material.panel.input": "Input",
  "material.panel.result": "Result",
  "material.field.count": "Total items",
  "material.action.convert": "Convert",
  "material.settings.basic": "Basics",
  "material.field.stackSize": "Items per stack",
  "material.field.shulkerSlots": "Slots per shulker",
  "material.col.shulkers": "Shulkers",
  "material.col.stacks": "Stacks",
  "material.col.items": "Items"
}
```

Copy the same keys into `zh_CN.json` and `zh_TW.json`. Missing keys fall back to Simplified Chinese.

## 7. Test

`tests/tools/material/test_actions.py` (or extend `tests/test_bridge.py`):

```python
def test_material_convert(api):
    result = api.tool_call("material", "convert", {"count": 1793})
    assert result["ok"] is True
    assert result["data"]["shulkers"] == 1
    assert result["data"]["stacks"] == 1
    assert result["data"]["items"] == 1
```

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests
```

---

## Checklist

- [ ] The new tool shows up in the rail, with translated name and description
- [ ] The settings drawer renders the fields from `schema.py` and keeps values across restarts
- [ ] Invalid `tool_call` arguments return an error envelope instead of raising
- [ ] `tools/material` does not import other tools
- [ ] `core/` (if any) never touches disk and never imports `store`
- [ ] `pytest` is green and `npm run build` succeeds

## Boundaries

- **No cross-tool imports**: `tools/pearl` and `tools/border` each own their constants; a new tool follows the same rule.
- **Where values live**: physics constants go in `constants.py`; user-tunable values go in `schema.py` + `defaults.py`.
- **Pure calculation**: put algorithms in `core/`, depending only on numpy and your own constants. Actions read parameters/settings and shape the response.
- **Generic components stay generic**: only components shared by multiple tools belong in `web/src/ui/`; tool-specific ones live under the tool folder.
