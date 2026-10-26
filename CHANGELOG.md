# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1] - 2026-10-26

### Fixed

- Use absolute documentation links in the README so they resolve on PyPI.
- Clarify the published distribution name (`spe-engine`) versus Python import
  package (`spe`).

## [0.2.0] - 2026-10-26

### Added

- `spe.tracking` (`ModelAgnosticTracker`, `TrackingConfig`): provider-neutral
  multi-object association with stable track ids and lifecycle diagnostics.
- `spe.motion` (`SpatialTrackStateManager`, `MotionConfig`): bounded
  trajectories, finite-difference velocity/direction, and optional prediction.
- `spe.observations` (`create_observation`, `create_image_observation`):
  timestamped, provider-neutral observation builders that preserve spatial and
  track data.
- `SPEClient.update_roi` / `AsyncSPEClient.update_roi` for `PUT /api/roi`,
  completing coverage of the engine's ROI routes.
- `spe.inference` (`InferenceContext`, `resolve_inference_context`): validated
  whole-source and four-point ROI inference scopes.
- `spe.analytics` (`ZoneOccupancyTracker`, `LineCrossingCounter`, `TrackSummary`,
  `summarize_tracks`): per-zone occupancy/dwell, directional tripwire counts,
  and per-track summaries.
- `ObservationBatchWriter`: opt-in JSON Lines persistence with batched writes
  and a manifest under a caller-chosen root.
- `ModelDescriptor` and `SPEClient.models()` / `AsyncSPEClient.models()` for
  typed model metadata, including capabilities and tracking modes.
- `SpatialEngine.zone_polygons()` and `SpatialEngine.detections_in_zone()` for
  source-space zone overlays and filtering.
- `BoundingBox` geometry helpers: `area`, `x2`/`y2`, `as_xyxy`, `from_xyxy`,
  `intersection`, `iou`, `union`, `contains`, `translate`, and `scale`.
- Status-specific API errors (`SPEBadRequestError`, `SPEAuthenticationError`,
  `SPENotFoundError`, `SPEConflictError`, `SPERateLimitError`, `SPEServerError`)
  that subclass `SPEAPIError`.
- Optional client authentication (`api_key`, `token`, `headers`) and
  environment support (`SPE_API_KEY`, `SPE_API_TOKEN`).
- CLI commands `spatialize`, `track`, and `render-grid`, plus `models
  --descriptors` and global `--api-key`, `--timeout`, and `--compact` options.
- `examples/analytics_pipeline.py` demonstrating tracks, zones, line crossings,
  and observation persistence.
- Four stand-alone demo apps (`examples/cli`, `examples/powershell`,
  `examples/template`, `examples/web`) that install the built wheel into their
  own virtual environments and cover interactive CLIs, batch automation,
  template-driven JSON, and the FlowTraffic OPS camera wall.

### Changed

- Idempotent requests now also retry HTTP 429/502/503/504, honoring the
  server's `Retry-After` header.
- `health`, `get_state`, `detect`, and `detect_frame` accept a per-call
  `timeout=` override.

## [0.1.0] - 2026-10-17

### Added

- Local spatial core (`spe.geometry`, `spe.spatial`, `spe.grid`, `spe.zones`)
  ported from the Spatial Intelligence Engine: four-point projective
  calibration, coordinate transforms, calibrated grid rendering, cell/zone
  resolution, and detection spatialization.
- `SpatialEngine`, a stateful local facade bundling calibration, grid, and
  source dimensions.
- `SPEClient`, a typed HTTP client for the SPE Flask API with a zero-dependency
  standard-library transport, typed errors, multipart uploads, and automatic
  retries for idempotent requests.
- `AsyncSPEClient`, an asyncio wrapper around `SPEClient`.
- Pluggable transports (`spe.transport`): stdlib `urllib` by default, with
  optional `httpx` and `requests` backends when installed.
- Typed value objects: `BoundingBox`, `Detection`, `ReferencePlane`,
  `GridCell`, `Zone`, and `Calibration`.
- `spe` command-line interface for health checks, state, models, point
  inspection, and calibration.
- Runnable examples under `examples/`.

[Unreleased]: https://github.com/kgosietsileRM/spe_sdk/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/kgosietsileRM/spe_sdk/releases/tag/v0.2.1
[0.2.0]: https://github.com/kgosietsileRM/spe_sdk/releases/tag/v0.2.0
[0.1.0]: https://github.com/kgosietsileRM/spe_sdk/releases/tag/v0.1.0
