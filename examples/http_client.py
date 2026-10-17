"""Talk to a running SPE engine server with the SDK HTTP client.

Start the engine first (from its repository root)::

    python app.py

Then run::

    python examples/http_client.py
"""

from __future__ import annotations

from spe import SPEClient

BASE_URL = "http://127.0.0.1:5000"


def main() -> None:
    with SPEClient(BASE_URL) as client:
        print("health:", client.health())
        print("state :", client.get_state()["state"])

        print("\nmodels:")
        for model in client.list_models():
            print(f"  - {model['id']}: {model['name']} ({model['status']})")

        # Upload an image, calibrate it, and inspect a point.
        # source = client.create_source("path/to/frame.jpg", source_type="image")
        # calibration = client.calibrate(
        #     [[180, 120], [1090, 150], [1180, 640], [90, 660]],
        #     source_width=1280,
        #     source_height=720,
        # )
        # inspection = client.inspect_point(
        #     [640, 360],
        #     calibration=calibration["calibration"],
        #     grid={"rows": 4, "columns": 6},
        #     source_dimensions={"width": 1280, "height": 720},
        # )
        # print("inspection:", inspection)


if __name__ == "__main__":
    main()
