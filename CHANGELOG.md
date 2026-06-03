# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
