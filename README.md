# 🇨🇭⚡ swiss-electricity-mcp

> **MCP server for Swiss electricity data — three official sources, twelve tools, zero authentication.**

[![CI](https://github.com/malkreide/swiss-electricity-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/malkreide/swiss-electricity-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/swiss-electricity-mcp.svg)](https://pypi.org/project/swiss-electricity-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/swiss-electricity-mcp.svg)](https://pypi.org/project/swiss-electricity-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

🌍 **Read this in your language:** [🇩🇪 Deutsch](README.de.md)

Part of the **[Swiss Public Data MCP Portfolio](https://github.com/malkreide/swiss-public-data-mcp)** — a coordinated set of MCP servers for Swiss public administration.

---

## 🔥 Anchor demo query

> *"How have ewz electricity tariffs for a typical school building (consumption category C3, ≈150'000 kWh/a) developed since 2019, and how do they compare to the Swiss median?"*

A single conversation calls `tariff_get_by_municipality` (bfs_nr=261, category="C3") + `tariff_get_median_swiss` and returns a year-by-year comparison with full provenance — ready for a Geschäftsleitung slide.

---

## 📊 What's inside

Three official Swiss data sources combined into one MCP server, each with its own dedicated tool group:

| Source | What it provides | Provenance |
|---|---|---|
| **Energiedashboard.ch** (Bundesamt für Energie) | National production mix, consumption forecast, storage-lake fill, consumer price index | `live_api` |
| **ElCom electricity-price cubes** (via LINDAS SPARQL) | Tariffs per municipality, category, year, with full breakdown (energy + grid usage + KEV + Abgaben) | `sparql` |
| **opendata.swiss + Stadt Zürich OGD** (CKAN) | Dataset discovery for raw time series (e.g. quarter-hour NE5/NE7 consumption) | `live_api` |

**No authentication required.** All endpoints are public Swiss OGD.

---

## 🛠️ Tools (12)

### `dashboard_*` — Energiedashboard.ch (BFE)

- **`dashboard_get_production_mix`** — Production mix by year (TWh + %): Kernkraft, Wasserkraft, PV, Wind, thermal.
- **`dashboard_get_consumption_forecast`** — Current consumption forecast + 5-day outlook + 5-year envelope.
- **`dashboard_get_storage_lakes`** — Speichersee fill level (CH or per region: Wallis, Tessin, Graubünden, Zentral/Ost) — critical winter-supply indicator.
- **`dashboard_get_consumer_price_index`** — Endverbraucher-Strompreis-Index (2020-01-01 = 100).

### `tariff_*` — ElCom (via LINDAS SPARQL)

- **`tariff_list_categories`** — H1–H8 (households) and C1–C7 (commercial). **C3 ≈ 150'000 kWh/a is the typical reference for school buildings.**
- **`tariff_get_by_municipality`** — Tariffs for a BFS-Nr + category + year range, broken into energy / grid usage / KEV / Abgaben.
- **`tariff_get_median_swiss`** — National median benchmark.
- **`tariff_get_median_canton`** — Cantonal median (e.g. for Kanton Zürich).
- **`tariff_compare_municipalities`** — Compare up to 20 municipalities side-by-side.

### `consumption_*` — opendata.swiss + Stadt Zürich OGD

- **`consumption_search_bfe_datasets`** — CKAN search across BFE-published datasets.
- **`consumption_search_zurich`** — CKAN search across Stadt Zürich OGD (includes quarter-hour NE5/NE7 consumption).

### Status

- **`electricity_check_status`** — Liveness probe across all four upstreams (HTTP status + latency + overall-healthy flag).

---

## 🚀 Installation

### From PyPI

```bash
pip install swiss-electricity-mcp
```

### From source

```bash
git clone https://github.com/malkreide/swiss-electricity-mcp.git
cd swiss-electricity-mcp
pip install -e ".[dev]"
```

---

## 💬 Use with Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "swiss-electricity": {
      "command": "swiss-electricity-mcp"
    }
  }
}
```

---

## ☁️ Cloud deployment (Streamable HTTP)

```bash
SWISS_ELECTRICITY_TRANSPORT=streamable-http \
SWISS_ELECTRICITY_HOST=0.0.0.0 \
SWISS_ELECTRICITY_PORT=8000 \
swiss-electricity-mcp
```

Works on Render.com, Railway, Fly.io.

---

## 🏗️ Architecture

**Hybrid (live API + SPARQL + CKAN discovery)**, no authentication. Three reasons this is the right shape:

1. **Different latency profiles per source**: Energiedashboard responds in ~200 ms (great live); LINDAS SPARQL is slower and occasionally returns 504 (longer timeout + 3 retries); CKAN is metadata-only and inherently safe.
2. **Different update cadences**: Dashboard updates intraday; ElCom tariffs update once per year; OGD datasets are stable for months. Per-source TTL caching (600 s / 3600 s) reflects this.
3. **Domain separation from `swiss-energy-mcp`**: that server covers geo and infrastructure data (power plants, grid lines). `swiss-electricity-mcp` covers time-series and tariffs. Both compose cleanly.

### Provenance discipline

Every tool response is a Pydantic envelope carrying:

- `source` — full attribution string (e.g. *"Daten: Bundesamt für Energie (BFE)…"*).
- `provenance` — exactly one of `live_api` / `sparql` / `cached` / `weekly_dump` / `stale_cache_fallback`.
- `retrieved_at` — ISO-8601 UTC timestamp.

This makes accidental misattribution structurally impossible.

### Resilience

- **Retry**: 3 attempts with exponential backoff (2 s / 4 s / 8 s).
- **5xx + 429**: retried. **4xx (except 429)**: raised immediately (permanent client error).
- **In-memory TTL cache**: per-source TTLs reduce upstream load and round-trip during multi-step agent workflows.

---

## 🧪 Testing

```bash
# Unit tests (mocked, fast, CI default)
PYTHONPATH=src pytest tests/ -m "not live" -v

# Live tests (hits real upstreams)
PYTHONPATH=src pytest tests/ -m live -v
```

19 unit tests cover the three contract layers: **Happy** (response parsing), **Retry** (5xx, 429, 4xx), **Timeout** (network errors → clean `UpstreamUnreachableError`), plus envelope/attribution invariants.

---

## ⚠️ Known limitations

- **LINDAS SPARQL 504 timeouts**: the LINDAS public endpoint occasionally returns 504 under load. The 3-retry policy handles transient cases; persistent unavailability surfaces as `UpstreamUnreachableError`.
- **No historical PV/wind detail**: Energiedashboard exposes only aggregated production mix at year level. For sub-yearly PV or wind, use `consumption_search_bfe_datasets`.
- **No FHIR or smart-meter data**: out of scope. Future work may add a `swiss-prosumer-mcp` or similar.
- **Year coverage**: ElCom tariff data starts in 2009. Energiedashboard mix starts in 2014.

---

## 🌐 Portfolio synergy

This server composes naturally with other portfolio servers:

- **+ `swiss-energy-mcp`** — combine geo/asset data (power plants) with time-series and tariffs for full energy-infrastructure analysis.
- **+ `meteoswiss-mcp`** — correlate consumption forecasts with weather (temperature drives heating/cooling load).
- **+ `fedlex-mcp`** — pair tariff data with the Stromversorgungsgesetz (StromVG) for compliance/legal context.
- **+ `zh-education-mcp`** — Schulamt-relevant queries combining tariffs, school counts, infrastructure budgets.

---

## 📜 Data sources & licensing

All upstream data is **Open Government Data Switzerland (OGD-CH)**:

- **Energiedashboard.ch** © Bundesamt für Energie BFE — *Open data, free to use.*
- **ElCom / LINDAS** © Eidgenössische Elektrizitätskommission ElCom — *CC BY 4.0.*
- **opendata.swiss** © Various Swiss public bodies — *Mostly CC0 / CC BY 4.0.*
- **Stadt Zürich OGD** © Stadt Zürich — *CC0.*

This MCP server is MIT-licensed (see [LICENSE](LICENSE)). Always cite the original data source — the response envelope includes the proper attribution string automatically.

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## 📝 Changelog

See [CHANGELOG.md](CHANGELOG.md).
