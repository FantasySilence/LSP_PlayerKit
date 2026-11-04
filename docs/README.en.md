# LSP PlayerKit

> A desktop toolbox for LSP server players. It merges the Universal Pearl Cannon Configurator, the Border Cannon Configurator and a Material Converter into one app. \
> Everything runs locally — no network, no uploads. \
> Grab the latest build from the release page 😘😘😘

[简体中文](../README.md) · [Adding a tool](ADDING_A_TOOL.en.md)

## Contents

- [1. Quick start](#1-quick-start)
- [2. Pearl cannon](#2-pearl-cannon)
  - [2.1 Usage](#21-usage)
  - [2.2 Settings](#22-settings)
- [3. Border cannon](#3-border-cannon)
  - [3.1 Usage](#31-usage)
  - [3.2 Settings](#32-settings)
- [4. Material converter](#4-material-converter)
  - [4.1 Import a material list](#41-import-a-material-list)
  - [4.2 Search and sorting](#42-search-and-sorting)
  - [4.3 Stack size: default and batch](#43-stack-size-default-and-batch)
  - [4.4 Ignoring materials](#44-ignoring-materials)
  - [4.5 Conversion result](#45-conversion-result)
  - [4.6 Loading plan](#46-loading-plan)
  - [4.7 Export CSV](#47-export-csv)
  - [4.8 Settings](#48-settings)
- [5. Settings](#5-settings)
- [6. Data and storage](#6-data-and-storage)
- [7. Calculation notes and limitations](#7-calculation-notes-and-limitations)
- [Stack](#stack)
- [License](#license)

---

## 1. Quick start

Unzip the release and double-click `LSP_PlayerKit.exe`. Python and Node are not required.

The window has three parts:

- **Left rail**: Pearl Cannon, Border Cannon, Material Converter, a “Coming soon” placeholder, and About.
- **Top bar**: active tool name and description, language (English / 简体中文 / 繁體中文), light/dark theme, and the settings gear.
- **Workspace**: parameters on the left, results on the right.

Shortcuts: `Ctrl+1 / Ctrl+2 / Ctrl+3` switch tools, `Ctrl+,` opens settings. Window size and the maximized state are remembered.

![Main window](../README_img/1-main.png)

---

## 2. Pearl cannon

### 2.1 Usage

Start from **Input pearl coordinates**:

1. Fill in **muzzle X / Z**, **target X / Z** and **max TNT**.
2. Pick a **launch mode**: Flat or Arc (Arc is disabled if you turn off “Arc enabled” in settings).
3. The **direction** compass points at the result automatically after a calculation; you can also pick one of the four directions manually, which shows a “Manual” badge.
4. Click **Calculate TNT**.

Results and actions:

- Columns: **Distance error / Flight time / Blue TNT / Red TNT / Total TNT**, sorted by **flight time ascending** by default. Click the **Distance error** or **Flight time** header to sort; click again to reverse.
- Selecting a row shows the blue and red TNT array breakdown at the bottom, e.g. `20 + 10 + 2 + 1 = 33`; **Copy** puts it on the clipboard.
- **Simulate** steps the pearl tick by tick for the selected configuration and switches to the **Trace** tab: columns are **tick / X / Y / Z**, and the expected arrival tick is highlighted in orange and scrolled into view.
- **Save as default** writes the current muzzle, target, max TNT and launch mode back to settings; **Fill from defaults** overwrites the inputs with the saved values.

![Pearl cannon result and trace](../README_img/2-trace.png)

### 2.2 Settings

Open Settings → Tool options:

| Setting | Description |
|---|---|
| Max TNT | Upper bound for one calculation, default 3640 |
| TNT per array | TNT equivalent of one array, default 260 |
| Muzzle X / Z | Default muzzle position, default `-31.9375 / -8.0625` |
| Target X / Z | Target coordinates pre-filled when the tool opens, default `0 / 0` |
| Launch mode | Default Flat or Arc |
| Arc enabled | When off, the Arc mode is unavailable |
| Flat: XZ motion / Y motion / initial Y motion / initial Y position | Flat trajectory parameters measured in game — **do not change casually** |
| Arc: the same four | Arc trajectory parameters |

Settings apply immediately. The numbers are line-by-line compatible with the legacy `LSP_PearlCannonConfig`; changing the motion parameters changes the results.

---

## 3. Border cannon

### 3.1 Usage

The inputs are two separate cards, so the destination is hard to type into the muzzle by mistake:

1. **Muzzle (pearl start position)**: X / Y / Z.
2. **Destination (pearl landing)**: X / Y / Z.
3. **Expected flight time** in gt.

Click **Calculate TNT**; the table lists three TNT charges and a direction per tick (100 rows by default). Selecting a row shows the **configuration decode** panel:

- **Predicted landing coordinates** (X / Z, three decimals)
- **minor** (remaining TNT) and **major** (780-charge) breakdowns for each of the three TNT, e.g. `371 = 260 + 80 + 20 + 10 + 1`, `78 = 40 + 20 + 10 + 8`
- three-axis momentum, plus one-click copy of the full decode text

**Save as default** and **Fill from defaults** work the same way as in the pearl cannon.

![Border cannon result](../README_img/5-border.png)

### 3.2 Settings

| Setting | Description |
|---|---|
| Muzzle X / Y / Z | Default muzzle position |
| Destination X / Y / Z | Default destination |
| Expected flight time | Default flight time (gt) |
| Direction reference | `Real muzzle`: direction from the current muzzle (recommended); `Legacy`: the old hard-coded `(10000, 10000)` |

> Long flight times may produce negative TNT (the legacy app had no solution either). The table then shows “No valid configuration for this flight time” — shorten the flight time or adjust the destination.

---

## 4. Material converter

Converts a Litematica material list into **shulker boxes / stacks / items** and produces a loading plan.

![Material converter](../README_img/7-material.png)

### 4.1 Import a material list

- Click **Import material list** and pick the CSV exported by Litematica. **GBK and UTF-8** are both supported.
- Headered CSV is preferred: the **name** and **count** columns are detected by header, and Litematica's `Item, Total, Missing, Available` uses the **Total** column. Files without a header fall back to `name count` lines.
- After import, the left column lists each material's **name and count** and converts immediately. Names are kept exactly as imported.
- Re-importing clears the current stack overrides, ignore list and search.

### 4.2 Search and sorting

- The search box filters as you type and shows up to **8 suggestions** (click or press `Enter` to apply, `Esc` or `✕` to clear).
- **Select all** applies only to the **filtered** rows, handy for “search then batch-process”.
- Click **Count ▼** above the list to toggle ascending/descending (descending by default).
- The result panel has a **stack filter**: `All / 64 / 16 / 1`; the **Count** header sorts the table.

### 4.3 Stack size: default and batch

- **Default stack size**: `64` / `16` / `1 (unstackable)`.
- **Batch**: select materials, choose 64/16/1 in the batch bar, click **Apply to selected**. The selection is cleared afterwards so you do not accidentally touch the next batch.
- Materials with a custom stack size show a teal chip; the result table has a **Stack** column with the value actually used.
- With `1`, each slot holds one item and the “stacks” column is always 0.

### 4.4 Ignoring materials

- Select materials and click **Ignore selected**; they are excluded from conversion, loading plans and export. When every selected material is already ignored, the button becomes **Restore selected**.
- The **Ignored materials** panel below the list shows what is ignored and lets you restore one or all of them.
- Ignored rows stay in the list, struck through with an “Ignored” tag.

### 4.5 Conversion result

Columns: **Material / Stack / Count / Shulkers / Stacks / Items**.

- **Shulkers** counts full boxes; **stacks** and **items** are the remainder — e.g. 4766 at stack 64 = 2 boxes + 20 stacks + 30 items.
- The footer shows kinds, total items, full boxes, **boxes needed** (per-material ceiling summed up, i.e. how many boxes to carry) and the default box capacity.
- Names and counts come from the imported list; the loading plan and CSV export use the same data.

### 4.6 Loading plan

**Loading plan** packs everything into the fewest shulker boxes:

- Each material is first converted to **slots**: `full stacks + (remainder ? 1 : 0)`, with 27 slots per box.
- Boxes are filled largest-first until full, so the box count equals `ceil(total slots / 27)`, the theoretical minimum.
- The dialog has two views: **Cards** (one card per box, ≤ 12 boxes by default) and **List** (box index on the left, details on the right, used automatically for larger plans). Switch any time from the title bar; both have their own scrollbars.
- Each box lists “material · stacks/items · slots”, and **Copy plan** exports the whole plan as text.

![Loading plan](../README_img/8-pack.png)

### 4.7 Export CSV

Two export settings at the bottom of the left column:

- **Export name**: empty means `<imported file name>_converted.csv`.
- **Export folder**: empty means `<data folder>/output` (by default `<exe folder>/data/output`). Use **Choose…** to pick another folder; the choice is saved.

The export follows the current **filter and sort**, is UTF-8 with BOM, and opens correctly in Excel.

### 4.8 Settings

| Setting | Description |
|---|---|
| Max stack size | `64` / `16` / `1`, default for new conversions |
| Slots per shulker | Slots in one shulker box, default 27 |
| Export folder | Default CSV folder, empty means `<data folder>/output` |

---

## 5. Settings

Click the gear (or press `Ctrl+,`) to open the settings drawer. It has three tabs:

- **Tool options**: generated from the active tool's schema; saved values apply immediately. Reset and import live at the bottom.
- **Data & storage**: view/change the data folder, open it, export/import a settings bundle.
- **About**: version, stack and documentation shortcuts.

**Import config** accepts two kinds of files:

- a single JSON exported by this app (e.g. `pearl.json`);
- the legacy `resources/settings/settings.json` from either original project — detected and converted automatically (the legacy border cannon switches to the legacy direction mode).

The **About** tab shows the version, stack, privacy note and license, with shortcuts to the configuration docs and the GitHub repository.

![Settings · Tool options](../README_img/3-settings.png)

![About](../README_img/6-about.png)

---

## 6. Data and storage

Settings live in `data` next to the executable by default. **Copy the whole folder to migrate.**

```
<folder containing the exe>/
├─ LSP_PlayerKit.exe
└─ data/
   ├─ settings/
   │  ├─ app.json        language, theme, window state
   │  ├─ pearl.json      pearl cannon settings
   │  ├─ border.json     border cannon settings
   │  └─ material.json   material converter settings
   ├─ output/            exported CSV files (default folder)
   ├─ backups/           snapshot before each save, last 5 kept
   └─ .lock              prevents two instances overwriting each other
```

Data folder resolution (first match wins):

1. `--data-dir` on the command line or the `LSPKIT_DATA_DIR` environment variable
2. `portable.json` next to the executable (portable mode)
3. `%APPDATA%\LSP_PlayerKit\location.json` (a location the user picked)
4. default `<exe folder>/data`; if it is not writable (e.g. installed in `Program Files`), the app falls back to `%APPDATA%\LSP_PlayerKit\data` and shows a notice

Other behaviour:

- Every write is “temp file + replace”; a corrupted JSON falls back to the latest backup.
- **Export / import bundle** produces a zip with every tool and preference.
- Window size and maximized state are stored in `app.json` and restored on the next launch.

![Data & storage](../README_img/4-storage.png)

---

## 7. Calculation notes and limitations

- Flat/arc rounding and enumeration order for the pearl cannon, and the three-TNT solve for the border cannon, are line-by-line compatible with the legacy implementations; golden snapshot tests keep the numbers identical.
- Some flight times produce negative TNT for the border cannon (the legacy app had no solution either); the table then reports “No valid configuration for this flight time”.
- Box counts use 27 slots per box; **boxes needed** sums the per-material ceiling, which is the number of shulker boxes to carry.
- The loading plan uses the theoretical minimum number of boxes, but one material may be split across two adjacent boxes; the dialog lists them by box number.
- Material names and counts come straight from the imported list; conversion only changes boxes/stacks/items, never names.

---

## Stack

Python 3.9 + pywebview 6 + Vue 3 + Vite + numpy

## License

GPL-3.0 license
