"""Live tests for swiss-electricity-mcp — hit the real upstream APIs.

Excluded from the *pull-request* CI via the `live` marker (`-m "not live"`) —
but not from CI as such. `.github/workflows/live-tests.yml` runs them weekly,
Mondays at 05:23 UTC, plus on demand via `workflow_dispatch`. That scheduled
run is what DRIFT-005 asks for: the mocked tests are written from the same
assumption as the code and cannot notice when the source changes its format.

Run them by hand:
    pytest tests/test_live.py -m live -v
"""

from __future__ import annotations

import pytest

from swiss_electricity_mcp.api_client import (
    CkanDiscoveryClient,
    ElComSparqlClient,
    EnergyDashboardClient,
)


@pytest.mark.live
class TestLiveEndpoints:
    async def test_energiedashboard_production_mix_live(self):
        client = EnergyDashboardClient()
        try:
            data, prov, _ = await client.get_production_mix()
            assert prov in {"live_api", "cached"}
            assert any(k.startswith("20") for k in data.keys())
        finally:
            await client.aclose()

    async def test_elcom_zurich_tariffs_live(self):
        client = ElComSparqlClient()
        try:
            bindings, prov, _ = await client.get_tariffs_by_municipality(
                bfs_nr=261, period_from=2019, period_to=2025, limit=10
            )
            assert prov in {"sparql", "cached"}
            assert len(bindings) >= 1
        finally:
            await client.aclose()

    async def test_opendata_swiss_bfe_search_live(self):
        client = CkanDiscoveryClient()
        try:
            data, prov, _ = await client.search_opendata_swiss(
                query="stromverbrauch", bfe_only=True
            )
            assert prov in {"live_api", "cached"}
            assert data.get("success") is True
        finally:
            await client.aclose()
