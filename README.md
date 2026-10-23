# SPE SDK

[![CI](https://github.com/kgosietsileRM/spe_sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/kgosietsileRM/spe_sdk/actions/workflows/ci.yml)
[![Python versions](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](https://github.com/kgosietsileRM/spe_sdk/blob/main/LICENSE)

Python SDK for the **Spatial Intelligence Engine (SPE)** — spatial-intelligence
middleware that turns visual observations into a persistent spatial
representation. The SDK gives Python applications two ways to work with SPE:

- **Local core** — four-point planar calibration, coordinate transforms, grid
  rendering, point inspection, and detection spatialization, all in-process with
  no server required.
- **HTTP client** — a typed, dependency-free client for a running SPE engine
  server (`Flask` API), with a synchronous `SPEClient` and an asyncio
  `AsyncSPEClient`.

> Part of the SPE entry for the **OpenCV AI Competition 2026**.

[Full API reference →](https://github.com/kgosietsileRM/spe_sdk/blob/main/docs/index.md)

## Contents

- [Highlights](#highlights)
- [Installation](#installation)
- [Requirements](#requirements)
- [Quick start — local core](#quick-start--local-core)
- [Quick start — HTTP client](#quick-start--http-client)
- [Quick start — async client](#quick-start--async-client)
- [Quick start — command line](#quick-start--command-line)
- [Configuration](#configuration)
- [Spatial model](#spatial-model)
- [Error handling](#error-handling)
- [Examples](#examples)
- [API overview](#api-overview)
- [Development](#development)
- [Releasing](#releasing)
- [License](#license)

## Highlights

- Calibrate a camera/plane from four image points (`TL, TR, BR, BL`) using OpenCV.
- Map image pixels ⇄ normalized reference-plane coordinates via a reusable homography.
- Resolve calibrated **grid cells** and semantic **zones** (`A1`, `B3`, `AA2`, ...).
- Inspect single points against the canonical spatial state contract.
- Enrich provider-neutral detections with calibrated spatial data.
- Render image-space and perspective-correct calibrated grid overlays.
- Talk to a live SPE server: sources, calibration, ROI, grids, inspection,
  models, detection, and video sessions.
- Choose a synchronous or asyncio client, with swappable HTTP transports
  (stdlib `urllib`, `requests`, or `httpx`).
- Fully typed (PEP 561 `py.typed`), linted with ruff, checked with mypy, and
  tested to ~99% line coverage.

## Installation

```bash
pip install -e .                 # from this directory
pip install -e ".[http]"         # + the optional httpx transport
pip install -e ".[dev]"          # + test/lint/type/build tooling
pip install -e ".[docs]"         # + mkdocs toolchain
```

Extras may be combined, e.g. `pip install -e ".[http,dev]"`.

Runtime dependencies are intentionally small: `numpy` and
`opencv-python-headless`. The
synchronous HTTP client and the `AsyncSPEClient` wrapper use only the Python
standard library; the `http` extra is only needed to opt into the `httpx`
transport.

## Requirements

- Python **3.10 – 3.14**
- `numpy >= 1.24`
- `opencv-python-headless >= 4.8`

## Quick start — local core

```python
from spe import SpatialEngine

# Four image points in TL, TR, BR, BL order for a 1280x720 frame.
engine = SpatialEngine(grid_rows=4, grid_columns=6)
engine.calibrate(
    [[180, 120], [1090, 150], [1180, 640], [90, 660]],
    source_width=1280,
    source_height=720,
)

image_point = [640, 360]
result = engine.inspect(image_point)

print(result["reference"])  # calibrated reference coordinates
print(result["grid_cell"])  # {"row": .., "column": .., "coordinate": [col, row]}
print(engine.zone_for_image_point(image_point))  # e.g. "C4"
```

## Quick start — HTTP client

```python
from spe import SPEClient

with SPEClient("http://127.0.0.1:5000") as client:
    print(client.health())
    print(client.list_models())

    source = client.create_source("frame.jpg", source_type="image")
    calibration = client.calibrate(
        [[180, 120], [1090, 150], [1180, 640], [90, 660]],
        source_width=1280,
        source_height=720,
    )
    inspection = client.inspect_point(
        [640, 360],
        calibration=calibration["calibration"],
        grid={"rows": 4, "columns": 6},
        source_dimensions={"width": 1280, "height": 720},
    )
    print(inspection)
```

## Quick start — async client

`AsyncSPEClient` mirrors `SPEClient` with the same method names, each exposed as
a coroutine. It offloads the blocking transport to a worker thread, so it adds
no dependencies and is safe to `await` inside an event loop.

```python
import asyncio

from spe import AsyncSPEClient


async def main() -> None:
    async with AsyncSPEClient("http://127.0.0.1:5000") as client:
        print(await client.health())
        models = await client.list_models()
        print(models)
        await client.set_grid(rows=4, columns=6)


asyncio.run(main())
```

## Quick start — command line

```bash
spe health
spe --url http://127.0.0.1:5000 models
spe state
spe calibrate --size 1280x720 --points 180,120 1090,150 1180,640 90,660
spe inspect --x 640 --y 360 --calibration calibration.json --size 1280x720
spe --version
```

`spe` is installed as a console script; `python -m spe ...` works too. See the
[CLI reference](https://github.com/kgosietsileRM/spe_sdk/blob/main/docs/index.md#command-line) for every option.

## Configuration

Both clients accept the same connection options:

```python
from spe import SPEClient, get_default_transport

client = SPEClient(
    "http://127.0.0.1:5000",
    timeout=30.0,  # per-request timeout, seconds
    retries=2,  # retries for idempotent requests on connection loss or 429/5xx
    backoff=0.5,  # base backoff, doubles each retry (or the Retry-After value)
    user_agent="my-app/1.0",  # optional User-Agent header
    api_key="...",  # optional X-API-Key header
    token="...",  # optional Authorization: Bearer token
    headers={"X-Trace": "abc"},  # extra headers on every request
    transport=get_default_transport("urllib"),  # force a transport backend
)
```

Read the base URL (and optional credentials) from the environment with
`from_env` (default variable `SPE_API_URL`, falling back to
`http://127.0.0.1:5000`; also reads `SPE_API_KEY` and `SPE_API_TOKEN`):

```python
from spe import SPEClient, AsyncSPEClient

client = SPEClient.from_env()
async_client = AsyncSPEClient.from_env("SPE_API_URL")
```

## Spatial model

SPE keeps three coordinate systems distinct:

1. **Image coordinates** — pixels, origin at the top-left.
2. **Spatial / reference coordinates** — a calibrated, application-defined plane
   (normalized `1000 x 600` by default; optional physical units).
3. **Virtual grid coordinates** — logical cells and semantic zones over the plane.

A four-point calibration computes the homography that maps image coordinates to
the reference plane; its inverse maps back. Units stay `normalized` unless you
explicitly request physical dimensions — the SDK never fabricates physical scale.
Grid cells are zero-based and exposed as `(column, row)`; zones use
spreadsheet-style ids such as `A1`, `B3`, and `AA2`.

## Error handling

All errors derive from `SPEError`:

| Exception | Meaning |
| --- | --- |
| `SPEError` | Base class for every error raised by the SDK. |
| `SPEValidationError` | Invalid geometry or parameters (also a `ValueError`). |
| `SPEEngineError` | Local processing cannot complete (also a `RuntimeError`). |
| `SPEModelUnavailableError` | A perception model has no usable runtime. |
| `SPETransportError` | Base class for HTTP transport failures (also a `RuntimeError`). |
| `SPEConnectionError` | The server cannot be reached. |
| `SPETimeoutError` | A request exceeded its timeout. |
| `SPEAPIError` | The server returned an error (`.status_code`, `.payload`, `.url`, `.retry_after`). |
| `SPEBadRequestError` | HTTP 400: invalid request payload. |
| `SPEAuthenticationError` | HTTP 401/403: missing or rejected credentials. |
| `SPENotFoundError` | HTTP 404: the resource does not exist. |
| `SPEConflictError` | HTTP 409: the server state rejected the request. |
| `SPERateLimitError` | HTTP 429: the client is being throttled. |
| `SPEServerError` | HTTP 5xx: a server-side failure. |

The status-specific errors subclass `SPEAPIError`, so existing
`except SPEAPIError` handlers keep working.

```python
from spe import SPEClient, SPEAPIError, SPEError

try:
    with SPEClient("http://127.0.0.1:5000") as client:
        client.get_source("missing")
except SPEAPIError as error:
    print(error.status_code, error.payload)
except SPEError as error:  # catch-all for the whole SDK
    print("SPE error:", error)
```

## Examples

Runnable scripts live under [`examples/`](https://github.com/kgosietsileRM/spe_sdk/tree/main/examples):

| Script | Shows |
| --- | --- |
| [`local_calibration.py`](https://github.com/kgosietsileRM/spe_sdk/blob/main/examples/local_calibration.py) | In-process calibration, inspection, zones, and state round-tripping. |
| [`detect_and_spatialize.py`](https://github.com/kgosietsileRM/spe_sdk/blob/main/examples/detect_and_spatialize.py) | Enriching provider-neutral detections with calibrated spatial data. |
| [`retail_zone_analytics.py`](https://github.com/kgosietsileRM/spe_sdk/blob/main/examples/retail_zone_analytics.py) | Per-zone occupancy, unique visitors, and dwell time from a frame sequence. |
| [`security_intrusion_detection.py`](https://github.com/kgosietsileRM/spe_sdk/blob/main/examples/security_intrusion_detection.py) | Alerting when a person's ground point enters a restricted polygon. |
| [`warehouse_grid_inventory.py`](https://github.com/kgosietsileRM/spe_sdk/blob/main/examples/warehouse_grid_inventory.py) | Bay occupancy map, empty-bay list, and fill ratio from pallet detections. |
| [`traffic_lane_speed.py`](https://github.com/kgosietsileRM/spe_sdk/blob/main/examples/traffic_lane_speed.py) | A metric reference plane (`units="meters"`) for lane assignment and speed. |
| [`annotated_overlay.py`](https://github.com/kgosietsileRM/spe_sdk/blob/main/examples/annotated_overlay.py) | Rendering the calibrated grid plus zone-labelled boxes to a PNG. |
| [`tracking_and_motion.py`](https://github.com/kgosietsileRM/spe_sdk/blob/main/examples/tracking_and_motion.py) | Stable track ids, per-track speed, and next-position prediction. |
| [`analytics_pipeline.py`](https://github.com/kgosietsileRM/spe_sdk/blob/main/examples/analytics_pipeline.py) | Zone occupancy, track summaries, line crossings, and observation persistence. |
| [`http_client.py`](https://github.com/kgosietsileRM/spe_sdk/blob/main/examples/http_client.py) | Talking to a running engine with the synchronous client. |
| [`async_client.py`](https://github.com/kgosietsileRM/spe_sdk/blob/main/examples/async_client.py) | The asyncio client (`AsyncSPEClient`). |
| [`http_analysis_session.py`](https://github.com/kgosietsileRM/spe_sdk/blob/main/examples/http_analysis_session.py) | A full server analysis session: health, source, frames, complete. |
| [`stream_video.py`](https://github.com/kgosietsileRM/spe_sdk/blob/main/examples/stream_video.py) | Streaming video frames into the detection endpoint with OpenCV. |

## API overview

The full, exhaustive reference is in [`docs/index.md`](https://github.com/kgosietsileRM/spe_sdk/blob/main/docs/index.md). At a glance:

| Surface | Key symbols |
| --- | --- |
| Local facade | `SpatialEngine` |
| HTTP clients | `SPEClient`, `AsyncSPEClient` |
| Uploads | `FileSource` (bytes, path, or binary stream) |
| Transports | `Transport`, `UrllibTransport`, `RequestsTransport`, `HttpxTransport`, `get_default_transport` |
| Value objects | `BoundingBox`, `Detection`, `ReferencePlane`, `GridCell`, `Zone`, `Calibration`, `ModelDescriptor` |
| Geometry | `calculate_calibration`, `calculate_homography`, `transform_points`, `inverse_homography`, `validate_homography`, `validate_source_points`, `reprojection_error`, `warp_image`, `REFERENCE_WIDTH`, `REFERENCE_HEIGHT`, `POINT_ORDER` |
| Spatial | `inspect_point`, `image_to_spatial`, `point_in_roi`, `spatial_point_to_grid_cell`, `spatialize_detection`, `spatialize_detection_result` |
| Rendering | `GridConfig`, `generate_grid`, `generate_calibrated_grid` |
| Inference | `InferenceContext`, `resolve_inference_context` |
| Zones | `row_label`, `generate_zones`, `zone_for_cell` |
| Tracking | `ModelAgnosticTracker`, `TrackingConfig` |
| Motion | `SpatialTrackStateManager`, `MotionConfig` |
| Analytics | `ZoneOccupancyTracker`, `LineCrossingCounter`, `TrackSummary`, `summarize_tracks` |
| Observations | `create_observation`, `create_image_observation`, `ObservationBatchWriter` |
| Errors | `SPEError`, `SPEValidationError`, `SPEEngineError`, `SPEModelUnavailableError`, `SPETransportError`, `SPEConnectionError`, `SPETimeoutError`, `SPEAPIError`, `SPEBadRequestError`, `SPEAuthenticationError`, `SPENotFoundError`, `SPEConflictError`, `SPERateLimitError`, `SPEServerError` |

## Development

```bash
pip install -e ".[dev]"

ruff check .          # lint
ruff format --check . # formatting
mypy                  # types (config in pyproject.toml)
pytest --cov=spe      # tests + coverage
```

The suite covers geometry, inspection, zones, tracking, motion, observations, the
engine facade, value objects, the sync and async HTTP clients (against a local mock
server), the transports, and the CLI. Linting, formatting, and strict type checking
all pass, with line coverage held at ~99%. See
[`CONTRIBUTING.md`](https://github.com/kgosietsileRM/spe_sdk/blob/main/CONTRIBUTING.md) for the quality
gates and conventions.

### Package layout

```text
src/spe/
├── __init__.py       # public API surface
├── __main__.py       # `python -m spe`
├── engine.py         # SpatialEngine — stateful local facade
├── client.py         # SPEClient — stdlib HTTP client
├── aio.py            # AsyncSPEClient — asyncio wrapper
├── transport.py      # Transport protocol + urllib/requests/httpx backends
├── geometry.py       # homography + four-point calibration
├── spatial.py        # inspection + detection spatialization
├── grid.py           # image-space & calibrated grid rendering
├── zones.py          # semantic zone identifiers
├── tracking.py       # provider-neutral multi-object tracking
├── motion.py         # trajectories, velocity, direction & prediction
├── observations.py   # provider-neutral observation builders
├── models.py         # typed value objects
├── exceptions.py     # SPE error hierarchy
├── _version.py       # single source of truth for the version
└── cli.py            # `spe` command-line interface
```

## Releasing

1. Bump `__version__` in `src/spe/_version.py`.
2. Move the `Unreleased` entries in [`CHANGELOG.md`](https://github.com/kgosietsileRM/spe_sdk/blob/main/CHANGELOG.md) under the new version.
3. Tag and push (`git tag v0.1.1 && git push origin v0.1.1`); the release
   workflow builds, checks, and publishes to PyPI.

## Contributing

Contributions are welcome — see [`CONTRIBUTING.md`](https://github.com/kgosietsileRM/spe_sdk/blob/main/CONTRIBUTING.md).

## License

MIT © Peach LLC. See [`LICENSE`](https://github.com/kgosietsileRM/spe_sdk/blob/main/LICENSE).
