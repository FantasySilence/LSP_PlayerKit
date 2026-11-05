# 开发任务（待办）

> 记录于 2026-11-04，更新于 2026-11-06；版本 **1.2.0** 已实现「假人搬货」（工作区未提交，基线为 `904fee1` / `v1.1.5`）。
> `README.md`、`docs/README.en.md` 的改动已随 cd9d8a2 提交；`src/tool_bundles/` 为新增的附赠工具目录，尚未打包，见 §6。
> 本文件尚未提交，可随时决定是否纳入版本库。

## 1. 投影模组材料转换计算器（✅ 已完成 2026-11-04）

- 工具：`tools/material`（左轨第三项「材料换算器」），解析 / 换算 / 装填分在 `core/parse.py`、`core/convert.py`、`core/packing.py`。
- 输入：只支持导入材料清单（`file_open_text`，GBK / UTF-8）；CSV 表头识别，Litematica 取 Total 列；名称原样保留并自动换算。
- 搜索：实时过滤 + 最多 8 条建议（Enter 填入、Esc/✕ 清空）；全选只作用于过滤结果。
- 排序/筛选：待处理列表按数量升降序；结果表按「堆叠」筛选、按「数量」排序。
- 堆叠：默认 64/16/1，支持勾选后批量应用（完成后清空勾选），单材料覆盖用青色芯片标出。
- 忽略：批量忽略/恢复，列表下方常驻已忽略面板（逐条/全部恢复）；忽略项不参与换算、装填、导出。
- 结果：材料名称 / 堆叠 / 数量 / 潜影盒 / 组 / 个；底部统计种类、总数量、整盒、折合盒数、默认单盒。
- 装填建议：按「占用格数」大件优先逐盒填满，盒数 = `ceil(总格数/27)`；卡片/列表双视图、可复制清单；同种材料连续满装多盒时合并成一张卡片（`1–2 号盒` + 「合装 N 盒」），节约页面空间；卡片按实测高度拼图式排布，短卡下方不留空行。
- 导出：文件名默认 `<导入名>_converted.csv`，目录默认 `<数据目录>/output`，可在设置或左栏修改；导出跟随筛选与排序，UTF-8 BOM。
- 设置：`stackSize`（枚举）、`shulkerSlots`、`exportDir`（path 类型，带目录选择）。
- 测试：`test_bridge.py` 与 `test_litematic.py` 覆盖解析/表头/空输入/容量/不可堆叠/按材料覆盖/忽略/装填最少盒数/导出目录/投影两种位打包/墙上方块与炼药锅折算/流体过滤/三语名称；全套 **49 passed**。
- 2026-11-05 增补：**支持多份材料清单**——一次多选 + 可追加（`file_open_texts`），每份清单一行带勾选框（决定是否参与换算）、种类·数量与移除按钮；`core/parse.py:parse_sources()` 跨清单按材料名求和，`convert` / `pack` 接受 `texts` 并回传各清单摘要。导出默认名：单份用该清单名，多份用 `merged_converted.csv`。截图同步重拍。
- 2026-11-05 增补：**支持 `.litematic` 投影**——`core/litematic.py` 解析 gzip NBT、多区域、紧凑/padded 位打包；按**物品形式**统计（`core/block_items.py`，Wiki 物品形式列 1018 条）：墙上的告示牌/火把并入对应物品、含水/熔岩/细雪炼药锅并入炼药锅、红石线并入红石粉、作物并入种子；水/岩浆只算源头，气泡柱/火/活塞头/传送门等无物品方块过滤。实测与 Litematica 中文 CSV 完全一致（51 种 / 17 091 个，过滤 807）。导入接口为 `file_open_material_lists`，`sources` 支持 `text` 或 `entries`；材料名按当前界面语言显示（`core/localize.py`，`entries` 带 `id`，切换语言自动重算），名称表已更新到 **Minecraft 26.3**（`core/block_names.py`：zh_cn 1301 / zh_tw 1301 / en 1297 条）。

## 2. 假人自动化（适配假人搬货站）（基础版已完成 2026-11-06）

- 已落地为 `tools/puppet`：站点管理（增删改 + 旧 `stops.json` / 「名称 x y z 前缀」导入）、盒数→人数（`ceil(盒数/36)`）→批次（24 人/批）→ spawn / kill 命令、命令复制与 `.txt` 导出、运单台账（200 条）、可选真实键鼠执行（剪贴板粘贴、卡顿回探重试、ESC 中断、补清理）与环境诊断。
- 执行默认关闭（`allowExecute=false`），只认 `GLFW30`/`LWJGL` 窗口类，不会误认启动器；平台层新增 `platform/autoinput.py` 与 `Context.doc_load/doc_save`。
- 测试：114 passed + 3 skipped（3 条真实注入用例需 `LSPKIT_GUI_TEST=1`，用 `tests/harness/mc_chat_stub.py` 的迷你聊天栏验证）。
- 2026-11-06 增补：站点支持导出（JSON / 文本，JSON 无 BOM、可再次导入）；`src/tool_bundles/station_configmaker.py` 可交互生成站点 JSON；运单台账条目可点击，把该次执行保存的命令恢复到上方预览并再次执行。
- 仍待确认（决定是否需要扩展 `core/plan.py` 的阶段）：
  - 假人从生成到卸货的完整物理流程；「生成于目的地」的真实用途。
  - 是否需要路径点 / 传送 / 交互（`use` / `goto`）命令，还是货站结构自己完成位移。
  - 命名是否必须带 `bot_` 前缀（旧实现 spawn 与 kill 名字不一致，已统一为模板）。
  - 超过 864 盒时是自动连发多批，还是每批手动推进（当前生成全部批次、由人决定何时执行）。
- 相关文件：`src/lspkit/tools/puppet/`、`src/lspkit/platform/autoinput.py`、`web/src/tools/puppet/`、`tests/test_puppet_*.py`。

## 3. 珍珠炮 / 边境炮「保存当前设置为默认」（✅ 已完成 2026-11-04）

- 珍珠炮 schema v3 新增 `targetX/targetZ/fireMode`；两个工具参数面板底部新增「保存为默认」「从设置填充」。
- 保存时合并现有设置，不覆盖动量参数；保存后 Toast 反馈。

## 4. 史莱姆区块查找器

- 参考：<https://github.com/wifi504/find-slime-chunk>（Java，GPL-3.0，兼容本仓库协议）
- 它做什么：输入世界种子和两个区块坐标，在矩形范围内寻找「直径 17 区块的圆」内史莱姆区块最多的位置，输出前 100 名。
  - 依据：玩家刷怪半径 128 格 = 8 区块，加上所在区块，正好是直径 17 区块的圆。
  - 参考实现例子：(357, 138) 处圆形区域有 44 个史莱姆区块；1M 区块约 0.9 秒，1 亿区块约 137 秒（Java 暴力遍历）。
- 判定公式（Java Edition，必须精确复刻 48 位 `Random`）：
  ```text
  slimeSeed = seed
            + x*x*0x4c1906 + x*0x5ac0db
            + z*z*0x4307a7 + z*0x5f24f
            ^ 0x3ad8025f
  new Random(slimeSeed).nextInt(10) == 0
  ```
  注意 `nextInt(10)` 不是 2 的幂，带拒绝采样，不能近似成 `% 10`。
- 建议接入：
  - 新工具 `tools/slime`：`core/slime.py` 纯计算，`actions.py` 暴露 `find`。
  - 种子按**字符串**收（JS Number 超 2^53 会丢精度），矩形两角用区块坐标，半径默认 8 且可在设置里改。
  - 性能：先算矩形内史莱姆掩码，再用 numpy 前缀和/滑窗统计每个圆心，避免逐点暴力；超大范围加面积上限。
  - 前端：Canvas 区块地图 + 前 100 名表格（点击定位、复制坐标、导出 CSV）。
- 待确认：是否支持基岩版、半径是否固定 17、超大范围是否需要后台线程与进度反馈。

## 5. 文档（✅ 已完成 2026-11-05，已提交 cd9d8a2）

- `README.md` / `docs/README.en.md` 重写：目录、下载（百度网盘，提取码 1234）、三个工具的使用与设置、数据存储、限制、**随应用附赠的小工具**。
- `ADDING_A_TOOL.md` / `docs/ADDING_A_TOOL.en.md` 重写：以数学计算器 `calc` 为例。
- `README_img/` 8 张浅色截图（v1.1.1、5 项左轨）；删除仓库根目录误放的三个旧 exe（说明见 README）。
- 2026-11-05：中英文两套截图（各 8 张、1600×1025）先后按 1.1.2、1.1.3、1.1.4、1.1.5 重拍；`README_img/` 中文、`README_img/en/` 英文，`docs/README.en.md` 引用指向英文目录；两套的「数据与存储」页显示同一 `data` 路径。为此顺带修了三处只在英文下暴露的问题——左轨标签换行（`App.vue`）、设置单位 i18n（schema 改 `unit.*`，三语补齐）、装填卡片列宽 232→300px（英文长名称不再被截断）。
- 2026-11-06：关于页「打开说明文件」改为打开 `resources/docs/README.pdf` / `README.en.pdf`（按界面语言），PDF 由本地脚本 `docs/build_readme_pdf.py`（不入库）用 Edge headless 生成，改 README 后需重新生成；执行结束补发英文 `Operation completed successfully`。

## 6. 随应用附赠的三个小工具纳入仓库（已完成 2026-11-05）

- 目录：`src/tool_bundles/`，与 `src/lspkit/` 平级，独立于主应用（互不 import，不进主应用 spec）。
- 三个工具：
  - `maincannon_configmaker.py`、`bordercannon_configmaker.py`：从旧项目 `test/` 迁入；补 banner 与回车确认，记录逻辑未改，输入提示带样例。
  - `configgenerator.py`：以 `ConfigGenerator.exe`（2024-07-12 构建）黑盒实测为准复现——banner、67 段横线、输入校验重试、只有 `y` 进抛射分支、写 exe 同目录、`json.dump(indent=4)`；文案另与回捞的旧源码 `gen_config_json.py`（`6464bce~1`）比对，banner 18 行 0 差异。
  - 等价性验证：抛射／平射／小写 `y`／`yes`（回退平射）／非法输入／空文件名／小数边界共 7 个场景，与 exe 的 stdout 和产物逐字节一致；之后才做下述有意修正，改完即不再逐字节等价。
- 与旧 exe 的有意差异：
  - 修正 `XZ_INIT_POSTION` → `XZ_INIT_POSITION`（旧版少一个 `I`，导入会丢炮口 X/Z）。`tools/pearl/legacy.py` 的 `convert()` 正是按 `XZ_INIT_POSITION` 与 `MOTION_FOR_*` 读取，修正后产物可直接导入珍珠炮工具。
  - 保存后输出「配置文件已保存至 …」（旧 exe 没有任何提示）。
  - banner 的 Github 链接改为本仓库 `LSP_PlayerKit`。
  - 输入提示全部加入格式与样例：坐标 `例：-31.9375`、坐标对 `例：(887, -189)`、TNT 数量 `例：3640`、文件名 `例：pearl_-31.9375_-8.0625`；样例均为实测可用输入。
- 打包（2026-11-05 完成）：
  - 三个 spec 在本地 `packaging/`（**不入库**，已加入 `.gitignore`）：`ConfigGenerator.spec`、`MainCannonConfigMaker.spec`、`BorderCannonConfigMaker.spec`；单文件控制台，**不配置图标**（用 PyInstaller 默认图标），`excludes` 去掉 tkinter/pandas/matplotlib/PIL/numpy。
  - 产物：`ConfigGenerator.exe` 6,329,728 B、`MainCannonConfigMaker.exe` 6,312,222 B、`BorderCannonConfigMaker.exe` 6,312,668 B（去掉图标后重新构建，位于 `dist/`，已被 `.gitignore` 忽略）。
  - 主应用也按 1.1.5 重新构建：`dist/LSP_PlayerKit/_internal/resources/version.json` 读回为 `1.1.5`。
  - 产物与脚本用同一组输入比对：退出码 0/0，stdout 逐字节一致（仅「已保存至」行的目录不同）。
  - 三个 exe 已复制到 `dist/LSP_PlayerKit/`，与 `LSP_PlayerKit.exe` 同目录，随下一个下载包分发。
- 文档：`README.md` / `docs/README.en.md` 的「随应用附赠的小工具」已改为新工具说明，删除 `XZ_INIT_POSTION` 改名提醒，改为「产物可直接导入」。
- 待办：
  - ~~提交 `packaging/`、`src/tool_bundles/`、`README`、`.gitignore`~~ 已完成：`b56986b` / `188c481` / `7a1cf29`，并打标签 `v1.1.2`；随后 `20aa609` 把 `packaging/` 移出版本库、改为本地忽略。
  - 发布新下载包：`dist/LSP_PlayerKit/` 已按 1.1.5 重新打包（4 个 exe + `_internal`，77.3 MB / 123 个文件，测试数据与临时文件已清理），压缩上传网盘即可。
  - `HANDOFF.md` 已按 1.1.5 重写（版本、提交、多清单、打包脚本不入库等），仍未入库。
- 测试：`pytest tests -q` 现 **49 passed**；三个脚本可用 `.venv\Scripts\python.exe src\tool_bundles\<name>.py` 直接跑；三个 exe 可直接双击（1.1.5 已重新打包并冒烟通过）。

## 备注：未提交内容

- 已提交：`README.md`、`docs/README.en.md`（cd9d8a2）；`src/tool_bundles/` 与三个 spec 见 §6；材料多清单与 1.1.3 见 `a913e7b` / `5215282` / `4ca53d3`（tag `v1.1.3`）；装填合并 + 拼图排布与 1.1.4 见 `b75c7fc` / `22797f7` / `4dd5ecd`（tag `v1.1.4`）；投影导入与 1.1.5 见 `80e4f67` / `2cbb2c8` / `904fee1`（tag `v1.1.5`）。
- 未跟踪：`HANDOFF.md`、`TODO.md`、`material_list_en.csv`、`material_list_zh_cn.csv`（样例清单，不入库）。`packaging/` 只留本地，已被 `.gitignore` 忽略，不再出现在 `git status` 中。
- 构建产物：`dist/`、`build/` 均在 `.gitignore` 内，不入库；三个新 exe 与 `LSP_PlayerKit.exe` 同在 `dist/LSP_PlayerKit/`。
- 三个旧 exe 从未进入版本库，已从仓库根目录删除；`ConfigGenerator.exe` 的逆向样本（6.6 MB）已于 2026-11-05 删除。
