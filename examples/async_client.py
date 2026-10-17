"""Use the asyncio client to talk to a running SPE engine server.

Start the engine first (from its repository root)::

    python app.py

Then run::

    python examples/async_client.py
"""

from __future__ import annotations

import asyncio

from spe import AsyncSPEClient

BASE_URL = "http://127.0.0.1:5000"


async def main() -> None:
    async with AsyncSPEClient(BASE_URL) as client:
        print("health:", await client.health())

        state = await client.get_state()
        print("calibrated:", state["state"].get("calibrated"))

        models = await client.list_models()
        print(f"models: {[model['id'] for model in models]}")

        grid = await client.set_grid(rows=4, columns=6)
        print("grid:", grid)


if __name__ == "__main__":
    asyncio.run(main())
