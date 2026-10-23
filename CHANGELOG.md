# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/kgosietsileRM/spe_sdk/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/kgosietsileRM/spe_sdk/releases/tag/v0.1.0
