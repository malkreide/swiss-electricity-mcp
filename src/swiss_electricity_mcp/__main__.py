"""Entrypoint for swiss-electricity-mcp.

Transport selected via SWISS_ELECTRICITY_TRANSPORT env var:
- stdio (default): for Claude Desktop and local IDE clients
- streamable-http: for cloud / remote deployments (Render, Railway, etc.)
"""

from __future__ import annotations

import os

from .server import mcp


def main() -> None:
    transport = os.environ.get("SWISS_ELECTRICITY_TRANSPORT", "stdio").lower()
    if transport in {"http", "streamable-http", "sse"}:
        host = os.environ.get("SWISS_ELECTRICITY_HOST", "0.0.0.0")
        port = int(os.environ.get("SWISS_ELECTRICITY_PORT", "8000"))
        mcp.settings.host = host
        mcp.settings.port = port
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
