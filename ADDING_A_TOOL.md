# 新增工具说明

这份文档以「材料换算器」为例，完整走一遍从后端到前端的接入流程。

目标：输入物品总数，换算成「潜影盒 / 组 / 个」，并显示成结果表格。

> 约定：工具 id 在目录名、manifest、视图目录、i18n 文件名里保持一致，这里统一用 `material`。

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
│     └─ _template/            新工具脚手架
├─ web/
│  ├─ src/
│  │  ├─ App.vue               外壳：左轨、命令栏、设置入口、关于
│  │  ├─ platform/             bridge / i18n / settings / theme / toast
│  │  ├─ shell/                SettingsDrawer、AboutDialog
│  │  ├─ ui/                   通用组件：DataTable、CompassRose、ToastHost
│  │  ├─ tools/<id>/View.vue   工具页面（外壳按 id 懒加载）
│  │  └─ i18n/                 外壳文案（工具文案在各自目录）
│  └─ dist/                    构建产物，已提交；运行不依赖 Node
├─ resources/                  图标、文档、version.json（打包进 exe）
├─ tests/                      golden 快照、API 契约、架构边界
├─ README_img/                 README 截图
└─ packaging/                  PyInstaller spec
```

一次调用的链路：

```text
View.vue
  └─ callTool('material', 'convert', payload)
       └─ window.pywebview.api.tool_call(tool, action, payload)
            └─ api.Api.tool_call → Registry.call
                 └─ tools/material/actions.py：convert_action(payload, ctx)
                      └─ ctx.settings('material') 读取该工具的设置
                 ← {ok: true, data}
```

三条分层规则：

- `tools/<id>` 只依赖 `platform` 与自己的目录，**不 import 其他工具**
- `platform` 不含任何物理常量或业务逻辑
- `actions.py` 只做参数校验与返回值组装；复杂算法放 `core/`，且 `core/` 不碰 IO

## 1. 复制脚手架

```powershell
Copy-Item src\lspkit\tools\_template src\lspkit\tools\material -Recurse
```

前端没有模板目录，手动新建 `web/src/tools/material/` 即可，结构如下：

```
src/lspkit/tools/material/
├─ __init__.py       导出 MANIFEST / HANDLERS / LEGACY
├─ manifest.py       工具声明
├─ schema.py         设置字段
├─ defaults.py       出厂默认值
├─ actions.py        对外动作
├─ legacy.py         旧配置迁移（没有历史格式就原样返回）
└─ constants.py      工具专用常量（可选）

web/src/tools/material/
├─ View.vue          工具页面
└─ i18n/
   ├─ zh_CN.json
   ├─ zh_TW.json
   └─ en.json
```

## 2. 后端：默认值与设置字段

`defaults.py`：

```python
DEFAULT_SETTINGS = {
    "stackSize": 64,      # 每格堆叠上限
    "shulkerSlots": 27,   # 每个潜影盒的格数
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
            "material.settings.basic",
            [
                Field("stackSize", "material.field.stackSize", "int", D["stackSize"], 1, 64, 1, unit="个/格"),
                Field("shulkerSlots", "material.field.shulkerSlots", "int", D["shulkerSlots"], 1, 27, 1, unit="格/盒"),
            ],
        ),
    ],
)
```

字段定义同时负责三件事：校验、默认值、设置抽屉里的表单。改这里不用写任何 UI 代码。

## 3. 后端：动作

`actions.py`：

```python
from lspkit.platform import params


def convert_action(payload: dict, ctx) -> dict:
    settings = ctx.settings("material")
    count = params.integer(payload, "count", minimum=0, maximum=1_000_000_000, label="物品总数")

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

返回值必须是 JSON 原生类型（`int/float/str/bool/list/dict`），不要返回 numpy 标量。

## 4. 后端：manifest 与注册

`manifest.py`：

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
from . import border, material, pearl

registry.register(material.MANIFEST, material.HANDLERS, material.LEGACY)
```

## 5. 前端：视图

`web/src/tools/material/View.vue`：

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

左轨按钮、页面标题、设置抽屉都由后端 manifest 自动生成，前端只要提供 `View.vue`。

## 6. 前端：翻译

`web/src/tools/material/i18n/zh_CN.json`：

```json
{
  "material.name": "材料换算器",
  "material.description": "物品数量换算成潜影盒 / 组 / 个",
  "material.panel.input": "输入物品数量",
  "material.panel.result": "换算结果",
  "material.field.count": "物品总数",
  "material.action.convert": "换算",
  "material.settings.basic": "基础",
  "material.field.stackSize": "每格堆叠上限",
  "material.field.shulkerSlots": "潜影盒格数",
  "material.col.shulkers": "潜影盒",
  "material.col.stacks": "组",
  "material.col.items": "个"
}
```

`zh_TW.json`、`en.json` 复制同样的键并翻译即可。缺键时会回退到简体中文。

## 7. 测试

`tests/tools/material/test_actions.py`（也可以直接放进 `tests/test_bridge.py`）：

```python
def test_material_convert(api):
    result = api.tool_call("material", "convert", {"count": 1793})
    assert result["ok"] is True
    assert result["data"]["shulkers"] == 1
    assert result["data"]["stacks"] == 1
    assert result["data"]["items"] == 1
```

跑：

```powershell
.venv\Scripts\python.exe -m pytest tests
```

---

## 检查清单

- [ ] 左轨出现新工具，标题与描述有翻译
- [ ] 设置抽屉能渲染 `schema.py` 里的字段，保存后重启仍生效
- [ ] `tool_call` 传非法参数时返回错误信封，而不是抛异常
- [ ] `tools/material` 没有 import 其他工具
- [ ] `core/`（如果有）不读写磁盘、不 import `store`
- [ ] `pytest` 全绿，前端 `npm run build` 通过

## 约定与边界

- **工具之间零 import**：`tools/pearl` 与 `tools/border` 各有一套常量，不互相引用；新工具也一样。
- **常量分母**：物理参数放 `constants.py`，可被用户调整的放 `schema.py` + `defaults.py`，不要混用。
- **纯计算**：需要复杂算法时放 `core/`，只依赖 numpy 与自己的常量；动作层负责取参数、读设置、组装返回值。
- **通用组件不认业务**：只有多个工具都会用的组件才放 `web/src/ui/`，专属组件放工具自己的目录。
