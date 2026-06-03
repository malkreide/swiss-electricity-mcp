# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

- **SEC-016**: HTTP host now defaults to `127.0.0.1` instead of `0.0.0.0`.
  Bind to all interfaces explicitly via `SWISS_ELECTRICITY_HOST=0.0.0.0` inside
  a container only (prevents NeighborJack exposure on developer machines).
- **SEC-007**: Added a multi-stage `Dockerfile` that runs as a non-root user
  (UID 10001) with a `HEALTHCHECK`.
- **SEC-018**: The `category` argument is validated against the closed ElCom
  category enumeration and the `canton` argument is SPARQL-escaped before
  interpolation, closing a SPARQL-injection vector. String arguments now carry
  `min_length`/`max_length` bounds.
- **SEC-021 / SEC-004 / SEC-005**: All outbound requests pass through
  `assert_url_allowed()` — an HTTPS-only, host-allow-listed egress gate
  (`frozenset`). Documented in `docs/network-egress.md`.
- **SEC-022**: Tool definitions are pinned in `tool-definitions.lock.json`; a
  test fails if the tool surface drifts without regenerating the lock.

### Changed

- **ARCH-009**: All 12 tools now declare explicit MCP annotations
  (`readOnlyHint=true`; `openWorldHint=true` for upstream-reaching tools,
  `false` for the static category list).
- **SDK-001**: Shared HTTP clients are now closed cleanly on shutdown via a
  FastMCP `lifespan` context manager.

## [0.1.0] - 2026-05-21

### Added

- Initial release with 12 tools across four groups.
- **Group 1 — Energiedashboard.ch (BFE)**: `dashboard_get_production_mix`,
  `dashboard_get_consumption_forecast`, `dashboard_get_storage_lakes`,
  `dashboard_get_consumer_price_index`.
- **Group 2 — ElCom tariffs (via LINDAS SPARQL)**: `tariff_list_categories`,
  `tariff_get_by_municipality`, `tariff_get_median_swiss`,
  `tariff_get_median_canton`, `tariff_compare_municipalities`.
- **Group 3 — CKAN discovery**: `consumption_search_bfe_datasets`,
  `consumption_search_zurich`.
- **Group 4 — Status**: `electricity_check_status` for liveness probing.
- Dual transport: stdio (default) and Streamable HTTP for cloud deployment.
- Pydantic v2 response envelope with `source` + `provenance` + `retrieved_at`
  on every tool response (no auth required for any endpoint).
- Retry with exponential backoff (3 retries, 2s/4s/8s, 5xx + 429 retried).
- In-memory TTL cache (Dashboard 600s, SPARQL/CKAN 3600s).
- 19 unit tests with respx-mocked happy/retry/timeout/envelope contracts.
- 3 live tests (excluded from CI by default, run with `pytest -m live`).
- GitHub Actions CI matrix for Python 3.11/3.12/3.13.
- OIDC Trusted Publisher workflow for PyPI release-tag publishing.

### Architecture

- **Pattern**: Hybrid (live API + SPARQL + CKAN discovery), no authentication.
- **Endpoints validated live** on 2026-05-21 via the `mcp-data-source-probe` skill.

[0.1.0]: https://github.com/malkreide/swiss-electricity-mcp/releases/tag/v0.1.0
