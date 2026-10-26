# PowerShell → batch traffic analyzer (stand-alone demo)

PowerShell bootstraps an isolated environment, then executes a real Windows
batch script (`analyze.bat`), which runs `batch_analyze.py` over the media in
`../assets/link.json`.

This folder is independent: it installs `spe-engine==0.2.1` from PyPI into its
own `.venv` through `requirements.txt` and never imports from `../../src`.

## Run

```powershell
.\run.ps1
```

This analyzes the `video` source at 5 fps for 60 frames and writes:

```text
outputs/
├── video.json
├── video.jpg
├── summary.json
└── summary.csv
```

Options:

```powershell
.\run.ps1 -Frames 120 -Fps 3 -Sources video
.\run.ps1 -Mode server -Url http://127.0.0.1:5000 -Model model-a
.\run.ps1 -Out C:\temp\spe-batch -Reinstall
```

The batch layer can also be called directly after bootstrapping:

```powershell
.\analyze.bat --sources video --frames 40 --fps 5
```

The batch script fails with a clear message if the local virtual environment
does not exist. Use `bootstrap.ps1` to create it.

To recreate or migrate an existing environment to the PyPI SDK install, run:

```powershell
.\bootstrap.ps1 -Reinstall
```
