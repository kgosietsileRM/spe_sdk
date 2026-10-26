# Interactive traffic CLI (stand-alone demo)

A small interactive command shell that reads media from `../assets/link.json`,
runs local or server-side detection, and prints calibrated lane analytics.

This folder is **independent** from the SDK source tree: `bootstrap.ps1` creates
a local `.venv` and installs `spe-engine==0.2.1` from PyPI using
`requirements.txt`. It never imports from `../../src`.

## Run

```powershell
.\run.ps1
```

The first run bootstraps `.venv` and installs the SDK from PyPI. Then use the
prompt. Run `bootstrap.ps1 -Reinstall` to recreate an existing environment:

```text
spe> sources
spe> use video
spe> analyze 80 5
spe> report
spe> overlay
spe> quit
```

Useful commands:

| Command | Purpose |
| --- | --- |
| `sources` | List configured feeds from `assets/link.json` (`cam1`–`cam6`, `video`). |
| `use <key>` | Select a media key. Use `video` here for the direct MP4; the YouTube camera links are resolved by the web demo. |
| `grid <rows> <columns>` | Change the calibrated lane grid. |
| `mode local\|server` | Local OpenCV motion detection or SPE server detection. |
| `server <url> [model]` | Configure `http://127.0.0.1:5000` and `model-a`. |
| `analyze [frames] [fps]` | Run the pipeline and print lane stats. |
| `report [path]` | Write the last report as JSON. |
| `overlay [path]` | Write the last annotated frame as JPEG. |

Non-interactive use:

```powershell
.\run.ps1 --source video --frames 20 analyze
```

Server mode requires the SPE engine to be running:

```powershell
.\run.ps1 --source video --mode server --url http://127.0.0.1:5000 --model model-a --frames 20 analyze
```

To recreate an environment or migrate an existing local-wheel venv to PyPI:

```powershell
.\bootstrap.ps1 -Reinstall
```
