# LSP PlayerKit

> A desktop toolbox for LSP players. It merges the Universal Pearl Cannon Configurator and the Border Cannon Configurator into one app. \
> Everything runs locally — no network, no uploads. \
> Grab the latest build from the release page 😘😘😘

[简体中文](../README.md) · [Adding a tool](ADDING_A_TOOL.en.md)

### 1. Guide

##### Step 1 — Launch and layout

The left rail lists the tools; the right side is the workspace of the active tool. From top to bottom: Pearl Cannon, Border Cannon, a “Coming soon” placeholder, and About.

The top-right corner switches language (English / 简体中文 / 繁體中文) and light/dark theme; the gear opens settings.

![1-main.png](../README_img/1-main.png)

##### Step 2 — Pearl cannon

Using **(10000, 10000)** as the destination: fill in the muzzle X/Z, target X/Z and max TNT, choose Flat or Arc, then click **Calculate TNT**.

- The result table is sorted by flight time ascending. Click the **Distance error** or **Flight time** header to re-sort; click again to reverse.
- Selecting a row shows the blue/red TNT array breakdown at the bottom, e.g. `20 + 10 + 2 + 1 = 33`.
- **Simulate** steps the pearl tick by tick for the selected configuration; the trace table highlights the expected arrival tick in orange.
- **Save as default** at the bottom of the panel stores the current muzzle, target and launch mode; **Fill from defaults** restores them.

![2-trace.png](../README_img/2-trace.png)

##### Step 3 — Border cannon

Using **(3750000, 3750000)** as the destination (Y = 128, flight time 1200 gt): fill in the muzzle coordinates, the destination coordinates and the expected flight time, then click **Calculate TNT**. Muzzle and destination are separate cards, with the destination tinted teal so they are hard to mix up.

The result table lists three TNT charges per tick. Selecting a row shows:

- minor (remaining TNT) and major (780-charge) breakdowns for each of the three TNT
- predicted landing coordinates and the three-axis momentum

**Save as default** remembers the current muzzle, destination and flight time; **Fill from defaults** restores them.

![5-border.png](../README_img/5-border.png)

##### Step 4 — Settings

Click the gear in the top-right corner:

- **Tool options**: muzzle position, max TNT, TNT per array, momentum parameters, and the direction reference for the border cannon. Saved values take effect immediately.
- **Import config**: import this app’s JSON, or the legacy `settings.json` from either original project — it is detected and converted automatically.

![3-settings.png](../README_img/3-settings.png)

##### Step 5 — Data & storage

Configuration lives in the `data` folder next to the executable by default; copy the whole folder to migrate.

- Change location: pick a new folder, existing settings are copied and switched immediately
- Open folder / reset location
- Export / import a bundle (zip with every tool and preference)
- If the install folder is read-only (e.g. `Program Files`), the app falls back to the user folder automatically

![4-storage.png](../README_img/4-storage.png)

##### Step 6 — About

The About button in the bottom-left shows the version, stack, privacy note and license, with shortcuts to the configuration docs and the GitHub repository.

![6-about.png](../README_img/6-about.png)

### 2. Data layout

```
<folder containing the exe>/
├─ LSP_PlayerKit.exe
└─ data/
   ├─ settings/
   │  ├─ app.json        language, theme, window state
   │  ├─ pearl.json      pearl cannon settings
   │  └─ border.json     border cannon settings
   ├─ backups/           snapshot before each save, last 5 kept
   └─ .lock              prevents two instances overwriting each other
```

Window size, position and the maximized state are stored in `app.json` and restored on the next launch.

Legacy configuration files:

| Tool | Legacy path |
|---|---|
| Pearl cannon | `LSP_PearlCannonConfig/resources/settings/settings.json` |
| Border cannon | `LSP_BorderCannonConfig/resources/settings/settings.json` |

### 3. Calculation notes

- Flat/arc rounding and enumeration order for the pearl cannon, and the three-TNT solve for the border cannon, are line-by-line compatible with the legacy implementations; golden snapshot tests keep the numbers identical.
- Some flight times produce negative TNT for the border cannon (the legacy app had no solution either). The table then reports “No valid configuration for this flight time” — shorten the flight time to get a solution.

### Stack

Python 3.9 + pywebview 6 + Vue 3 + Vite

### License

GPL-3.0 license
