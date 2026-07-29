"""End-to-end integration over an in-memory MCP session.

Validates the ARCH-004 lifespan wiring: a tool reaches its HTTP client through
`ctx.request_context.lifespan_context`, populated by the server lifespan — not a
module global. Uses the real MCPServer server + lowlevel session, with respx
mocking the upstream.
"""

from __future__ import annotations

import httpx
import respx
from mcp.client import Client as session_ctx

from swiss_electricity_mcp.api_client import DASHBOARD_BASE
from swiss_electricity_mcp.server import mcp

_PRODUCTION_MIX = {"2023": {"kumuliertKernkraft": 23.3, "anteilKernkraft": 32.1}}


@respx.mock
async def test_tool_uses_lifespan_scoped_client():
    respx.get(f"{DASHBOARD_BASE}/strom/strom-produktionsmix").mock(
        return_value=httpx.Response(200, json=_PRODUCTION_MIX)
    )
    async with session_ctx(mcp) as client:
        result = await client.call_tool("dashboard_get_production_mix", {"response_format": "json"})
        assert result.is_error is False
        text = result.content[0].text
        assert "2023" in text
        assert "live_api" in text


@respx.mock
async def test_tool_list_exposes_annotations():
    async with session_ctx(mcp) as client:
        listed = await client.list_tools()
        assert len(listed.tools) == 12
        prod = next(t for t in listed.tools if t.name == "dashboard_get_production_mix")
        assert prod.annotations.read_only_hint is True
