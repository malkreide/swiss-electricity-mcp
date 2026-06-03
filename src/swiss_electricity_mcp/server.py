"""FastMCP server for swiss-electricity-mcp.

Tools are grouped by source:
- dashboard_*  -> Energiedashboard.ch (BFE) live national figures
- tariff_*     -> ElCom electricity-price cubes via LINDAS SPARQL
- consumption_* -> Stadt Zuerich OGD + opendata.swiss BFE dataset discovery
- electricity_check_status -> liveness probe across all upstream sources
"""

from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .api_client import (
    DASHBOARD_BASE,
    LINDAS_SPARQL,
    OPENDATA_SWISS_CKAN,
    ZURICH_OGD_CKAN,
    CkanDiscoveryClient,
    ElComSparqlClient,
    EnergyDashboardClient,
    UpstreamUnreachableError,
    sparql_value,
    utc_now_iso,
)
from .models import (
    ATTRIBUTION_BFE,
    ATTRIBUTION_ELCOM,
    ATTRIBUTION_OPENDATA_SWISS,
    ATTRIBUTION_ZURICH,
    CkanDataset,
    ConsumptionEntry,
    ConsumptionForecastResponse,
    DatasetSearchResponse,
    IndexedPriceEntry,
    IndexedPriceResponse,
    MedianTariffEntry,
    MedianTariffResponse,
    ProductionMixResponse,
    ProductionMixYear,
    SourceStatus,
    StatusResponse,
    StorageLakeEntry,
    StorageLakesResponse,
    TariffCategoriesResponse,
    TariffCategory,
    TariffComparisonResponse,
    TariffComparisonRow,
    TariffObservation,
    TariffResponse,
)

# Shared HTTP clients, reused across all tool calls (no per-call client creation).
# Their lifecycle is owned by the lifespan context manager below, which closes
# them cleanly on server shutdown.
_dashboard = EnergyDashboardClient()
_elcom = ElComSparqlClient()
_ckan = CkanDiscoveryClient()

# Annotation presets: every tool is read-only. Tools that reach an external
# upstream are open-world; the static category list is closed-world.
_READ_ONLY_EXTERNAL = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
_READ_ONLY_STATIC = ToolAnnotations(readOnlyHint=True, openWorldHint=False)


@asynccontextmanager
async def lifespan(_server: FastMCP):
    """Own the lifecycle of the shared HTTP clients; close them on shutdown."""
    try:
        yield
    finally:
        await _dashboard.aclose()
        await _elcom.aclose()
        await _ckan.aclose()


mcp = FastMCP(
    name="swiss-electricity-mcp",
    instructions=(
        "Swiss electricity data from three official sources: Energiedashboard.ch (BFE) "
        "for national production/consumption/prices, ElCom for tariffs per municipality, "
        "and Stadt Zuerich OGD for high-frequency local consumption data. "
        "Every response includes source attribution and provenance - quote them. "
        "Category C3 (~150'000 kWh/a) is the typical reference for school buildings."
    ),
    lifespan=lifespan,
)


def _format_response(model_obj, response_format: str) -> str:
    """Toggle JSON / Markdown response format."""
    if response_format == "json":
        return model_obj.model_dump_json(indent=2)
    return _to_markdown(model_obj)


def _to_markdown(model_obj) -> str:
    """Generic markdown formatter that respects the envelope."""
    data = model_obj.model_dump()
    lines: list[str] = []
    if "source" in data:
        lines.append(f"**Source:** {data['source']}")
    if "provenance" in data:
        lines.append(
            f"**Provenance:** `{data['provenance']}`  "
            f"**Retrieved:** {data.get('retrieved_at', '?')}"
        )
        lines.append("")
    for k, v in data.items():
        if k in {"source", "provenance", "retrieved_at"}:
            continue
        if isinstance(v, list):
            lines.append(f"### {k} ({len(v)})")
            for item in v[:25]:
                if isinstance(item, dict):
                    summary = ", ".join(
                        f"{kk}={vv}" for kk, vv in item.items() if vv is not None
                    )
                    lines.append(f"- {summary}")
                else:
                    lines.append(f"- {item}")
            if len(v) > 25:
                lines.append(
                    f"- _(+ {len(v) - 25} more - request JSON format for full list)_"
                )
        else:
            lines.append(f"**{k}:** {v}")
    return "\n".join(lines)


# ===== GROUP 1: dashboard_* (Energiedashboard.ch BFE) =====


@mcp.tool(
    description=(
        "Get the Swiss electricity production mix (Kernkraft, Wasserkraft, PV, Wind ...) "
        "by year, with absolute TWh and percentage shares. Source: Energiedashboard.ch (BFE)."
    ),
    annotations=_READ_ONLY_EXTERNAL,
)
async def dashboard_get_production_mix(
    response_format: Annotated[
        Literal["json", "markdown"],
        Field(description="Output format. 'json' for processing, 'markdown' for display."),
    ] = "markdown",
) -> str:
    """Aktueller Schweizer Strom-Produktionsmix pro Jahr (Anteile + TWh)."""
    data, prov, retrieved = await _dashboard.get_production_mix()
    years: list[ProductionMixYear] = []
    for year_str, payload in sorted(data.items()):
        try:
            year = int(year_str)
        except ValueError:
            continue
        years.append(
            ProductionMixYear(
                year=year,
                kumuliert_kernkraft_twh=payload.get("kumuliertKernkraft"),
                kumuliert_thermische_twh=payload.get("kumuliertThermische"),
                kumuliert_flusskraft_twh=payload.get("kumuliertFlusskraft"),
                kumuliert_speicherkraft_twh=payload.get("kumuliertSpeicherkraft"),
                kumuliert_wind_twh=payload.get("kumuliertWind"),
                kumuliert_photovoltaik_twh=payload.get("kumuliertPhotovoltaik"),
                kumuliert_eigenproduktion_twh=payload.get("kumuliertEigenproduktion"),
                anteil_kernkraft_pct=payload.get("anteilKernkraft"),
                anteil_thermische_pct=payload.get("anteilThermische"),
                anteil_flusskraft_pct=payload.get("anteilFlusskraft"),
                anteil_speicherkraft_pct=payload.get("anteilSpeicherkraft"),
                anteil_wind_pct=payload.get("anteilWind"),
                anteil_photovoltaik_pct=payload.get("anteilPhotovoltaik"),
            )
        )
    response = ProductionMixResponse(
        source=ATTRIBUTION_BFE, provenance=prov, retrieved_at=retrieved, years=years,
    )
    return _format_response(response, response_format)


@mcp.tool(
    description=(
        "Get current Swiss national electricity consumption forecast: today's value, "
        "5-day-ahead forecast, trend signal, and 5-year-window comparison series. "
        "Source: Energiedashboard.ch (BFE)."
    ),
    annotations=_READ_ONLY_EXTERNAL,
)
async def dashboard_get_consumption_forecast(
    limit_days: Annotated[int, Field(ge=1, le=400)] = 90,
    response_format: Annotated[Literal["json", "markdown"], Field()] = "markdown",
) -> str:
    """Stromverbrauchs-Prognose Schweiz mit 5-Jahres-Vergleich."""
    data, prov, retrieved = await _dashboard.get_consumption_forecast()
    current = data.get("currentEntry") or {}
    entries = data.get("entries") or []
    parsed = [
        ConsumptionEntry(
            date=e.get("date", ""),
            landesverbrauch_gwh=e.get("landesverbrauch"),
            landesverbrauch_geschaetzt_gwh=e.get("landesverbrauchGeschaetzt"),
            landesverbrauch_prognose_gwh=e.get("landesverbrauchPrognose"),
            five_year_min_gwh=e.get("fiveYearMin"),
            five_year_max_gwh=e.get("fiveYearMax"),
            five_year_mittelwert_gwh=e.get("fiveYearMittelwert"),
        )
        for e in entries[-limit_days:]
    ]
    response = ConsumptionForecastResponse(
        source=ATTRIBUTION_BFE,
        provenance=prov,
        retrieved_at=retrieved,
        current_forecast_gwh=current.get("landesverbrauchPrognose"),
        forecast_in_five_days_gwh=current.get("landesverbrauchPrognoseInFiveDays"),
        trend=current.get("trend"),
        trend_rating=current.get("trendRating"),
        series=parsed,
    )
    return _format_response(response, response_format)


@mcp.tool(
    description=(
        "Get storage-lake (Speichersee) fill level for Switzerland or a region: "
        "current fill in % and GWh, 5-year envelope, full time series. "
        "Critical indicator for winter supply security."
    ),
    annotations=_READ_ONLY_EXTERNAL,
)
async def dashboard_get_storage_lakes(
    region: Annotated[
        Literal["totalCH", "Wallis", "Tessin", "Graubuenden", "ZentralOst"],
        Field(description="Region selector."),
    ] = "totalCH",
    limit_weeks: Annotated[int, Field(ge=1, le=300)] = 52,
    response_format: Annotated[Literal["json", "markdown"], Field()] = "markdown",
) -> str:
    """Speicherseen-Fuellstand (Wochenwerte) fuer Schweiz oder Region."""
    data, prov, retrieved = await _dashboard.get_storage_lakes()
    block = data.get(region) or data.get("totalCH") or {}
    current = block.get("currentEntry") or {}
    entries = block.get("entries") or []
    parsed = [
        StorageLakeEntry(
            date=e.get("date", ""),
            speicherstand_prozent=e.get("speicherstandProzent"),
            speicherstand_gwh=e.get("speicherstandGWh"),
            five_year_min_pct=e.get("fiveYearMin"),
            five_year_max_pct=e.get("fiveYearMax"),
            five_year_mittelwert_pct=e.get("fiveYearMittelwert"),
        )
        for e in entries[-limit_weeks:]
    ]
    capacity = entries[-1].get("speicherstandBei100ProzentInGWh") if entries else None
    response = StorageLakesResponse(
        source=ATTRIBUTION_BFE,
        provenance=prov,
        retrieved_at=retrieved,
        region=region,
        current_fill_pct=current.get("speicherstandProzent"),
        current_fill_gwh=current.get("speicherstandGWh"),
        capacity_gwh=capacity,
        series=parsed,
    )
    return _format_response(response, response_format)


@mcp.tool(
    description=(
        "Get the Endverbraucher-Strompreis-Index (consumer electricity price index, "
        "indexed to 2020-01-01 = 100). Monthly time series."
    ),
    annotations=_READ_ONLY_EXTERNAL,
)
async def dashboard_get_consumer_price_index(
    limit_months: Annotated[int, Field(ge=1, le=200)] = 60,
    response_format: Annotated[Literal["json", "markdown"], Field()] = "markdown",
) -> str:
    """Endverbraucher-Strompreis-Index (Index 2020-01-01 = 100)."""
    data, prov, retrieved = await _dashboard.get_consumer_price_index()
    series = data if isinstance(data, list) else []
    parsed = [
        IndexedPriceEntry(date=e.get("date", ""), preis_indexiert=e.get("preisIndexiert"))
        for e in series[-limit_months:]
    ]
    response = IndexedPriceResponse(
        source=ATTRIBUTION_BFE, provenance=prov, retrieved_at=retrieved, series=parsed,
    )
    return _format_response(response, response_format)


# ===== GROUP 2: tariff_* (ElCom via LINDAS SPARQL) =====


@mcp.tool(
    description=(
        "List the standard ElCom Verbrauchskategorien (H1-H8 households, C1-C7 commercial). "
        "Use C3 for typical school buildings (~150'000 kWh/year). Static data, no upstream call."
    ),
    annotations=_READ_ONLY_STATIC,
)
async def tariff_list_categories(
    response_format: Annotated[Literal["json", "markdown"], Field()] = "markdown",
) -> str:
    """Liste der ElCom-Verbrauchskategorien (statisch)."""
    cats = [
        TariffCategory(
            code=c["code"], description_de=c["desc"], typical_consumption_kwh=c["kwh"]
        )
        for c in ElComSparqlClient.CATEGORIES
    ]
    response = TariffCategoriesResponse(
        source=ATTRIBUTION_ELCOM,
        provenance="cached",
        retrieved_at=utc_now_iso(),
        categories=cats,
    )
    return _format_response(response, response_format)


@mcp.tool(
    description=(
        "Get ElCom tariff observations for a Swiss municipality (BFS-Nr). Returns total "
        "rate in Rp./kWh broken down by energy, grid usage, public charges (KEV, Abgaben). "
        "Filterable by category (e.g. C3 for schools) and year range. "
        "Example: bfs_nr=261 for Zuerich, category='C3', period_from=2019."
    ),
    annotations=_READ_ONLY_EXTERNAL,
)
async def tariff_get_by_municipality(
    bfs_nr: Annotated[int, Field(description="BFS-Gemeindenummer (e.g. 261=Zuerich)", ge=1)],
    category: Annotated[str | None, Field(description="Verbrauchskategorie")] = None,
    period_from: Annotated[int | None, Field(ge=2009)] = None,
    period_to: Annotated[int | None, Field(le=2100)] = None,
    limit: Annotated[int, Field(ge=1, le=500)] = 100,
    response_format: Annotated[Literal["json", "markdown"], Field()] = "markdown",
) -> str:
    """ElCom-Tarif-Beobachtungen fuer eine Gemeinde."""
    bindings, prov, retrieved = await _elcom.get_tariffs_by_municipality(
        bfs_nr=bfs_nr,
        category=category,
        period_from=period_from,
        period_to=period_to,
        limit=limit,
    )
    municipality_name: str | None = None
    obs_list: list[TariffObservation] = []
    for b in bindings:
        if municipality_name is None:
            municipality_name = sparql_value(b, "munLabel")
        operator_uri = sparql_value(b, "operator") or ""
        operator_id = str(operator_uri).rsplit("/", 1)[-1]
        obs_list.append(
            TariffObservation(
                period=int(sparql_value(b, "period") or 0),
                municipality_bfs_nr=bfs_nr,
                municipality_name=municipality_name,
                operator_id=operator_id,
                operator_name=sparql_value(b, "operatorLabel"),
                category=str(sparql_value(b, "categoryCode") or ""),
                product=str(sparql_value(b, "productLabel") or ""),
                total_rp_per_kwh=sparql_value(b, "total"),
                energy_rp_per_kwh=sparql_value(b, "energy"),
                gridusage_rp_per_kwh=sparql_value(b, "gridusage"),
                charge_rp_per_kwh=sparql_value(b, "charge"),
                aidfee_rp_per_kwh=sparql_value(b, "aidfee"),
                energy_name=sparql_value(b, "energyName"),
                gridusage_name=sparql_value(b, "gridusageName"),
            )
        )
    response = TariffResponse(
        source=ATTRIBUTION_ELCOM,
        provenance=prov,
        retrieved_at=retrieved,
        municipality_name=municipality_name,
        municipality_bfs_nr=bfs_nr,
        observations=obs_list,
    )
    return _format_response(response, response_format)


@mcp.tool(
    description=(
        "Get Swiss median electricity tariff (across all distribution operators) by "
        "year and category. Useful as benchmark for individual municipality tariffs."
    ),
    annotations=_READ_ONLY_EXTERNAL,
)
async def tariff_get_median_swiss(
    category: Annotated[str | None, Field()] = None,
    period_from: Annotated[int | None, Field(ge=2009)] = None,
    period_to: Annotated[int | None, Field(le=2100)] = None,
    limit: Annotated[int, Field(ge=1, le=500)] = 200,
    response_format: Annotated[Literal["json", "markdown"], Field()] = "markdown",
) -> str:
    """Schweizer Median-Tarif als Vergleichswert."""
    bindings, prov, retrieved = await _elcom.get_median_swiss(
        category=category, period_from=period_from, period_to=period_to, limit=limit
    )
    entries = [
        MedianTariffEntry(
            period=int(sparql_value(b, "period") or 0),
            category=str(sparql_value(b, "categoryCode") or ""),
            median_total_rp_per_kwh=float(sparql_value(b, "total") or 0.0),
        )
        for b in bindings
    ]
    response = MedianTariffResponse(
        source=ATTRIBUTION_ELCOM,
        provenance=prov,
        retrieved_at=retrieved,
        scope="swiss",
        observations=entries,
    )
    return _format_response(response, response_format)


@mcp.tool(
    description=(
        "Get cantonal median electricity tariff. Useful to position a municipality "
        "against its canton. Pass canton name in German (e.g. 'Zuerich', 'Bern')."
    ),
    annotations=_READ_ONLY_EXTERNAL,
)
async def tariff_get_median_canton(
    canton: Annotated[str, Field(description="Canton name in German")],
    category: Annotated[str | None, Field()] = None,
    period_from: Annotated[int | None, Field(ge=2009)] = None,
    period_to: Annotated[int | None, Field(le=2100)] = None,
    limit: Annotated[int, Field(ge=1, le=500)] = 200,
    response_format: Annotated[Literal["json", "markdown"], Field()] = "markdown",
) -> str:
    """Kantonaler Median-Tarif."""
    bindings, prov, retrieved = await _elcom.get_median_canton(
        canton=canton,
        category=category,
        period_from=period_from,
        period_to=period_to,
        limit=limit,
    )
    entries = [
        MedianTariffEntry(
            period=int(sparql_value(b, "period") or 0),
            category=str(sparql_value(b, "categoryCode") or ""),
            median_total_rp_per_kwh=float(sparql_value(b, "total") or 0.0),
        )
        for b in bindings
    ]
    response = MedianTariffResponse(
        source=ATTRIBUTION_ELCOM,
        provenance=prov,
        retrieved_at=retrieved,
        scope="canton",
        canton_id=canton,
        observations=entries,
    )
    return _format_response(response, response_format)


@mcp.tool(
    description=(
        "Compare electricity tariffs across multiple municipalities (BFS-Nrs) for one "
        "category and year. One row per (municipality, operator). Useful for procurement, "
        "benchmarking, school-network analysis."
    ),
    annotations=_READ_ONLY_EXTERNAL,
)
async def tariff_compare_municipalities(
    bfs_numbers: Annotated[list[int], Field(min_length=1, max_length=20)],
    category: Annotated[str, Field(description="Verbrauchskategorie (e.g. C3)")],
    period: Annotated[int, Field(ge=2009, le=2100)],
    response_format: Annotated[Literal["json", "markdown"], Field()] = "markdown",
) -> str:
    """Tarif-Vergleich mehrerer Gemeinden fuer eine Kategorie und ein Jahr."""
    rows: list[TariffComparisonRow] = []
    last_prov: str = "sparql"
    for bfs in bfs_numbers:
        bindings, prov, _ = await _elcom.get_tariffs_by_municipality(
            bfs_nr=bfs, category=category, period_from=period, period_to=period, limit=20
        )
        last_prov = prov
        for b in bindings:
            rows.append(
                TariffComparisonRow(
                    municipality_bfs_nr=bfs,
                    municipality_name=sparql_value(b, "munLabel"),
                    period=int(sparql_value(b, "period") or 0),
                    category=str(sparql_value(b, "categoryCode") or ""),
                    total_rp_per_kwh=sparql_value(b, "total"),
                )
            )
    response = TariffComparisonResponse(
        source=ATTRIBUTION_ELCOM,
        provenance=last_prov,
        retrieved_at=utc_now_iso(),
        rows=rows,
    )
    return _format_response(response, response_format)


# ===== GROUP 3: consumption_* (opendata.swiss + Stadt Zuerich OGD) =====


@mcp.tool(
    description=(
        "Search opendata.swiss CKAN for energy / electricity datasets. Filter by BFE "
        "organisation. Use to find raw datasets not covered by other tools."
    ),
    annotations=_READ_ONLY_EXTERNAL,
)
async def consumption_search_bfe_datasets(
    query: Annotated[str, Field(description="Free-text search")],
    bfe_only: Annotated[bool, Field()] = True,
    limit: Annotated[int, Field(ge=1, le=50)] = 20,
    offset: Annotated[int, Field(ge=0)] = 0,
    response_format: Annotated[Literal["json", "markdown"], Field()] = "markdown",
) -> str:
    """Suche nach BFE-Datensaetzen auf opendata.swiss."""
    data, prov, retrieved = await _ckan.search_opendata_swiss(
        query=query, rows=limit, offset=offset, bfe_only=bfe_only
    )
    if not data.get("success"):
        raise UpstreamUnreachableError("opendata.swiss returned success=false")
    result = data.get("result") or {}
    datasets: list[CkanDataset] = []
    for r in result.get("results", []):
        title = r.get("title")
        if isinstance(title, dict):
            title_de = title.get("de") or title.get("en") or "?"
        else:
            title_de = str(title or "?")
        desc = r.get("description")
        desc_de = desc.get("de") if isinstance(desc, dict) else desc
        datasets.append(
            CkanDataset(
                name=r.get("name", "?"),
                title_de=title_de,
                organization=(r.get("organization") or {}).get("name", "?"),
                description_de=desc_de,
                resources_count=len(r.get("resources") or []),
                landing_page=f"https://opendata.swiss/de/dataset/{r.get('name')}",
            )
        )
    response = DatasetSearchResponse(
        source=ATTRIBUTION_OPENDATA_SWISS,
        provenance=prov,
        retrieved_at=retrieved,
        query=query,
        total_hits=result.get("count", len(datasets)),
        datasets=datasets,
    )
    return _format_response(response, response_format)


@mcp.tool(
    description=(
        "Search the Stadt Zuerich OGD catalogue for energy datasets, including the "
        "quarter-hour consumption time series for grid levels NE5 and NE7."
    ),
    annotations=_READ_ONLY_EXTERNAL,
)
async def consumption_search_zurich(
    query: Annotated[str, Field()],
    limit: Annotated[int, Field(ge=1, le=50)] = 10,
    offset: Annotated[int, Field(ge=0)] = 0,
    response_format: Annotated[Literal["json", "markdown"], Field()] = "markdown",
) -> str:
    """Suche im Stadt-Zuerich-OGD-Portal."""
    data, prov, retrieved = await _ckan.search_zurich(query=query, rows=limit, offset=offset)
    if not data.get("success"):
        raise UpstreamUnreachableError("data.stadt-zuerich.ch returned success=false")
    result = data.get("result") or {}
    datasets: list[CkanDataset] = []
    for r in result.get("results", []):
        title = r.get("title") or "?"
        desc = r.get("notes")
        datasets.append(
            CkanDataset(
                name=r.get("name", "?"),
                title_de=str(title),
                organization=(r.get("organization") or {}).get("name", "stadt-zurich"),
                description_de=str(desc) if desc else None,
                resources_count=len(r.get("resources") or []),
                landing_page=f"https://data.stadt-zuerich.ch/dataset/{r.get('name')}",
            )
        )
    response = DatasetSearchResponse(
        source=ATTRIBUTION_ZURICH,
        provenance=prov,
        retrieved_at=retrieved,
        query=query,
        total_hits=result.get("count", len(datasets)),
        datasets=datasets,
    )
    return _format_response(response, response_format)


# ===== GROUP 4: electricity_check_status (liveness) =====


@mcp.tool(
    description=(
        "Check liveness of all four upstream sources. Returns HTTP status, latency, "
        "and an overall-healthy flag."
    ),
    annotations=_READ_ONLY_EXTERNAL,
)
async def electricity_check_status() -> str:
    """Liveness-Check aller Upstream-Quellen."""
    probes = [
        ("Energiedashboard.ch (BFE)", f"{DASHBOARD_BASE}/strom/strom-produktionsmix"),
        ("LINDAS SPARQL (ElCom)", LINDAS_SPARQL),
        ("opendata.swiss CKAN", f"{OPENDATA_SWISS_CKAN}/status_show"),
        ("Stadt Zuerich OGD", f"{ZURICH_OGD_CKAN}/status_show"),
    ]
    results: list[SourceStatus] = []
    async with httpx.AsyncClient(
        timeout=10.0,
        headers={"User-Agent": "swiss-electricity-mcp/0.1.0 status-probe"},
    ) as http:
        for name, url in probes:
            t0 = time.monotonic()
            try:
                resp = await http.get(url)
                latency_ms = int((time.monotonic() - t0) * 1000)
                results.append(
                    SourceStatus(
                        name=name,
                        url=url,
                        reachable=resp.status_code < 500,
                        http_status=resp.status_code,
                        latency_ms=latency_ms,
                    )
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                latency_ms = int((time.monotonic() - t0) * 1000)
                results.append(
                    SourceStatus(
                        name=name,
                        url=url,
                        reachable=False,
                        http_status=None,
                        latency_ms=latency_ms,
                        note=f"{type(exc).__name__}: {exc}",
                    )
                )
    overall = all(r.reachable for r in results)
    response = StatusResponse(
        checked_at=utc_now_iso(), sources=results, overall_healthy=overall,
    )
    return json.dumps(response.model_dump(), indent=2, ensure_ascii=False)
