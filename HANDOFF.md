# 交接说明（新对话接手用）

> 记录于 2026-11-04，更新于 2026-11-06。本文用于在新对话中快速恢复上下文，不需要时可删除。
> 当前版本 **v1.2.0**（已提交）；`v1.1.5` 的提交是 `904fee1`，1.2.0 之后的 HEAD 以 `git log -1` 为准。

---

## 0. 一句话

`D:\GitsProject\LSP_PlayerKit` 是一个 **Python 3.9.7 + pywebview(WebView2) + Vue 3** 的桌面工具箱，把原先两个 Tkinter 项目（`LSP_PearlCannonConfig`、`LSP_BorderCannonConfig`）合并成一个应用，并做成了「一个平台 + 若干自包含工具」的插件化结构。

两个旧项目保持原样，只作为**数值黄金快照的来源**和**旧配置导入格式的来源**。

---

## 1. 现状快照

| 项 | 值 |
|---|---|
| 路径 | `D:\GitsProject\LSP_PlayerKit` |
| 分支 | `master`（跟踪 `origin/master`） |
| HEAD | 1.2.0 提交（`git log -1`）；上一版 `v1.1.5` 为 `904fee1` |
| 标签 | `v1.0.0`、`v1.1.0`、`v1.1.1`（0732719）、`v1.1.2`（7a1cf29）、`v1.1.3`（4ca53d3）、`v1.1.4`（4dd5ecd）、`v1.1.5`（904fee1） |
| 版本号 | `resources/version.json` = 1.2.0（同步在 `lspkit/__init__.py`、`pyproject.toml`、`web/package.json`、`web/package-lock.json`、三个工具 manifest） |
| 测试 | `.venv\Scripts\python.exe -m pytest tests` → **123 passed, 3 skipped**（3 条是需真实桌面的 `win32gui` 用例） |
| 打包产物 | `dist/LSP_PlayerKit/`（onedir，仍是 1.1.5 的包；1.2.0 待重新打包）；同目录含三个附赠工具 exe |
| 解释器 | 必须用仓库内 `.venv`（Python 3.9.7）；系统 Python 3.12 里没有 webview |
| 未提交 | 无（1.2.0 已提交）；仅本地样例清单、测试投影与 `docs/build_readme_pdf.py` 未入库 |
| 未跟踪 | `material_list_en.csv`、`material_list_zh_cn.csv`、测试投影、`docs/build_readme_pdf.py`（本地脚本，不入库） |
| 构建脚本 | `packaging/` 下的 spec **只在本地，不入库**（`.gitignore` 忽略整个目录） |

---

## 2. 仓库结构

```text
LSP_PlayerKit/
├─ main.py                     启动入口（插 sys.path 后调 lspkit.app.run）
├─ packaging/                   PyInstaller spec（本地目录，不入库）：主应用 + 三个附赠工具
├─ resources/                  version.json、Config.pdf、README.pdf / README.en.pdf、图标（只读）
├─ src/lspkit/
│  ├─ app.py                   窗口、本地静态服务、单实例锁、窗口状态
│  ├─ api.py                   js_api 门面：工具调用、设置、文件读写、数据目录
│  ├─ paths.py / errors.py
│  ├─ platform/                locator / store / schema / registry / storage / params
│  │  └─ autoinput.py          向目标窗口注入文本（Transport 可替换，见 §3.4）
│  └─ tools/
│     ├─ pearl/                珍珠炮（constants/defaults/schema/manifest/actions/legacy + core/）
│     ├─ border/               边境炮（同结构，常量与算法独立）
│     ├─ material/             材料换算（parse / convert / packing + actions，支持多清单）
│     └─ puppet/               假人搬货（core: naming/plan/stations；actions: 站点/运单/执行）
├─ src/tool_bundles/           控制台小工具（独立打包，不 import lspkit）
│  ├─ configgenerator.py       珍珠炮技术参数生成器（按旧 exe 实测复现）
│  ├─ maincannon_configmaker.py
│  ├─ bordercannon_configmaker.py
│  └─ station_configmaker.py   假人搬货站点生成器（生成可导入的 JSON）
├─ web/src/
│  ├─ App.vue                  外壳：工具轨、命令栏、设置、关于
│  ├─ platform/                bridge / i18n / settings / theme / toast / tools
│  ├─ shell/                   SettingsDrawer、AboutDialog
│  ├─ ui/                      DataTable、CompassRose、ToastHost
│  ├─ tools/
│  │  ├─ pearl/View.vue
│  │  ├─ border/View.vue
│  │  ├─ material/             View.vue、PackingDialog.vue、PackEntry.vue、i18n/
│  │  └─ puppet/               View.vue、StationDialog.vue、ImportDialog.vue、types.ts、i18n/
│  └─ dist/                    已提交，运行不依赖 Node
├─ tests/                      123 项：golden、契约、边界、存储、多清单、假人搬货与冒烟
│  └─ harness/mc_chat_stub.py  真实注入测试用的迷你聊天栏（需交互桌面）
├─ README.md / ADDING_A_TOOL.md           中文
├─ docs/README.en.md / docs/ADDING_A_TOOL.en.md   英文
├─ README_img/1..8.png         中文截图（浅色 1600×1025，v1.1.5）
└─ README_img/en/1..8.png      英文截图（同上）
```

一次调用：`View.vue → callTool → pywebview.api → Api.tool_call → Registry.call → tools/<id>/actions.py → core/*.py`，设置走 `ctx.settings` / `ctx.save_settings`，工具自有变长数据走 `ctx.doc_load` / `ctx.doc_save`。

三条硬规则（`tests/test_boundaries.py` 强制）：工具之间零 import、`platform/` 不含业务、`core/` 纯函数不碰 IO。

---

## 3. 四个工具

### 3.1 珍珠炮（`tools/pearl`）
- 动作：`calculate` / `decode` / `trace`。
- 设置 schema v3：`maxTnt`、`tntPerUnit`、`originX/Z`、`targetX/Z`、`fireMode`、`ejectionAvailable`、`flat.*` / `eject.*` 四组动量。
- 出厂默认：炮口 `-31.9375 / -8.0625`、`maxTnt 3640`、目标 `0 / 0`。
- 算法严格复刻旧版，golden 快照锁死；结果 5 列，默认飞行时间升序，点表头排序。

### 3.2 边境炮（`tools/border`）
- 动作：`calculate` / `decode`（含 `landing` 预计落点）。
- 设置：炮口 XYZ、目的地 XYZ、`flightTime`、`directionMode`（`origin` / `fixed`）。
- 修了旧版把炮口写死成 `(10000,10000)` 的 bug，可用 `fixed` 兼容旧结果。
- 长飞行时间可能无有效解（旧版同样），表格会提示。

### 3.3 材料换算器（`tools/material`）
**多清单输入（2026-11-05 新增）**
- 「导入材料列表」一次可多选清单或 **`.litematic` 投影**，继续点击可追加；`file_open_material_lists` 对文本返回 `name` / `text`（GBK / UTF-8 自动识别），对投影返回 `name` / `entries` / `meta`。
- 投影解析在 `core/litematic.py`（纯函数）：gzip + NBT，遍历 `Regions`，`bits = max(2, ceil(log2(palette)))`，自动识别 Litematica 紧凑打包与 1.16+ padded 打包，numpy 向量化统计；跳过空气后按**物品形式**折算（`core/block_items.py`，Wiki「物品形式」列 1018 条：883 同 ID、124 映射、11 无物品），水/岩浆只算 `level=0` 源头，气泡柱等无物品方块过滤；显示名查 `core/block_names.py`（三语名称表，Minecraft 26.3：zh_cn 1301 / zh_tw 1301 / en 1297 条）与 `ITEM_NAMES`；`parse_litematic(data, locale)` 与 `convert` / `pack` 的 `locale` 字段决定材料名语言，切换语言后前端会自动重算。
- 左栏为**清单列表**：每份一行，勾选框决定是否参与换算，行内显示该清单「种类 · 数量」，`✕` 移除；取消勾选立即重算，全部取消则清空结果；投影行悬停显示「区域数 · 方块数」。
- `core/parse.py:parse_sources()` 逐份解析后**按材料名合并数量**（同名相加），`convert` / `pack` 接受 `sources`（`text` 或 `entries`）并回传各清单摘要。
- 材料列表、结果、装填、导出都只使用**勾选**的清单；堆叠覆盖与忽略名单按材料名全局生效。
- 追加导入不清空堆叠与忽略设置，只清空材料勾选与导出文件名。

**解析**
- 优先按 CSV 表头取名称与数量，Litematica 的 `Item, Total, Missing, Available` 取 **Total** 列；无表头回退「名称 数量」。
- 名称原样保留（不改大小写、不加前缀），只有完全同名才合并。

**搜索与排序**
- 搜索框实时过滤，弹出最多 8 条建议（点击 / Enter 填入，Esc / ✕ 清空）；「全选」只作用于过滤结果。
- 列表点「数量」切换升降序（默认降序）；结果表支持「堆叠」筛选（全部 / 64 / 16 / 1）。

**堆叠与忽略**
- 默认堆叠数枚举 `64 / 16 / 1`；批量勾选后「应用到所选」，完成后自动清空勾选。
- 「忽略所选 / 恢复所选」，列表下方常驻「已忽略的材料」面板（逐条或全部恢复），忽略项不参与换算、装填、导出。

**结果**
- 列：材料名称 / 堆叠 / 数量 / 潜影盒 / 组 / 个；底部统计种类、总数量、整盒、折合盒数、默认单盒。
- `stackSize = 1` 时不出「组」，余量全部计入「个」。

**装填建议（动作 `pack`，`core/packing.py`）**
- 每种材料折算「占用格数」= 满组数 + (有零头 ? 1 : 0)，每盒 27 格；按格数从大到小逐盒填满，盒数 = `ceil(总格数 / 27)`。
- 弹窗两种视图：≤12 盒默认卡片，更多默认列表，可手动切换；支持「复制装填清单」。
- 同一种材料连续满装多个盒子时，`core/packing.py:_group_boxes()` 把它们合并成一张卡片（标题 `1–2 号盒`、标注「合装 N 盒」），混合或未装满的盒子仍单独显示；`plan()` 结果除 `boxes` 外还返回 `groups`，前端卡片/列表/复制清单都按 `groups` 渲染。
- 卡片列宽 300px（三列），名称最多两行，英文长名不再截断。
- 卡片高度随材料种类数变化，采用**拼图式排布**：容器为 `grid-auto-rows: 4px` 的细网格，`PackingDialog.vue` 渲染后按 `getBoundingClientRect().height` 计算每张卡的 `grid-row-end: span N`，窗口宽度变化时重算；短卡片下方不再留整行空档。

**导出**
- 文件名默认 `<清单名>_converted.csv`；勾选多份时用 `merged_converted.csv`；目录默认数据目录下 `output`。
- 导出跟随当前筛选与排序，UTF-8 BOM，Excel 直接打开。

**设置**：`stackSize`（枚举）、`shulkerSlots`（默认 27）、`exportDir`（类型 `path`，设置抽屉带「选择…」）。

### 3.4 假人搬货（`tools/puppet`，v1.2.0 新增）
- 动作：`stations_*`（增删改查 + 导入 / 导出）、`plan`、`history_*`、`run_start/status/stop`、`diagnose`、`validate_template`。
- 数据：站点与台账存在 `data/settings/puppet_stations.json` / `puppet_orders.json`（`Context.doc_load/doc_save`，走同一套原子写与备份，也会进配置包）。
- 纯计算（`core/`）：`plan.py` 负责「盒数 → ceil(盒数/36) 人 → 按 24 人切批 → spawn/kill 命令」，`stations.py` 负责站点校验、合并、去重，`naming.py` 负责名字模板与 3–16 字符校验。
- 命令：`/execute in minecraft:<dim> run player <name> spawn at <x> <y> <z>`、`/player <name> kill`；名字默认 `bot_{origin}_{dest}_{index}`。
- 导入：兼容旧 `stops.json` 与「名称 x y z 前缀」文本，前缀里的 `end_` / `ov_` / `nether_` 自动识别维度并剥离；也接受「名称 x y z 前缀 [分组] 维度」。站点有 `group`（分组 tag，不能含空格）；旧名字里的「工业区·地点」在 `core/stations.normalize()` 里自动拆成 group + 短名称。
- 导出：`stations_export` 返回 JSON（默认，可再次导入）或文本（`名称 x y z 前缀 分组 维度`，空分组写 `-`），前端用 `file_save_text(..., bom=false)` 落盘；JSON 与站点导入、`src/tool_bundles/station_configmaker.py` 生成的格式互通。
- 工具定位：只负责 spawn / kill；典型流程是「始发地 spawn → 货站装货 → kill → 操作改为生成于目的地再 spawn → 货站卸货」，README 5.2 的 600 盒例子按这个顺序写。
- 台账：每次执行写一条，含 `spawnStation`（id/名称/维度，来自 `plan.spawnStation` 或恢复记录的 meta）、`commands`（最多 200 条）与 `meta.names`；前端在「操作位置」列显示站点与维度，点击台账行把命令恢复到上方预览，可直接再次执行，「回到当前订单」切回当前生成结果。
- 工具栏：「复制全部」旁边是「清空命令」，清掉当前 `plan` 与恢复记录、让预览回到空状态；命令为空时相关按钮自动禁用。
- 执行（可选）：`platform/autoinput.py` 的 `CommandRunner` + `Win32Transport`；默认 `allowExecute=false`，开启后倒计时切到游戏窗口，粘贴注入，回车前用 `SendMessageTimeout(WM_NULL)` 回探，卡顿则整条重来；ESC 轮询中断；只认 `GLFW30` / `LWJGL` 类窗口，不会误认启动器。全部命令成功后补发一条英文聊天消息 `Operation completed successfully`（`constants.FINAL_MESSAGE`）。
- 前端：`web/src/tools/puppet/`，左栏订单 + 站点，右栏命令预览（生成/清除）与执行/台账；订单的始发/目的站是自绘选择器 `StationPicker.vue`（先点分组 tag 筛选，再选地名，地名不重复 tag）；`Ctrl+1..4` 切工具。
- 测试：`test_puppet_plan/stations/input/bridge` 为 L0/L1（假 Transport + 虚拟时钟，含随机卡顿 30 组）；`test_puppet_win32.py` 是 L2，默认 skip，需 `LSPKIT_GUI_TEST=1` 与 `tests/harness/mc_chat_stub.py` 的迷你聊天栏；`test_station_script.py` 覆盖站点生成脚本。

---

## 4. 平台层与数据

- 文件接口：`file_open_text`（单个）、`file_open_texts`（多选，返回 `files: [{name, text}]`）、`file_save_text(filename, content, directory, bom=True)`（`bom=False` 写无 BOM 的 UTF-8，导出 JSON 用）；`open_manual(locale)` 按语言打开 `resources/docs/README.pdf` 或 `README.en.pdf`；`_export_dir` 解析导出目录（自定义优先，否则 `<数据目录>/output`）并自动创建。
- 工具自有文档：`Context.doc_load(tool_id, name, default)` / `doc_save(tool_id, name, data)`，落到 `settings/<tool_id>_<name>.json`，复用原子写与备份。
- `platform/schema.py` 支持 `string` / `path` 类型；字段 `unit` 可写 i18n key（`unit.pcs` 等，前端带 `.` 时走 `t()`）。
- 数据目录：默认 `<exe>/data`；优先级 `--data-dir`/`LSPKIT_DATA_DIR` → `portable.json` → `%APPDATA%\LSP_PlayerKit\location.json` → 默认（不可写则回退 `%APPDATA%`）。
- `data/` 下：`settings/{app,pearl,border,material,puppet}.json`、`puppet_stations.json`、`puppet_orders.json`、`output/`、`backups/`（5 份）、`.lock`。
- 所有写入原子化；损坏回退最近备份。
- `api._clipboard_write` 在 64 位下需显式声明 `SetClipboardData` / `GlobalAlloc` 的 HANDLE 类型（已修，否则「复制」会 OverflowError）。

---

## 5. 界面约定

- 左轨：珍珠炮、边境炮、材料换算器、假人搬货、敬请期待、关于；顶栏语言 / 主题 / 设置齿轮；`Ctrl+1/2/3/4`、`Ctrl+,`。
- 左轨标签允许换行（英文名 `Material Converter` 等不再被截断）；中文仍单行。
- 深色「末影控制台」主题 + 浅色；表格统一居中，数字等宽。
- 罗盘：北 0° / 东 90° / 南 180° / 西 270°。
- TNT 拆解为算式色块：`20 + 10 + 2 + 1 = 33`，单值显示裸数字。
- 珍珠轨迹只有表格，按飞行时间高亮到达行。
- 窗口状态（宽高、最大化）记在 `app.json`。

---

## 6. 常用命令

```powershell
.\.venv\Scripts\python.exe main.py                 # 运行（前端已构建）
.\.venv\Scripts\python.exe main.py --dev --debug   # Vite + devtools
.\.venv\Scripts\python.exe -m pytest tests         # 123 passed, 3 skipped
$env:LSPKIT_GUI_TEST="1"; .\.venv\Scripts\python.exe -m pytest tests\test_puppet_win32.py -q -s   # 真实注入（会抢焦点几秒）
cd web; npm run build                               # 改前端后必须

# 打包（spec 只在本地 packaging/，不入库）
.\.venv\Scripts\python.exe -m PyInstaller packaging\LSP_PlayerKit.spec --noconfirm
.\.venv\Scripts\python.exe -m PyInstaller packaging\ConfigGenerator.spec --noconfirm
.\.venv\Scripts\python.exe -m PyInstaller packaging\MainCannonConfigMaker.spec --noconfirm
.\.venv\Scripts\python.exe -m PyInstaller packaging\BorderCannonConfigMaker.spec --noconfirm
# 三个工具 exe 产出在 dist/，按需复制进 dist/LSP_PlayerKit/
# station_configmaker.py 还没有本地 spec，需要时自行补一个单文件控制台 spec
```

---

## 7. 代码约定

- 文件头注释统一旧项目风格（`# ===== #` 框 + `@Author/@Time/@IDE/@Python/@Descript`），CJK 双宽对齐 39 列；区段注释 `# ------ xxx ------ #`。
- 前端改完必须 `npm run build`；`web/dist` 已提交（应用直接服务该目录）。
- `packaging/` 是本地构建脚本，**不入库**；`src/tool_bundles/` 入库，与 `src/lspkit/` 平级、互不 import。
- 新增工具流程见 `ADDING_A_TOOL.md`（以数学计算器 `calc` 为例）。
- 工具之间零 import；`core/` 不碰 IO；通用组件才放 `web/src/ui/`。
- 平台层不放业务，但允许放「向窗口输入」「文档读写」这类通用能力（`autoinput.py`）。

---

## 8. 文档体系

- `README.md` / `docs/README.en.md`：目录 + 下载（百度网盘，提取码 1234）+ 四个工具的使用与设置 + 数据存储 + 限制 + **随应用附赠的小工具**。
- `ADDING_A_TOOL.md` / `docs/ADDING_A_TOOL.en.md`：以 `calc` 为例的完整接入指南。
- 截图：`README_img/1..8.png`（中文）、`README_img/en/1..8.png`（英文），浅色 1600×1025、v1.1.5；1.2.0 的新页面截图尚未补拍。
- 说明文件 PDF：`resources/docs/README.pdf`、`README.en.pdf`，由本地脚本 `docs/build_readme_pdf.py`（**不入库**；README.md → 打印用 HTML → Edge headless `--print-to-pdf`）生成；**改完 README 后必须重新生成**，否则「关于 → 打开说明文件」还是旧内容。`Config.pdf` 保留但已不再从界面打开。

### 随应用附赠的小工具（源码在仓库，构建脚本本机）
| 文件 | 源码 | 作用 |
|---|---|---|
| `ConfigGenerator.exe` | `src/tool_bundles/configgenerator.py` | 珍珠炮参数生成器：用 `/log projectiles full` 实测反推动量，输出可导入 JSON（写在 exe 同目录）。键名已修正为 `XZ_INIT_POSITION`，保存后打印完整路径，输入提示带样例 |
| `MainCannonConfigMaker.exe` | `src/tool_bundles/maincannon_configmaker.py` | 主炮配置信息记录器：输入目的地/坐标/方向/蓝红 TNT，打印格式化文本 |
| `BorderCannonConfigMaker.exe` | `src/tool_bundles/bordercannon_configmaker.py` | 边境炮配置信息记录器：输入目的地/坐标/方向/三个 TNT 小头大头，打印格式化文本 |
| `station_configmaker.py` | `src/tool_bundles/station_configmaker.py` | 假人搬货站点生成器：输入名称/维度/坐标/前缀/备注，输出 `{"version":1,"stations":[...]}`，可在「假人搬货 → 导入」直接读取（暂无 exe） |

三者均为单文件控制台程序，不参与本应用运行；`packaging/` 下各有一个 spec（不入库），产物名沿用旧 exe。

---

## 9. 已知限制

1. **边境炮默认 1200gt 可能无解**（负数 TNT，旧版同样），表格提示即可；400gt 正常。
2. **数值不能动**：`tests/fixtures/` 来自旧项目原始 venv，改 `core/` 前先确认是否要改数值。
3. 旧项目路径（生成快照用）：`LSP_PearlCannonConfig`（`venv\`）、`LSP_BorderCannonConfig`（`.venv\`）。
4. 材料换算的忽略/筛选只影响视图与导出，不改原始清单；多清单时同名材料按名称求和，清单摘要按文件名显示（重名文件会共用同一行统计）。
5. 装填建议的盒数最小，但同种材料可能拆到相邻盒。
6. 材料截图目前只导入 1 份清单演示（未额外准备第二份样例）。
7. 假人搬货只负责 spawn / kill，装货、位移、卸货由货站结构完成；中断可能留下已生成的假人，用台账旁的「生成清理命令」补齐。当前默认按「工具只发 spawn/kill」实现，若真实流程需要路径点/传送/交互命令，需在 `core/plan.py` 增加阶段。
8. 执行模式仅 Windows，且只认 `GLFW30` / `LWJGL` 窗口类；启动器（HMCL/PCL）标题带 Minecraft 也不会被误认。游戏以管理员启动时，本应用必须同样以管理员运行，否则 UIPI 丢按键。
9. 键鼠自动化是否符合服务器规则由使用者自行确认；默认 `allowExecute=false`，必须在设置里显式打开。

---

## 10. 接手建议

v1.1.5 已发布标签并推送；本次（1.2.0）新增 **假人搬货**：站点管理（含旧 `stops.json` / 文本导入、导出 JSON/文本）、盒数→人数→批次→命令、spawn/kill 双页、运单台账（点击恢复命令）、可选的真实键鼠执行（抗卡顿、ESC 中断、补清理）、环境诊断与三语文案，并新增平台能力 `Context.doc_load/doc_save` 与 `platform/autoinput.py`；另加 `src/tool_bundles/station_configmaker.py`。

建议按 `TODO.md` 继续：先与用户确认**假人搬货的真实货站流程**（是否需要路径点/传送/交互命令），再做**史莱姆区块查找器**。1.2.0 的收尾：提交、打标签、重拍截图（`README_img/` 与 `README_img/en/` 各新增一张假人搬货页）、重新打包 `dist/`、按 §6 跑一次 `LSPKIT_GUI_TEST=1` 的注入测试。
