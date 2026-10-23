"""SPE SDK — Python SDK for the Spatial Intelligence Engine.

The SDK offers two complementary surfaces:

* a **local core** (:class:`~spe.engine.SpatialEngine`) that performs four-point
  calibration, coordinate inspection, grid rendering and detection
  spatialization entirely in-process; and
* an **HTTP client** (:class:`~spe.client.SPEClient`) that talks to a running SPE
  engine server.

Quick start (local)::

    from spe import SpatialEngine

    engine = SpatialEngine(grid_rows=4, grid_columns=6)
    engine.calibrate([[120, 80], [880, 110], [940, 520], [60, 540]], 1000, 600)
    print(engine.inspect([500, 300]))

Quick start (server)::

    from spe import SPEClient

    with SPEClient("http://127.0.0.1:5000") as client:
        print(client.health())
        print(client.list_models())
"""

from __future__ import annotations

from ._version import __version__
from .aio import AsyncSPEClient
from .analytics import (
    LineCrossingCounter,
    TrackSummary,
    ZoneOccupancyTracker,
    summarize_tracks,
)
from .client import FileSource, SPEClient
from .engine import SpatialEngine
from .exceptions import (
    SPEAPIError,
    SPEAuthenticationError,
    SPEBadRequestError,
    SPEConflictError,
    SPEConnectionError,
    SPEEngineError,
    SPEError,
    SPEModelUnavailableError,
    SPENotFoundError,
    SPERateLimitError,
    SPEServerError,
    SPETimeoutError,
    SPETransportError,
    SPEValidationError,
)
from .geometry import (
    POINT_ORDER,
    REFERENCE_HEIGHT,
    REFERENCE_WIDTH,
    calculate_calibration,
    calculate_homography,
    inverse_homography,
    reprojection_error,
    transform_points,
    validate_homography,
    validate_source_points,
    warp_image,
)
from .grid import GridConfig, generate_calibrated_grid, generate_grid
from .inference import InferenceContext, resolve_inference_context
from .models import (
    BoundingBox,
    Calibration,
    Detection,
    GridCell,
    ModelDescriptor,
    ReferencePlane,
    Zone,
)
from .motion import MotionConfig, SpatialTrackStateManager
from .observations import (
    ObservationBatchWriter,
    create_image_observation,
    create_observation,
)
from .spatial import (
    image_to_spatial,
    inspect_point,
    point_in_roi,
    spatial_point_to_grid_cell,
    spatialize_detection,
    spatialize_detection_result,
)
from .tracking import ModelAgnosticTracker, TrackingConfig
from .transport import (
    HttpxTransport,
    RequestsTransport,
    Transport,
    UrllibTransport,
    get_default_transport,
)
from .zones import generate_zones, row_label, zone_for_cell

__all__ = [
    "__version__",
    # engines & clients
    "SpatialEngine",
    "SPEClient",
    "AsyncSPEClient",
    "FileSource",
    "Transport",
    "UrllibTransport",
    "RequestsTransport",
    "HttpxTransport",
    "get_default_transport",
    # models
    "BoundingBox",
    "Calibration",
    "Detection",
    "GridCell",
    "ModelDescriptor",
    "ReferencePlane",
    "Zone",
    # geometry
    "POINT_ORDER",
    "REFERENCE_WIDTH",
    "REFERENCE_HEIGHT",
    "calculate_calibration",
    "calculate_homography",
    "inverse_homography",
    "reprojection_error",
    "transform_points",
    "validate_homography",
    "validate_source_points",
    "warp_image",
    # grid
    "GridConfig",
    "generate_grid",
    "generate_calibrated_grid",
    # spatial
    "image_to_spatial",
    "inspect_point",
    "point_in_roi",
    "spatial_point_to_grid_cell",
    "spatialize_detection",
    "spatialize_detection_result",
    # inference
    "InferenceContext",
    "resolve_inference_context",
    # zones
    "row_label",
    "generate_zones",
    "zone_for_cell",
    # tracking, motion, observations & analytics
    "ModelAgnosticTracker",
    "TrackingConfig",
    "MotionConfig",
    "SpatialTrackStateManager",
    "ObservationBatchWriter",
    "create_observation",
    "create_image_observation",
    "ZoneOccupancyTracker",
    "LineCrossingCounter",
    "TrackSummary",
    "summarize_tracks",
    # exceptions
    "SPEError",
    "SPEValidationError",
    "SPEEngineError",
    "SPEModelUnavailableError",
    "SPETransportError",
    "SPEConnectionError",
    "SPETimeoutError",
    "SPEAPIError",
    "SPEBadRequestError",
    "SPEAuthenticationError",
    "SPENotFoundError",
    "SPEConflictError",
    "SPERateLimitError",
    "SPEServerError",
]
