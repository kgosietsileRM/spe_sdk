# Template studio (stand-alone Flask demo)

Takes media from `../assets/link.json` or an upload, applies a spatial template
(calibration + grid), and renders a consistent JSON report through a Jinja JSON
template.

Independent environment: the local `.venv` installs the SDK wheel from
`../assets` and Flask; nothing imports from `../../src`.

## Run

```powershell
.\run.ps1
```

Open <http://127.0.0.1:5001>.

Presets live in `presets/`:

- `highway.json` — 2×3 grid over a three-lane approach.
- `compact.json` — 2×2 grid for narrower footage.

## API

```powershell
curl.exe "http://127.0.0.1:5001/api/analyze?source=hd&preset=highway&frames=20&fps=5"
curl.exe -X POST -F media=@clip.mp4 -F preset=highway "http://127.0.0.1:5001/api/analyze"
```

`report.json.j2` controls the response shape. Edit it to add, remove, or rename
fields without touching the analysis code.

Server detection mode uses the same form fields and expects the SPE engine at
`http://127.0.0.1:5000`.
