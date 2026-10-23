# SPE SDK documentation

Complete reference for the `spe-sdk` Python package. For a shorter overview and
quick-start examples, see the [README](../README.md).

## Contents

- [Installation](#installation)
- [Architecture](#architecture)
- [Type aliases and version](#type-aliases-and-version)
- [Coordinate contract](#coordinate-contract)
- [`SpatialEngine`](#spatialengine)
- [Value objects](#value-objects)
- [Geometry reference](#geometry-reference)
- [Spatial reference](#spatial-reference)
- [Grid reference](#grid-reference)
- [Zones reference](#zones-reference)
- [Tracking, motion and observations](#tracking-motion-and-observations)
- [`SPEClient`](#speclient)
- [`AsyncSPEClient`](#asyncspeclient)
- [Transports](#transports)
- [Command line](#command-line)
- [Exceptions](#exceptions)
- [Development](#development)

## Installation

```bash
pip install -e .                 # from the repository root
pip install -e ".[http]"         # + the optional httpx transport
pip install -e ".[dev]"          # + pytest, pytest-cov, ruff, mypy, build, twine
pip install -e ".[docs]"         # + mkdocs, mkdocs-material, mkdocstrings
```

Runtime dependencies are `numpy >= 1.24` and `opencv-python-headless >= 4.8`. The HTTP
clients use only the standard library unless you opt into the `httpx` transport.

Supported Python versions: **3.10, 3.11, 3.12, 3.13, 3.14**.

## Architecture

The SDK exposes two independent surfaces that share one coordinate contract:

| Module | Role |
| --- | --- |
| `spe.engine` | `SpatialEngine` — stateful, in-process facade. |
| `spe.geometry` | Homography math and four-point calibration (OpenCV/NumPy). |
| `spe.spatial` | Point inspection and detection spatialization primitives. |
| `spe.grid` | Image-space and calibrated grid rendering. |
| `spe.zones` | Deterministic semantic zone identifiers. |
| `spe.tracking` | Provider-neutral multi-object association (`ModelAgnosticTracker`). |
| `spe.motion` | Bounded trajectories, velocity, direction, and prediction. |
| `spe.observations` | Provider-neutral timestamped observation builders. |
| `spe.models` | Typed value objects over the JSON contracts. |
| `spe.client` | `SPEClient` — synchronous HTTP client for a running engine. |
| `spe.aio` | `AsyncSPEClient` — asyncio wrapper around `SPEClient`. |
| `spe.transport` | Pluggable HTTP transports (`urllib`, `requests`, `httpx`). |
| `spe.exceptions` | The `SPEError` hierarchy. |
| `spe.cli` | The `spe` command-line interface. |

The **local core** (`SpatialEngine` plus the free functions) performs all
geometry in-process and never needs a server. The **HTTP client** speaks to a
running SPE engine server and mirrors the same spatial model.

## Type aliases and version

- `spe.__version__` — the installed SDK version string (also printed by
  `spe --version`).
- `FileSource` — the accepted input type for uploads:
  `bytes | bytearray | memoryview | str | os.PathLike | BinaryIO`. A `str` or
  `os.PathLike` is read from disk; bytes-like values are sent as-is; any object
  with a callable `read` is read as a binary stream.

## Coordinate contract

Three coordinate systems are kept distinct:

1. **Image coordinates** — source pixels, `(x, y)`, origin at the top-left.
   Exposed with `coordinate_system: "image_pixels"` (or `"source_pixels"` for
   model detections).
2. **Reference coordinates** — the calibrated plane, default `1000 x 600`,
   `units: "normalized"`. Exposed with
   `coordinate_system: "calibrated_reference_plane"`. Physical units are only
   reported when the calibration was created with non-`normalized` `units`; the
   SDK never invents a physical scale.
3. **Grid coordinates** — logical cells over the reference plane, plus semantic
   zones.

Calibration uses exactly four points in **`TL, TR, BR, BL`** order —
`top_left, top_right, bottom_right, bottom_left`. Points must form a
non-degenerate, non-self-intersecting quadrilateral inside the source frame.

A four-point calibration computes a `3 x 3` homography mapping image → reference
(`homography`) and its inverse reference → image (`inverse_homography`).

**Grid cells** are zero-based `row`/`column` indices, exposed both as a
`GridCell` and as a `coordinate` list in `(column, row)` order. **Zones** are
human-readable ids built from a spreadsheet-style row label and a one-based
column: `A1`, `B3`, `AA2`, ...

## `SpatialEngine`

`spe.engine.SpatialEngine` is a stateful local facade bundling a calibration, a
calibrated grid size, and optional source dimensions.

```python
from spe import SpatialEngine

engine = SpatialEngine(
    grid_rows=4,  # default 3
    grid_columns=6,  # default 3
    source_dimensions={"width": 1280, "height": 720},  # optional
    calibration=None,  # optional pre-built Calibration or mapping
)
```

### Constructor

```python
SpatialEngine(
    *,
    calibration: Calibration | Mapping[str, Any] | None = None,
    grid_rows: int = 3,
    grid_columns: int = 3,
    source_dimensions: Mapping[str, Any] | None = None,
) -> None
```

When `calibration` is supplied, its `rows`/`columns` override `grid_rows`/
`grid_columns`.

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| `grid_rows` | `int` | Calibrated grid row count. |
| `grid_columns` | `int` | Calibrated grid column count. |
| `source_dimensions` | `dict \| None` | `{"width": ..., "height": ...}`. |
| `calibration` | `Calibration \| None` | The installed calibration, if any. |

### State methods

#### `calibrate`

```python
calibrate(
    source_points: Sequence[Sequence[float]],
    source_width: int,
    source_height: int,
    *,
    reference_plane: ReferencePlane | None = None,
    rows: int | None = None,
    columns: int | None = None,
) -> Calibration
```

Validates four `TL, TR, BR, BL` points and installs a reusable calibration.
`rows`/`columns` default to the engine's current grid size. Updates
`source_dimensions` and returns the new `Calibration`.

Raises `SPEValidationError` for invalid geometry, or when the resolved grid rows
or columns are not positive.

#### `load_calibration`

```python
load_calibration(data: Calibration | Mapping[str, Any]) -> Calibration
```

Installs a previously serialized calibration and adopts its grid size.

#### `clear_calibration`

```python
clear_calibration() -> None
```

Removes the installed calibration.

#### `is_calibrated` (property)

`True` when a calibration with a homography is installed.

### Transform methods

These require a calibration and raise `SPEEngineError` when the engine is not
calibrated.

| Method | Returns |
| --- | --- |
| `image_to_reference(points)` | `list[list[float]]` — image points in reference coordinates. |
| `reference_to_image(points)` | `list[list[float]]` — reference points in image coordinates. |
| `cell_for_reference_point(point)` | `GridCell \| None`. |
| `zone_for_reference_point(point)` | `str \| None`. |
| `cell_for_image_point(point)` | `GridCell \| None`. |
| `zone_for_image_point(point)` | `str \| None`. |
| `zones()` | `list[Zone]` for the configured grid. |

### Inspection

#### `spatial_state`

```python
spatial_state() -> dict[str, Any]
```

Returns the canonical state contract consumed by `inspect_point`:

```python
{
    "calibration": {...},  # Calibration.to_dict()
    "grid": {"rows": 4, "columns": 6},
    "source_dimensions": {"width": 1280, "height": 720},  # when known
}
```

#### `inspect`

```python
inspect(image_point: Sequence[float]) -> dict[str, Any]
```

Inspects one image-space point against the installed state. See
[`inspect_point`](#inspect_point) for the returned shape.

### Spatialization

| Method | Description |
| --- | --- |
| `spatialize_detection(detection)` | Enrich one detection mapping with spatial data. |
| `spatialize_result(result)` | Enrich a normalized `{"detections": [...]}` result. |
| `spatialize(detections)` | Enrich a sequence of detection mappings, returning a list. |

These require a calibration and raise `SPEEngineError` when uncalibrated. The
per-detection payload matches [`spatialize_detection`](#spatialize_detection).

### Rendering

#### `render_grid`

```python
render_grid(
    image: np.ndarray,
    *,
    rows: int = 8,
    columns: int = 12,
    line_thickness: int = 1,
    line_color: tuple[int, int, int] = (91, 243, 168),
    show_coordinates: bool = True,
) -> tuple[np.ndarray, dict]
```

Draws a regular image-space grid on a copy of `image`. This does not require a
calibration. See [`generate_grid`](#generate_grid).

#### `render_calibrated_grid`

```python
render_calibrated_grid(
    image: np.ndarray,
    *,
    show_grid: bool = True,
    show_roi: bool = True,
    line_color: tuple[int, int, int] = (91, 243, 168),
    roi_color: tuple[int, int, int] = (48, 59, 255),
    overlay_only: bool = False,
) -> tuple[np.ndarray, dict]
```

Renders the calibrated grid, projected back into image space through the inverse
homography. Requires a calibration (raises `SPEEngineError` otherwise). See
[`generate_calibrated_grid`](#generate_calibrated_grid).

### Persistence

#### `to_dict`

```python
to_dict() -> dict[str, Any]
```

```python
{
    "grid_rows": 4,
    "grid_columns": 6,
    "source_dimensions": {"width": 1280, "height": 720},
    "calibration": {...} | None,
}
```

#### `from_dict` (classmethod)

```python
SpatialEngine.from_dict(data: Mapping[str, Any]) -> SpatialEngine
```

Restores an engine from `to_dict()` output.

## Value objects

All value objects live in `spe.models` and round-trip through `to_dict()` /
`from_dict()`.

### `BoundingBox`

Frozen dataclass; an axis-aligned box in source-pixel coordinates.

```python
BoundingBox(x: float, y: float, width: float, height: float)
```

Validation: `x`/`y` must be `>= 0`; `width`/`height` must be `> 0`.

| Member | Type | Description |
| --- | --- | --- |
| `x`, `y`, `width`, `height` | `float` | Box geometry. |
| `center` (property) | `dict[str, float]` | `{"x": ..., "y": ...}` box center. |
| `foot_point` (property) | `dict[str, float]` | Bottom-center `{"x": ..., "y": ...}`. |
| `to_dict()` | `dict` | `{"x", "y", "width", "height"}`. |
| `from_dict(data)` | `BoundingBox` | Classmethod. |

### `Detection`

Frozen dataclass; a single perception observation in source pixels.

```python
Detection(
    class_name: str,
    bbox: BoundingBox,
    confidence: float = 0.0,
    id: str | None = None,
    class_id: int | None = None,
    track_id: str | None = None,
    coordinate_system: str = "source_pixels",
)
```

Validation: `class_name` must be non-empty; `confidence` must be within
`[0, 1]`; `coordinate_system` must be `"source_pixels"`.

`to_dict()` returns `class_name`, `confidence`, `bbox`, `center`, `foot_point`,
`coordinate_system`, and (when set) `id`, `class_id`, `track_id`. `from_dict`
accepts `class_name` or a `label` fallback.

### `ReferencePlane`

Dataclass; the calibration target plane.

```python
ReferencePlane(width: float = 1000, height: float = 600, units: str = "normalized")
```

`from_dict(None)` yields the defaults.

### `GridCell`

Frozen dataclass.

```python
GridCell(row: int, column: int)
```

`coordinate` (property) returns `[column, row]`. `to_dict()` returns
`{"row", "column", "coordinate"}`.

### `Zone`

Frozen dataclass.

```python
Zone(id: str, row: int, column: int)
```

`to_dict()` returns `{"id", "row", "column"}`.

### `Calibration`

Dataclass; a four-point planar calibration and its reusable transforms.

**Fields**

| Field | Type | Default |
| --- | --- | --- |
| `source_points` | `list[list[float]]` | — |
| `homography` | `list[list[float]] \| None` | — |
| `inverse_homography` | `list[list[float]] \| None` | — |
| `reference_plane` | `ReferencePlane` | `ReferencePlane()` |
| `rows` | `int` | `3` |
| `columns` | `int` | `3` |
| `status` | `str` | `"calibrated"` |
| `method` | `str` | `"manual_four_point"` |
| `coordinate_system` | `str` | `"calibrated_reference_plane"` |
| `point_order` | `Sequence[str]` | `POINT_ORDER` |
| `destination_points` | `list[list[float]]` | `[]` |
| `reprojection_error` | `float` | `0.0` |
| `source_roi` | `dict` | `{}` |
| `inlier_mask` | `list[int]` | `[]` |
| `transformation` | `dict` | `{}` |

**Constructors**

| Method | Description |
| --- | --- |
| `Calibration.from_points(source_points, source_width, source_height, reference_plane=None, rows=3, columns=3)` | Compute a calibration from four points. |
| `Calibration.from_record(record, rows=None, columns=None)` | Build from a `calculate_calibration` record. |
| `Calibration.from_dict(data)` | Alias of `from_record`. |

**Serialization and transforms**

| Method | Description |
| --- | --- |
| `to_dict(*, include_grid=True)` | Serialize; `include_grid=False` omits `calibrated_grid`. |
| `require_homography()` | Return the image→reference matrix or raise `SPEValidationError`. |
| `require_inverse_homography()` | Return the reference→image matrix or raise. |
| `image_to_reference(points)` | Transform image points to reference coordinates. |
| `reference_to_image(points)` | Transform reference points to image coordinates. |
| `cell_for(reference_point)` | `GridCell \| None`. |
| `zone_for(reference_point)` | `str \| None`. |

## Geometry reference

`spe.geometry`. Constants:

| Name | Value |
| --- | --- |
| `REFERENCE_WIDTH` | `1000` |
| `REFERENCE_HEIGHT` | `600` |
| `POINT_ORDER` | `("top_left", "top_right", "bottom_right", "bottom_left")` |

### `calculate_calibration`

```python
calculate_calibration(
    points, width, height,
    reference_width=REFERENCE_WIDTH,
    reference_height=REFERENCE_HEIGHT,
    units="normalized",
) -> dict
```

Validates four `TL, TR, BR, BL` points and returns a calibration record:

```python
{
    "status": "calibrated",
    "method": "manual_four_point",
    "coordinate_system": "calibrated_reference_plane",
    "point_order": ["top_left", "top_right", "bottom_right", "bottom_left"],
    "source_points": [[x, y], ...],
    "destination_points": [[x, y], ...],
    "reference_plane": {"width": ..., "height": ..., "units": ...},
    "roi": {"status": "active", "type": "calibrated_planar_region"},
    "homography": [[...], [...], [...]],
    "inverse_homography": [[...], [...], [...]],
    "reprojection_error": 0.0,
    "source_roi": {"area_px": ..., "area_percent": ...},
    "transformation": {"direction": "image_to_calibrated_reference_plane", "reusable": True},
    "inlier_mask": [...],
}
```

Raises `SPEValidationError` for invalid points, source dimensions, reference
dimensions, or units.

### `calculate_homography`

```python
calculate_homography(source_points, destination_points) -> tuple[np.ndarray, np.ndarray]
```

Returns the `3 x 3` matrix and the per-point inlier mask (both NumPy arrays).
Requires exactly four points per side.

### `validate_homography`

```python
validate_homography(homography) -> np.ndarray
```

Returns a finite, invertible `3 x 3` matrix as `float64`, else raises
`SPEValidationError`.

### `transform_points`

```python
transform_points(points, homography) -> list[list[float]]
```

Transforms one point or many through `homography`. Non-finite results raise
`SPEValidationError`.

### `inverse_homography`

```python
inverse_homography(homography) -> np.ndarray
```

Returns the inverse matrix normalized so that its `[2, 2]` element is `1`.

### `reprojection_error`

```python
reprojection_error(source_points, destination_points, homography) -> float
```

Mean Euclidean destination-space error of the transformed source points.

### `warp_image`

```python
warp_image(image: np.ndarray, homography, width: int, height: int) -> np.ndarray
```

Warps an image into the reference plane using `INTER_LINEAR`. Requires a
non-empty image and integer dimensions `> 1`.

### `validate_source_points`

```python
validate_source_points(points, width, height) -> np.ndarray
```

Validates `TL, TR, BR, BL` points against `width x height` (inside-frame,
non-duplicate, convex, non-degenerate) and returns `float32` coordinates.

## Spatial reference

`spe.spatial`.

### `point_in_roi`

```python
point_in_roi(image_point, source_points) -> bool
```

`True` when the point is inside or on the four-point ROI.

### `image_to_spatial`

```python
image_to_spatial(image_point, calibration) -> dict
```

Maps one image point through an existing calibration record:

```python
{
    "x": ...,
    "y": ...,
    "coordinate_system": "calibrated_reference_plane",
    "units": "normalized",
    "width": ...,
    "height": ...,
}
```

### `spatial_point_to_grid_cell`

```python
spatial_point_to_grid_cell(spatial_point, rows, columns, width, height) -> dict | None
```

Returns `{"row": ..., "column": ..., "coordinate": [column, row]}` or `None`
when the point lies outside the plane. Boundary points clamp to the edge cell.

### `inspect_point`

```python
inspect_point(image_point, spatial_state) -> dict
```

Inspects a point using the canonical state contract produced by
`SpatialEngine.spatial_state()`.

- Invalid input returns status `"invalid"` with a `reason` of
  `"point_outside_image"` or `"calibration_unavailable"`.
- A point outside the ROI returns status `"outside_roi"` with `image`, `roi`,
  `reference: None`, `physical`, and `grid_cell: None`.
- A valid point returns status `"valid"` and adds `reference`, `grid_cell`, and
  (only when the units are not `normalized`) a populated `physical` block.

### `spatialize_detection`

```python
spatialize_detection(detection, calibration, roi=None, grid=None) -> dict
```

Adds calibrated spatial data to one detection mapping without mutating its
source-pixel fields. The ground point is the bottom-center (`foot_point`) of the
bounding box. Returns:

```python
{
    "status": "valid" | "outside_roi" | "unavailable",
    "ground_point": {"x", "y", "coordinate_system": "source_pixels", "units": "px"},
    "position": {"x", "y", "coordinate_system", "units"} | None,
    "grid_cell": {"row", "column", "coordinate"} | None,
    "zone": "C4" | None,
    "in_roi": bool | None,
    "coordinate_system": "calibrated_reference_plane",
    "units": str | None,
    "reason": "invalid_bbox" | "calibration_unavailable" | "roi_unavailable" | "invalid_roi" | "spatialization_error",
}
```

`reason` is present only on unavailable results.

### `spatialize_detection_result`

```python
spatialize_detection_result(result, calibration, roi=None, grid=None) -> dict
```

Returns a copy of `result` with each entry in `detections` enriched under a
`"spatial"` key.

Two aliases are defined in the module: `is_point_in_spatial_roi` (=
`point_in_roi`) and `point_to_grid_cell` (= `spatial_point_to_grid_cell`).

## Grid reference

`spe.grid`.

### `GridConfig`

Frozen dataclass configuring an image-space grid.

```python
GridConfig(
    rows: int = 8,
    columns: int = 12,
    line_thickness: int = 1,        # must be 1..12
    show_coordinates: bool = True,
    line_color: tuple[int, int, int] = (91, 243, 168),  # 0..255 each
)
```

### `generate_grid`

```python
generate_grid(image: np.ndarray, config: GridConfig | None = None) -> tuple[np.ndarray, dict]
```

Draws a regular grid on a copy of `image`. The metadata dict reports the source
size, grid geometry, `coordinate_system: "image"`, and
`status: "grid generated"`.

### `generate_calibrated_grid`

```python
generate_calibrated_grid(
    image, homography,
    rows=4, columns=6,
    reference_width=1000, reference_height=600,
    source_points=None,
    show_grid=True, show_roi=True,
    line_color=(91, 243, 168), roi_color=(48, 59, 255),
    overlay_only=False,
) -> tuple[np.ndarray, dict]
```

Projects reference-plane grid lines back into image space through the inverse
homography. When `overlay_only` is `True`, the returned image is a 4-channel
transparent overlay. Metadata reports the grid geometry, `show_grid`/`show_roi`/
`overlay_only`, the source size, `coordinate_system:
"calibrated_reference_plane"`, and `status: "calibrated grid generated"`.

## Zones reference

`spe.zones`.

### `row_label`

```python
row_label(index: int) -> str
```

Spreadsheet-style row label: `A..Z, AA, AB, ...`. Rejects negative or
non-integer input with `SPEValidationError`.

### `generate_zones`

```python
generate_zones(rows: int, columns: int) -> list[dict]
```

Returns every zone in row-major order, each `{"id", "row", "column"}`.

### `zone_for_cell`

```python
zone_for_cell(cell: dict | None, rows: int, columns: int) -> str | None
```

Returns the zone id for a grid-cell dict, or `None` when unknown.

## Tracking, motion and observations

`spe.tracking`, `spe.motion`, and `spe.observations` mirror the engine's temporal
layer. They are pure and in-process: they operate on normalized detection
mappings and never touch images or a server.

### `TrackingConfig`

```python
TrackingConfig(
    min_iou: float = 0.01,
    max_center_distance_scale: float = 2.5,
    max_missing_seconds: float = 1.5,
    confirmation_observations: int = 2,
)
```

Association thresholds in source-pixel units and seconds.

### `ModelAgnosticTracker`

```python
ModelAgnosticTracker(config: TrackingConfig | None = None)
tracker.update(detections, timestamp=None) -> {"detections": [...], "diagnostics": {...}}
tracker.snapshot() -> dict
tracker.reset() -> None
```

`update` assigns stable `track-<n>` ids to detections while rejecting duplicate
and out-of-order timestamps without mutating state. Diagnostics include
`active_tracks`, `tracks_created`, `tracks_terminated`, `matched_detections`,
and related counters.

### `MotionConfig`

```python
MotionConfig(
    max_trajectory_samples: int = 32,
    max_velocity_gap_seconds: float = 2.0,
    prediction_horizon_seconds: float = 0.5,
    max_prediction_horizon_seconds: float = 2.0,
    max_prediction_age_seconds: float = 1.5,
    max_tracks: int = 256,
)
```

### `SpatialTrackStateManager`

```python
SpatialTrackStateManager(config: MotionConfig | None = None)
manager.update(detections, timestamp, prediction_enabled=False) -> dict
manager.snapshot(timestamp=None, prediction_enabled=False) -> dict
manager.reset() -> None
```

Prefers a valid detection `spatial.position` (keeping its coordinate system and
units) and otherwise falls back to the bounding-box foot point in source
pixels. Velocity is a finite difference over the last two samples; predictions
are only produced when enabled and the track is fresh.

### `create_observation`

```python
create_observation(
    detection_result,
    *,
    analysis_id: str,
    source_id: str,
    timestamp: float,
    frame_index: int,
) -> dict
```

Builds a timestamped, provider-neutral observation without frame data,
preserving calibrated `spatial` data and `track_id` when present. The SDK does
not persist observations; store the returned dict however you prefer.

### `create_image_observation`

```python
create_image_observation(detection_result, *, source_id: str) -> dict
```

Wraps one static-image detection result with source context.

## `SPEClient`

`spe.client.SPEClient` is a thin, typed client for a running SPE engine server.
It is a context manager.

```python
from spe import SPEClient

with SPEClient("http://127.0.0.1:5000") as client:
    client.health()
```

### Constructor

```python
SPEClient(
    base_url: str = "http://127.0.0.1:5000",
    *,
    timeout: float = 30.0,
    retries: int = 2,
    backoff: float = 0.5,
    user_agent: str | None = None,
    transport: Transport | None = None,
) -> None
```

| Argument | Description |
| --- | --- |
| `base_url` | Root URL of the server; must be a non-empty string. |
| `timeout` | Per-request timeout in seconds. |
| `retries` | Automatic retries for idempotent requests on connection loss. |
| `backoff` | Base backoff delay (seconds); doubles each retry. |
| `user_agent` | Optional `User-Agent` header. |
| `transport` | Custom `Transport`; defaults to the best available backend. |

Raises `SPEValidationError` when `base_url` is empty or not a string.

### Lifecycle

| Member | Description |
| --- | --- |
| `base_url` | Normalized base URL (no trailing slash). |
| `__enter__` / `__exit__` | Context-manager protocol. |
| `close()` | Release transport resources. |
| `SPEClient.from_env(variable="SPE_API_URL", **kwargs)` | Build from an environment variable. |

### Health and state

| Method | Route | Returns |
| --- | --- | --- |
| `health()` | `GET /health` | Raw payload. |
| `get_state()` | `GET /api/state` | Raw payload. |

### Sources

| Method | Route | Returns |
| --- | --- | --- |
| `create_source(source, *, filename=None, source_type="image", mime_type=None)` | `POST /api/sources` | `response["source"]`. |
| `get_source(source_id)` | `GET /api/sources/{id}` | `response["source"]`. |
| `delete_source(source_id)` | `DELETE /api/sources/{id}` | `None`. |
| `source_media_url(source_id)` | — | Absolute media URL string. |
| `get_source_media(source_id)` | `GET /api/sources/{id}/media` | Raw `bytes`. |

`source` may be `bytes`, `bytearray`, `memoryview`, `str`/`os.PathLike` path, or
a binary file object.

### Calibration

| Method | Route |
| --- | --- |
| `calibrate(source_points, source_width, source_height, *, reference_width=1000, reference_height=600, units="normalized", rows=3, columns=3)` | `POST /api/calibration` |
| `get_calibration()` | `GET /api/calibration` → `response["calibration"]` |
| `update_calibration(...)` (same signature as `calibrate`) | `PUT /api/calibration` |
| `delete_calibration()` | `DELETE /api/calibration` |

### ROI and grid

| Method | Route | Returns |
| --- | --- | --- |
| `get_roi()` | `GET /api/roi` | `response["roi"]`. |
| `create_roi(points)` | `POST /api/roi` | `response["roi"]`. |
| `update_roi(points)` | `PUT /api/roi` | `response["roi"]`. |
| `delete_roi()` | `DELETE /api/roi` | `None`. |
| `get_grid()` | `GET /api/grid` | `response["grid"]`. |
| `set_grid(rows, columns)` | `PUT /api/grid` | `response["grid"]`. |
| `delete_grid()` | `DELETE /api/grid` | `None`. |

### Spatial queries

#### `transform_points`

```python
transform_points(
    points,
    *,
    homography=None,
    calibration=None,
    direction="image_to_reference",
) -> dict
```

Posts to `POST /api/calibration/transform`. Provide a `homography` or a
`calibration` mapping.

#### `inspect_point`

```python
inspect_point(
    point=None,
    *,
    x=None, y=None,
    calibration=None,
    grid=None,
    source_dimensions=None,
    spatial_state=None,
) -> dict
```

Posts to `POST /api/spatial/inspect-point`. Supply either `point` or both `x`
and `y` (otherwise `SPEValidationError`). When `spatial_state` is given it is
used directly; otherwise `calibration`/`grid`/`source_dimensions` are sent.

### Rendering

| Method | Route |
| --- | --- |
| `generate_grid(image, *, filename=None, rows=8, columns=12, line_thickness=1, line_color="#a8f35b", show_coordinates=True, source_type="image", fps=None, frame_count=None)` | `POST /api/grid` |
| `generate_calibrated_grid(image, homography, *, filename=None, rows=4, columns=6, reference_width=1000, reference_height=600, source_points=None, show_grid=True, show_roi=True, line_color="#a8f35b", roi_color="#ff3b30", overlay_only=False)` | `POST /api/calibrated-grid` |
| `video_metadata(video, *, filename=None)` | `POST /api/video/metadata` |

The rendering methods return `{"image": ..., "metadata": {...}}`.

### Models

| Method | Route | Returns |
| --- | --- | --- |
| `list_models()` | `GET /api/models` | `response["models"]`. |
| `get_model(model_id)` | `GET /api/models/{id}` | `response["model"]`. |
| `model_status(model_id)` | `GET /api/models/{id}/status` | Raw payload. |
| `load_model(model_id)` | `POST /api/models/{id}/load` | Raw payload. |
| `unload_model(model_id)` | `POST /api/models/{id}/unload` | Raw payload. |
| `model_classes(model_id)` | `GET /api/models/{id}/classes` | `response["classes"]`. |

### Analysis

#### `detect`

```python
detect(*, model_id="model-a", confidence=0.4, classes=None, source_id=None) -> dict
```

`POST /api/analysis/detect`.

#### `detect_frame`

```python
detect_frame(
    frame,
    *,
    filename="frame.jpg",
    model_id="model-a",
    confidence=0.4,
    classes=None,
    analysis_id="analysis",
    source_id="source",
    timestamp=0.0,
    frame_index=0,
    tracking=False,
    tracking_mode=None,
    target_track_id=None,
    target_detection=None,
    inference_context=None,
    spatial_context=None,
    interval_ms=None,
    effective_fps=None,
) -> dict
```

`POST /api/analysis/detect-frame`. Detects and (optionally) tracks, spatializes,
and timestamps a single frame.

#### Session methods

| Method | Route | Returns |
| --- | --- | --- |
| `start_analysis_session(analysis_id, source_id, model, *, spatial_context=None)` | `POST /api/analysis/session/start` | `response["analysis"]`. |
| `update_analysis_status(analysis_id, status="running", *, inference_fps=None, interval_ms=None)` | `PATCH /api/analysis/session/status` | `response["analysis"]`. |
| `complete_analysis_session(analysis_id, status="complete")` | `POST /api/analysis/session/complete` | Raw payload. |

## `AsyncSPEClient`

`spe.aio.AsyncSPEClient` mirrors `SPEClient`. Every method is a coroutine; the
synchronous client runs in a worker thread (`asyncio.to_thread`).

```python
import asyncio
from spe import AsyncSPEClient


async def main() -> None:
    async with AsyncSPEClient("http://127.0.0.1:5000") as client:
        await client.health()


asyncio.run(main())
```

Constructor arguments are forwarded verbatim to `SPEClient`. Additional members:

| Member | Description |
| --- | --- |
| `async __aenter__` / `__aexit__` | Async context manager. |
| `await aclose()` | Close the underlying client. |
| `AsyncSPEClient.from_env(variable="SPE_API_URL", **kwargs)` | Build from an environment variable. |
| `base_url` (property) | The underlying base URL. |

Async methods (all coroutines; signatures match `SPEClient`):

`health`, `get_state`, `create_source`, `get_source`, `delete_source`,
`source_media_url` (sync), `get_source_media`, `calibrate`, `get_calibration`,
`update_calibration`, `delete_calibration`, `get_roi`, `create_roi`,
`delete_roi`, `get_grid`, `set_grid`, `delete_grid`, `transform_points`,
`inspect_point`, `generate_grid`, `generate_calibrated_grid`, `video_metadata`,
`list_models`, `get_model`, `model_status`, `load_model`, `unload_model`,
`model_classes`, `detect`, `detect_frame`, `start_analysis_session`,
`update_analysis_status`, `complete_analysis_session`.

## Transports

`spe.transport`. A transport performs exactly **one** request and never retries;
retries, timeouts, and error mapping live in the client. Transport-level
failures are raised as `SPEConnectionError` or `SPETimeoutError`.

### `Transport` (protocol)

```python
class Transport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        data: bytes | None,
        timeout: float,
    ) -> tuple[int, Mapping[str, str], bytes]: ...
    def close(self) -> None: ...
```

### Backends

| Class | Backing library | Notes |
| --- | --- | --- |
| `UrllibTransport` | standard library `urllib.request` | Default; zero dependencies. |
| `RequestsTransport` | `requests` | Used when installed (not exported at package top level). |
| `HttpxTransport` | `httpx` | Preferred when installed (not exported at package top level). |

### `get_default_transport`

```python
get_default_transport(prefer: str | None = None) -> Transport
```

With `prefer=None`, returns `HttpxTransport` if `httpx` is importable, then
`RequestsTransport` if `requests` is importable, otherwise `UrllibTransport`.
Pass `"urllib"`, `"requests"`, or `"httpx"` to force a backend; an unknown name
raises `ValueError`.

## Command line

Installed as the `spe` console script; also runnable as `python -m spe`.

```text
spe [--url URL] [--version] {health,state,models,inspect,calibrate} ...
```

| Command | Description | Options |
| --- | --- | --- |
| `health` | Check server health. | — |
| `state` | Fetch the master spatial state. | — |
| `models` | List registered perception models. | — |
| `inspect` | Inspect a point against a calibration file. | `--x FLOAT`, `--y FLOAT`, `--calibration PATH`, `--size WxH` (default `1000x600`), `--rows INT` (3), `--columns INT` (3) |
| `calibrate` | Calculate a calibration from four points. | `--size WxH` (required), `--points X,Y X,Y X,Y X,Y` (required), `--rows INT` (3), `--columns INT` (3), `--reference WxH` (`1000x600`), `--units STR` (`normalized`) |

Global options: `--url` (default `http://127.0.0.1:5000`) and `--version`
(prints `spe-sdk <version>`). Points may be written with either commas or
semicolons. Errors print `error: ...` to stderr and return exit code `1`.

```bash
spe --url http://127.0.0.1:5000 health
spe state
spe calibrate --size 1280x720 --points 180,120 1090,150 1180,640 90,660 --rows 4 --columns 6
spe inspect --x 640 --y 360 --calibration calibration.json --size 1280x720
spe --version
```

## Exceptions

All errors derive from `SPEError`.

| Exception | Base classes | Meaning |
| --- | --- | --- |
| `SPEError` | `Exception` | Base class for every SDK error. |
| `SPEValidationError` | `SPEError`, `ValueError` | Invalid geometry or parameters. |
| `SPEEngineError` | `SPEError`, `RuntimeError` | Local processing cannot complete. |
| `SPEModelUnavailableError` | `SPEEngineError` | A model has no usable runtime. |
| `SPETransportError` | `SPEError`, `RuntimeError` | Base for transport failures. |
| `SPEConnectionError` | `SPETransportError` | The server cannot be reached. |
| `SPETimeoutError` | `SPETransportError` | A request exceeded its timeout. |
| `SPEAPIError` | `SPEError` | The server returned an error. |

`SPEAPIError` exposes `status_code: int | None`, `payload: Any | None`, and
`url: str | None`.

## Development

```bash
pip install -e ".[dev]"

ruff check .            # lint
ruff format --check .   # formatting
mypy                    # static types
pytest --cov=spe        # tests + coverage
```

- **Lint/format**: ruff (config in `pyproject.toml`).
- **Types**: mypy in strict-ish mode; all public functions are fully annotated.
- **Tests**: pytest with branch coverage held at ~99% (CI gate: 90%).
- **Packaging**: `python -m build` produces an sdist and wheel; `twine check`
  validates the metadata.

Pre-commit hooks are provided (`pre-commit install`). See
[`CONTRIBUTING.md`](../CONTRIBUTING.md) for conventions and the release process,
and [`CHANGELOG.md`](../CHANGELOG.md) for version history.
