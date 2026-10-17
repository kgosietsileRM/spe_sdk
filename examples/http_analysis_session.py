"""Run an end-to-end analysis session against a running SPE engine server.

Demonstrates the server workflow: check health, create a source, start an
analysis session, push frames to the detection endpoint, update the session
status, and complete it. Requires the engine to be running (from its own
repository root)::

    python app.py

Then, from this project's root::

    python examples/http_analysis_session.py
"""

from __future__ import annotations

import time

from spe import SPEClient, SPEConnectionError, SPEError

BASE_URL = "http://127.0.0.1:5000"
ANALYSIS_ID = "example-analysis"


def main() -> int:
    try:
        with SPEClient(BASE_URL) as client:
            client.health()
            models = client.list_models()
            model = models[0] if models else {"id": "model-a", "name": "Model A"}
            model_id = str(model["id"])
            print(f"connected to {BASE_URL}; using model {model_id!r}")

            source = client.create_source(b"example-frame", filename="example.jpg")
            source_id = source["id"]

            session = client.start_analysis_session(ANALYSIS_ID, source_id, model)
            print(f"session {ANALYSIS_ID!r} started: {session.get('status', 'running')}")

            for index in range(3):
                result = client.detect_frame(
                    b"example-frame",
                    filename=f"frame-{index}.jpg",
                    model_id=model_id,
                    analysis_id=ANALYSIS_ID,
                    source_id=source_id,
                    frame_index=index,
                    timestamp=time.time(),
                )
                detections = result.get("detections", [])
                print(f"  frame {index}: {len(detections)} detection(s)")

            client.update_analysis_status(ANALYSIS_ID, "running")
            client.complete_analysis_session(ANALYSIS_ID)
            client.delete_source(source_id)
            print("session complete")
    except SPEConnectionError:
        print(f"no SPE server reachable at {BASE_URL} -- start the engine and retry")
        return 1
    except SPEError as error:
        print(f"engine error: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
