"""Asyncio flavour of the SPE HTTP client.

:class:`AsyncSPEClient` mirrors :class:`~spe.client.SPEClient` but exposes every
operation as a coroutine. It is a thin wrapper that offloads the (blocking)
standard-library transport to :func:`asyncio.to_thread`, so it adds no runtime
dependencies while remaining safe to ``await`` inside an event loop.

Usage::

    import asyncio
    from spe.aio import AsyncSPEClient

    async def main() -> None:
        async with AsyncSPEClient("http://127.0.0.1:5000") as client:
            print(await client.health())

    asyncio.run(main())
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping, Sequence
from typing import Any

from .client import FileSource, SPEClient
from .transport import Transport

__all__ = ["AsyncSPEClient"]


class AsyncSPEClient:
    """Asyncio wrapper around :class:`~spe.client.SPEClient`.

    Constructor arguments are forwarded verbatim to :class:`SPEClient`.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:5000",
        *,
        timeout: float = 30.0,
        retries: int = 2,
        backoff: float = 0.5,
        user_agent: str | None = None,
        transport: Transport | None = None,
    ) -> None:
        self._client = SPEClient(
            base_url,
            timeout=timeout,
            retries=retries,
            backoff=backoff,
            user_agent=user_agent,
            transport=transport,
        )

    # -- context management ------------------------------------------------
    async def __aenter__(self) -> AsyncSPEClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Release resources (courtesy of the synchronous client)."""
        await asyncio.to_thread(self._client.close)

    @classmethod
    def from_env(cls, variable: str = "SPE_API_URL", **kwargs: Any) -> AsyncSPEClient:
        """Create a client from an environment variable base URL."""
        return cls(os.environ.get(variable, "http://127.0.0.1:5000"), **kwargs)

    @property
    def base_url(self) -> str:
        return self._client.base_url

    async def _call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(getattr(self._client, method), *args, **kwargs)

    # -- health & state ----------------------------------------------------
    async def health(self) -> dict[str, Any]:
        return await self._call("health")

    async def get_state(self) -> dict[str, Any]:
        return await self._call("get_state")

    # -- sources -----------------------------------------------------------
    async def create_source(
        self,
        source: FileSource,
        *,
        filename: str | None = None,
        source_type: str = "image",
        mime_type: str | None = None,
    ) -> dict[str, Any]:
        return await self._call(
            "create_source",
            source,
            filename=filename,
            source_type=source_type,
            mime_type=mime_type,
        )

    async def get_source(self, source_id: str) -> dict[str, Any]:
        return await self._call("get_source", source_id)

    async def delete_source(self, source_id: str) -> None:
        await self._call("delete_source", source_id)

    def source_media_url(self, source_id: str) -> str:
        return self._client.source_media_url(source_id)

    async def get_source_media(self, source_id: str) -> bytes:
        return await self._call("get_source_media", source_id)

    # -- calibration -------------------------------------------------------
    async def calibrate(
        self,
        source_points: Sequence[Sequence[float]],
        source_width: int,
        source_height: int,
        *,
        reference_width: float = 1000,
        reference_height: float = 600,
        units: str = "normalized",
        rows: int = 3,
        columns: int = 3,
    ) -> dict[str, Any]:
        return await self._call(
            "calibrate",
            source_points,
            source_width,
            source_height,
            reference_width=reference_width,
            reference_height=reference_height,
            units=units,
            rows=rows,
            columns=columns,
        )

    async def get_calibration(self) -> dict[str, Any]:
        return await self._call("get_calibration")

    async def update_calibration(
        self,
        source_points: Sequence[Sequence[float]],
        source_width: int,
        source_height: int,
        *,
        reference_width: float = 1000,
        reference_height: float = 600,
        units: str = "normalized",
        rows: int = 3,
        columns: int = 3,
    ) -> dict[str, Any]:
        return await self._call(
            "update_calibration",
            source_points,
            source_width,
            source_height,
            reference_width=reference_width,
            reference_height=reference_height,
            units=units,
            rows=rows,
            columns=columns,
        )

    async def delete_calibration(self) -> None:
        await self._call("delete_calibration")

    async def get_roi(self) -> dict[str, Any]:
        return await self._call("get_roi")

    async def create_roi(self, points: Sequence[Sequence[float]]) -> dict[str, Any]:
        return await self._call("create_roi", points)

    async def update_roi(self, points: Sequence[Sequence[float]]) -> dict[str, Any]:
        return await self._call("update_roi", points)

    async def delete_roi(self) -> None:
        await self._call("delete_roi")

    async def get_grid(self) -> dict[str, Any]:
        return await self._call("get_grid")

    async def set_grid(self, rows: int, columns: int) -> dict[str, Any]:
        return await self._call("set_grid", rows, columns)

    async def delete_grid(self) -> None:
        await self._call("delete_grid")

    # -- spatial queries ---------------------------------------------------
    async def transform_points(
        self,
        points: Sequence[Sequence[float]],
        *,
        homography: Sequence[Sequence[float]] | None = None,
        calibration: Mapping[str, Any] | None = None,
        direction: str = "image_to_reference",
    ) -> dict[str, Any]:
        return await self._call(
            "transform_points",
            points,
            homography=homography,
            calibration=calibration,
            direction=direction,
        )

    async def inspect_point(
        self,
        point: Sequence[float] | None = None,
        *,
        x: float | None = None,
        y: float | None = None,
        calibration: Mapping[str, Any] | None = None,
        grid: Mapping[str, Any] | None = None,
        source_dimensions: Mapping[str, Any] | None = None,
        spatial_state: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._call(
            "inspect_point",
            point,
            x=x,
            y=y,
            calibration=calibration,
            grid=grid,
            source_dimensions=source_dimensions,
            spatial_state=spatial_state,
        )

    # -- rendering ---------------------------------------------------------
    async def generate_grid(
        self,
        image: FileSource,
        *,
        filename: str | None = None,
        rows: int = 8,
        columns: int = 12,
        line_thickness: int = 1,
        line_color: str = "#a8f35b",
        show_coordinates: bool = True,
        source_type: str = "image",
        fps: float | None = None,
        frame_count: int | None = None,
    ) -> dict[str, Any]:
        return await self._call(
            "generate_grid",
            image,
            filename=filename,
            rows=rows,
            columns=columns,
            line_thickness=line_thickness,
            line_color=line_color,
            show_coordinates=show_coordinates,
            source_type=source_type,
            fps=fps,
            frame_count=frame_count,
        )

    async def generate_calibrated_grid(
        self,
        image: FileSource,
        homography: Sequence[Sequence[float]],
        *,
        filename: str | None = None,
        rows: int = 4,
        columns: int = 6,
        reference_width: float = 1000,
        reference_height: float = 600,
        source_points: Sequence[Sequence[float]] | None = None,
        show_grid: bool = True,
        show_roi: bool = True,
        line_color: str = "#a8f35b",
        roi_color: str = "#ff3b30",
        overlay_only: bool = False,
    ) -> dict[str, Any]:
        return await self._call(
            "generate_calibrated_grid",
            image,
            homography,
            filename=filename,
            rows=rows,
            columns=columns,
            reference_width=reference_width,
            reference_height=reference_height,
            source_points=source_points,
            show_grid=show_grid,
            show_roi=show_roi,
            line_color=line_color,
            roi_color=roi_color,
            overlay_only=overlay_only,
        )

    async def video_metadata(
        self, video: FileSource, *, filename: str | None = None
    ) -> dict[str, Any]:
        return await self._call("video_metadata", video, filename=filename)

    # -- models & analysis -------------------------------------------------
    async def list_models(self) -> list[dict[str, Any]]:
        return await self._call("list_models")

    async def get_model(self, model_id: str) -> dict[str, Any]:
        return await self._call("get_model", model_id)

    async def model_status(self, model_id: str) -> dict[str, Any]:
        return await self._call("model_status", model_id)

    async def load_model(self, model_id: str) -> dict[str, Any]:
        return await self._call("load_model", model_id)

    async def unload_model(self, model_id: str) -> dict[str, Any]:
        return await self._call("unload_model", model_id)

    async def model_classes(self, model_id: str) -> list[str]:
        return await self._call("model_classes", model_id)

    async def detect(
        self,
        *,
        model_id: str = "model-a",
        confidence: float = 0.4,
        classes: Sequence[str] | None = None,
        source_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._call(
            "detect",
            model_id=model_id,
            confidence=confidence,
            classes=classes,
            source_id=source_id,
        )

    async def detect_frame(
        self,
        frame: FileSource,
        *,
        filename: str = "frame.jpg",
        model_id: str = "model-a",
        confidence: float = 0.4,
        classes: Sequence[str] | None = None,
        analysis_id: str = "analysis",
        source_id: str = "source",
        timestamp: float = 0.0,
        frame_index: int = 0,
        tracking: bool = False,
        tracking_mode: str | None = None,
        target_track_id: str | None = None,
        target_detection: Mapping[str, Any] | None = None,
        inference_context: Mapping[str, Any] | None = None,
        spatial_context: Mapping[str, Any] | None = None,
        interval_ms: float | None = None,
        effective_fps: float | None = None,
    ) -> dict[str, Any]:
        return await self._call(
            "detect_frame",
            frame,
            filename=filename,
            model_id=model_id,
            confidence=confidence,
            classes=classes,
            analysis_id=analysis_id,
            source_id=source_id,
            timestamp=timestamp,
            frame_index=frame_index,
            tracking=tracking,
            tracking_mode=tracking_mode,
            target_track_id=target_track_id,
            target_detection=target_detection,
            inference_context=inference_context,
            spatial_context=spatial_context,
            interval_ms=interval_ms,
            effective_fps=effective_fps,
        )

    async def start_analysis_session(
        self,
        analysis_id: str,
        source_id: str,
        model: Mapping[str, Any],
        *,
        spatial_context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._call(
            "start_analysis_session",
            analysis_id,
            source_id,
            model,
            spatial_context=spatial_context,
        )

    async def update_analysis_status(
        self,
        analysis_id: str,
        status: str = "running",
        *,
        inference_fps: float | None = None,
        interval_ms: float | None = None,
    ) -> dict[str, Any]:
        return await self._call(
            "update_analysis_status",
            analysis_id,
            status,
            inference_fps=inference_fps,
            interval_ms=interval_ms,
        )

    async def complete_analysis_session(
        self, analysis_id: str, status: str = "complete"
    ) -> dict[str, Any]:
        return await self._call("complete_analysis_session", analysis_id, status)
