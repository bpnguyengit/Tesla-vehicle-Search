# Tesla Vehicle Search

Desktop app that searches **Tesla’s public US inventory** across locations and ranks vehicles by the best (lowest) effective price.

Built with **Python 3** and **Tkinter** (stdlib). Network calls use **urllib**. Runtime needs no `pip install`; packaging uses PyInstaller (see below).

## Run (source)

```bash
cd Tesla-vehicle-Search
python3 tesla_search.py
```

Window title: **Tesla Vehicle Search**.

## Filters

| Filter | Notes |
|--------|--------|
| **Models** | Model 3 / Y / S / X / Cybertruck (multi-select, default all). Mapped to Tesla codes `m3`, `my`, `ms`, `mx`, `ct`. |
| **Condition** | New, Used, or Both (default). |
| **Year** | Min / max. When left wide open, vehicles with no `Year` are kept. If you narrow the range, missing or out-of-range years are excluded. |
| **ZIP + distance** | Default ZIP `90210`. Choose a mile radius, or **Any / nationwide** to search all locations. ZIP → lat/lng via [zippopotam.us](https://api.zippopotam.us/us/{zip}). |

## Results

- Ranked by effective purchase price (ascending).
- Cheapest match marked **Best deal**.
- Columns: price, discount, year, model, trim, mileage, location, distance, VIN.
- Click column headers to sort; click a row for details.
- Search runs on a background thread so the UI stays responsive.

## Help menu

- **User guide** — filters, ranking, Best deal, and data source.
- **Check for updates** — compares the stamped local calendar version to `app_release.json` (GitHub raw URL for this repo when reachable, otherwise the bundled file). Does **not** download or install anything.
- **About** — app name, calendar version, short description.

## Data source

Live data from Tesla’s public inventory endpoint:

`GET https://www.tesla.com/inventory/api/v4/inventory-results?query=<url-encoded JSON>`

Inventory availability, fields, and anti-bot rules can change without notice. This app does not use Tesla account credentials or private APIs. Datacenter networks sometimes receive HTTP 403 from Tesla’s edge; a normal home/office connection usually works.

## Windows packaging (dashboard_PE-style)

Requires Python 3.12+ on Windows. Inno Setup 6/7 is required only for the installer step.

### 1. Build the program EXE (one-folder)

```bat
build_exe.bat
```

- Optional argument: exe base name without `.exe`.
- **Default exe name: `Tesla Search`** → output `dist\Tesla Search\Tesla Search.exe` plus `_internal\`.
- Creates/uses `.venv`, runs `pip install -r requirements.txt pyinstaller`, then PyInstaller via `packaging\tesla_search.spec`.
- Saves the name in `packaging\last_build_name.txt` for the setup script.

Example with an explicit name:

```bat
build_exe.bat "Tesla Search"
```

### 2. Build the Setup installer

```bat
build_setup.bat
```

- Optional args: `build_setup.bat "Tesla Search"` or `build_setup.bat "Tesla Search" 2026.10.03.2130`
- Stamps a calendar version **Year.MM.DD.HHMM** into `app_version.py` (Help → About) via `scripts\stamp_setup_version.py` (PowerShell `Get-Date` fallback).
- Writes `app_release.json` and compiles **`TeslaSearch_Setup.exe`** with Inno Setup from the ONEDIR under `dist\`.

## Project layout

```
tesla_search.py              # Tkinter GUI
inventory.py                 # Inventory API client, geocoding, ranking
app_version.py               # APP_VERSION (stamped by setup build)
update_check.py              # Help → Check for updates
app_release.json             # Version / setup filename for update checks
build_exe.bat                # PyInstaller ONEDIR build
build_setup.bat              # Inno Setup installer flow
resolve_app_ver.bat          # Auto calendar version
build_setup_body_a.bat       # Installer body (part 1)
build_setup_body_b.bat       # Installer body (part 2)
scripts/stamp_setup_version.py
packaging/tesla_search.spec
requirements.txt             # pyinstaller (build)
smoke_test.py                # Headless search smoke (no GUI)
tests/                       # Parse fixtures / unit checks
```

## Optional smoke test

```bash
python3 smoke_test.py
```

Calls the live inventory search (Model Y, new, ZIP 90210) without opening the GUI and prints the cheapest priced vehicle if any are returned.
