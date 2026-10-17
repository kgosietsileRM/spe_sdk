"""Local (in-process) calibration and inspection with the SPE SDK.

Run from the project root::

    python examples/local_calibration.py
"""

from __future__ import annotations

from spe import SpatialEngine


def main() -> None:
    # Four image points in TL, TR, BR, BL order for a 1280x720 frame.
    source_points = [[180, 120], [1090, 150], [1180, 640], [90, 660]]

    engine = SpatialEngine(grid_rows=4, grid_columns=6)
    calibration = engine.calibrate(source_points, 1280, 720)

    print(f"reprojection error: {calibration.reprojection_error:.6f}")
    print(f"homography:\n{calibration.homography}")

    result = engine.inspect([640, 360])
    print("\ninspection:")
    print(f"  status   : {result['status']}")
    print(f"  reference: ({result['reference']['x']:.1f}, {result['reference']['y']:.1f})")
    print(f"  grid cell: {result['grid_cell']}")
    print(f"  zone     : {engine.zone_for_image_point([640, 360])}")

    print("\nall zones:", [zone.id for zone in engine.zones()])

    # Persist and reload the calibration.
    payload = engine.to_dict()
    restored = SpatialEngine.from_dict(payload)
    print("\nreloaded calibration is ready:", restored.is_calibrated)


if __name__ == "__main__":
    main()
