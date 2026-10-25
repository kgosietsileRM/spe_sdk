# Interactive traffic CLI (stand-alone demo)

A small interactive command shell that reads media from `../assets/link.json`,
runs local or server-side detection, and prints calibrated lane analytics.

This folder is **independent** from the SDK project: `bootstrap.ps1` creates a
local `.venv` and installs the built wheel from `../assets`. It never imports
from `../../src`.

## Run

```powershell
.\run.ps1
```

The first run bootstraps `.venv` and installs the SDK wheel. Then use the
prompt:

```text
spe> sources
spe> use hd
spe> analyze 80 5
spe> report
spe> overlay
spe> quit
```

Useful commands:

| Command | Purpose |
| --- | --- |
| `sources` | List keys from `assets/link.json` (`hd`, `fullHd`, `online`). |
| `use <key>` | Select a video. Remote keys download into `assets/.cache`. |
| `grid <rows> <columns>` | Change the calibrated lane grid. |
| `mode local\|server` | Local OpenCV motion detection or SPE server detection. |
| `server <url> [model]` | Configure `http://127.0.0.1:5000` and `model-a`. |
| `analyze [frames] [fps]` | Run the pipeline and print lane stats. |
| `report [path]` | Write the last report as JSON. |
| `overlay [path]` | Write the last annotated frame as JPEG. |

Non-interactive use:

```powershell
.\run.ps1 --source hd --frames 20 analyze
```

Server mode requires the SPE engine to be running:

```powershell
.\run.ps1 --source hd --mode server --url http://127.0.0.1:5000 --model model-a --frames 20 analyze
```

To rebuild the environment:

```powershell
.\bootstrap.ps1 -Reinstall
```
