# Adaptive signal console (stand-alone web demo)

A creative SPE use case: estimate per-lane queue pressure from traffic video
and recommend adaptive green-time splits for a junction.

- Calibrates three virtual approaches over the road.
- Tracks objects and aggregates queue, occupancy, crossings, and dwell.
- Allocates green time proportionally to queue pressure (8 s minimum green,
  6 s lost time, 60–120 s cycle).
- Lets you explore a **what-if** cycle length live.
- Supports local OpenCV detection or the SPE server endpoint.

Independent environment: `bootstrap.ps1` creates a local `.venv` and installs
the SDK wheel from `../assets` plus Flask. Nothing imports from `../../src`.

## Run

```powershell
.\run.ps1
```

Open <http://127.0.0.1:5002>, choose `hd` or `fullHd`, and press
**Start simulation**.

Outputs land in `outputs/sessions/<id>/`:

- `latest.jpg` — annotated frame used by the dashboard
- `report.json` — full analytics plus the signal recommendation

## API

```powershell
$body = '{"source":"hd","preset":"highway","frames":60,"fps":5,"mode":"local"}'
$id = (Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5002/api/sessions -ContentType application/json -Body $body).id
Invoke-RestMethod http://127.0.0.1:5002/api/sessions/$id
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5002/api/sessions/$id/what-if -ContentType application/json -Body '{"cycle_seconds":90}'
```

Server mode requires the SPE engine at `http://127.0.0.1:5000` (configurable in
the form).
