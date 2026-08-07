"""HTTP clients for the three upstream sources.

Eselsbrücke: «Drei Mal anklopfen, dann höflich aufgeben.»
- 3 retries with 2s/4s/8s waits
- 5xx + network errors retry; 4xx (except 429) raise immediately
- In-memory TTL cache to reduce redundant fetches
"""

from __future__ import annotations

import asyncio
import random
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from . import __version__
from .models import (
    ATTRIBUTION_BFE,
    ATTRIBUTION_ELCOM,
    ATTRIBUTION_OPENDATA_SWISS,
    ATTRIBUTION_ZURICH,
)
from .observability import get_logger

DASHBOARD_BASE = "https://www.energiedashboard.admin.ch/api"
LINDAS_SPARQL = "https://lindas.admin.ch/query"
OPENDATA_SWISS_CKAN = "https://opendata.swiss/api/3/action"
ZURICH_OGD_CKAN = "https://data.stadt-zuerich.ch/api/3/action"

DEFAULT_USER_AGENT = (
    f"swiss-electricity-mcp/{__version__} (+https://github.com/malkreide/swiss-electricity-mcp)"
)
DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 3
BACKOFF_BASE = 2


# --- Retry policy ------------------------------------------------------------
# Adopted from the mcp-data-source-probe reference template (repaired
# 2026-08-07). Three questions: *what* is retried, *how fast*, and *how long*.
# The first is settled in the retry loop (4xx except 429 fails fast); these
# settle the other two.

# The attempt count and the base live above as MAX_RETRIES / BACKOFF_BASE.

# Ceiling on the WHOLE call — every attempt and every wait together. An attempt
# count is not a bound: four attempts against an upstream that takes 30s to time
# out is two minutes inside one tool call, and the number never says so. The
# anchor is measured, not guessed: the Python MCP SDK ships
# MCP_DEFAULT_TIMEOUT = 30.0, so 25s leaves headroom for framing and parsing.
RETRY_TOTAL_BUDGET = 25.0

# Ceiling for a single wait. Bounds the exponential ladder, and bounds a
# `Retry-After` the source may send but we are not obliged to sit through.
RETRY_MAX_DELAY = 20.0

# Jitter spread. Without it every client that hit the same outage retries in
# lockstep, and the load returns as a wave exactly when the source recovers —
# the retry storm extends the outage it was meant to bridge.
RETRY_JITTER_SPREAD = 0.5  # exponential delays land in [0.5x, 1.5x]

# On a `Retry-After`, deliberately one-sided: the source said when to come back,
# so coming back later is fine and coming back earlier is not.
RETRY_AFTER_JITTER = 0.25  # lands in [1.0x, 1.25x]

# Statuses that carry a meaningful `Retry-After` (RFC 9110 section 10.2.3).
RETRY_AFTER_STATUSES = frozenset({429, 503})


def parse_retry_after(resp: httpx.Response | None) -> float | None:
    """Seconds to wait per the response's ``Retry-After``, or ``None``.

    RFC 9110 section 10.2.3 allows two forms — delta-seconds (``120``) and an
    HTTP-date (``Wed, 21 Oct 2026 07:28:00 GMT``). Both appear in the wild, so
    both are read. Anything unparseable yields ``None`` and the caller falls
    back to its own curve: a malformed header must not become a crash on the
    error path, which is the one path already going badly.
    """
    if resp is None or resp.status_code not in RETRY_AFTER_STATUSES:
        return None
    raw = (resp.headers.get("retry-after") or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return float(raw)
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:  # RFC 9110 dates are GMT; a naive one means UTC
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


def compute_delay(attempt: int, last_error: Exception | None) -> float:
    """Seconds to wait before ``attempt`` (1-based for the first retry).

    The source's own answer beats our guess: a ``Retry-After`` on a 429 or 503
    wins over the exponential curve. Everything is spread, then capped.

    The cap wraps the jitter and not the other way round. ``min(cap, base) *
    jitter`` and ``min(cap, base * jitter)`` both contain a cap and a jitter;
    only the second is bounded — a value capped at 20s and then multiplied by
    up to 1.5 lands at 30s, and the constant would claim a ceiling it does not
    hold.
    """
    hinted = parse_retry_after(getattr(last_error, "response", None))
    if hinted is not None:
        return min(
            hinted * (1.0 + random.random() * RETRY_AFTER_JITTER),
            RETRY_MAX_DELAY,
        )
    return min(
        float(BACKOFF_BASE) ** attempt
        * (1.0 - RETRY_JITTER_SPREAD + random.random() * 2 * RETRY_JITTER_SPREAD),
        RETRY_MAX_DELAY,
    )


# SEC-021 egress allow-list: the only hosts this server is ever allowed to reach.
# Code-layer control as a frozenset, not config-mutable at runtime. Network-layer
# egress control (NetworkPolicy / firewall) is the complementary defense-in-depth
# layer documented in docs/network-egress.md.
ALLOWED_HOSTS: frozenset[str] = frozenset(
    {
        "www.energiedashboard.admin.ch",
        "lindas.admin.ch",
        "opendata.swiss",
        "data.stadt-zuerich.ch",
    }
)


class UpstreamUnreachableError(Exception):
    """Raised when an upstream is unreachable after exhausted retries."""


class UpstreamSchemaError(Exception):
    """Die Antwort kam an, sieht aber anders aus, als der Code sie liest.

    Bewusst neben ``UpstreamUnreachableError`` und nicht darunter: Dort ist die
    Quelle nicht erreichbar, hier hat sie geantwortet und ihre Form geändert.
    Die Behebung ist eine andere — Warten hilft beim einen, beim anderen nie.
    """


def ckan_result(data: object, action: str) -> dict:
    """Den ``result``-Block einer CKAN-Antwort holen, oder laut scheitern.

    ``data.get("result") or {}`` schrieb jede Strukturänderung in ein gültiges
    leeres Ergebnis um: Die Suche gelang, die Trefferliste war leer, und für das
    Modell war das nicht von «opendata.swiss kennt das nicht» zu unterscheiden
    (FID-006).

    Der ``or {}``-Zweig war dabei noch etwas weiter gefasst als ein Default —
    er verschluckte auch ein ``result: null``, also genau den Fall, in dem die
    Quelle ausdrücklich sagt, dass sie nichts hat.
    """
    if not isinstance(data, dict):
        raise UpstreamSchemaError(
            f"CKAN `{action}`: Antwort ist {type(data).__name__} und kein Objekt."
        )
    if "result" not in data:
        raise UpstreamSchemaError(
            f"CKAN `{action}`: Antwort ohne `result`. Vorhandene Schlüssel: "
            f"{sorted(data)}. Das ist keine Leermenge — die Struktur der Quelle "
            "hat sich geändert."
        )
    result = data["result"]
    if not isinstance(result, dict):
        raise UpstreamSchemaError(
            f"CKAN `{action}`: `result` ist {type(result).__name__} und kein Objekt."
        )
    if "results" not in result:
        raise UpstreamSchemaError(
            f"CKAN `{action}`: `result` ohne `results`. Vorhandene Schlüssel: "
            f"{sorted(result)}. `package_search` liefert `results` auch bei null "
            "Treffern — dies ist keine leere Suche."
        )
    return result


def sparql_bindings(payload: object) -> list:
    """Die Bindings einer SPARQL-JSON-Antwort, oder laut scheitern (FID-006).

    ``resp.json().get("results", {}).get("bindings", [])`` machte aus jeder
    Strukturänderung null Zeilen — und damit aus einem Fehler eine gültige
    Aussage über die Schweizer Stromtarife.

    Die Form ist hier nicht geraten: Die SPARQL-1.1-Results-Empfehlung des W3C
    schreibt ``results.bindings`` vor, auch für ein leeres Ergebnis. Fehlt es,
    hat nicht LINDAS nichts gefunden — dann ist die Antwort keine
    SPARQL-Antwort mehr (etwa eine Fehlerseite mit HTTP 200).
    """
    if not isinstance(payload, dict):
        raise UpstreamSchemaError(
            f"LINDAS SPARQL: Antwort ist {type(payload).__name__} und kein Objekt."
        )
    if "results" not in payload:
        raise UpstreamSchemaError(
            f"LINDAS SPARQL: Antwort ohne `results`. Vorhandene Schlüssel: "
            f"{sorted(payload)}. SPARQL 1.1 schreibt `results.bindings` vor, "
            "auch für ein leeres Ergebnis — dies ist keine leere Abfrage."
        )
    results = payload["results"]
    if not isinstance(results, dict) or "bindings" not in results:
        raise UpstreamSchemaError(
            "LINDAS SPARQL: `results` ohne `bindings`. Vorhanden: "
            f"{sorted(results) if isinstance(results, dict) else type(results).__name__}."
        )
    return results["bindings"]


class EgressNotAllowedError(ValueError):
    """Raised when an outbound request targets a non-allow-listed host or scheme."""


def assert_url_allowed(url: str) -> None:
    """Pre-request gate (SEC-004/005/021): enforce HTTPS + host allow-list.

    Raises EgressNotAllowedError for any non-HTTPS scheme or any host that is
    not in ALLOWED_HOSTS. Call this before every outbound request.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise EgressNotAllowedError(
            f"Only HTTPS is allowed, got scheme {parsed.scheme!r} for {url!r}"
        )
    host = parsed.hostname
    if host not in ALLOWED_HOSTS:
        raise EgressNotAllowedError(
            f"Host {host!r} is not in the egress allow-list {sorted(ALLOWED_HOSTS)}"
        )


def _sparql_escape_literal(value: str) -> str:
    """Escape a string for safe inclusion in a SPARQL double-quoted literal.

    Prevents SPARQL injection (SEC-018) via interpolated tool arguments such as
    canton/category. Control characters are rejected outright; backslash and
    double-quote are escaped per SPARQL 1.1 string-literal grammar.
    """
    if any(ord(c) < 0x20 for c in value):
        raise ValueError("Control characters are not allowed in query values")
    return value.replace("\\", "\\\\").replace('"', '\\"')


# SEC-018: ElCom Verbrauchskategorien form a closed enumeration. The `category`
# tool argument is validated against this allow-list before it ever reaches a
# SPARQL query, rejecting typos and injection attempts alike.
VALID_CATEGORY_CODES: frozenset[str] = frozenset(
    {"H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "C1", "C2", "C3", "C4", "C5", "C6", "C7"}
)


def _category_filter(category: str | None) -> str:
    """Build a validated, escaped SPARQL FILTER clause for a category code."""
    if not category:
        return ""
    if category not in VALID_CATEGORY_CODES:
        raise ValueError(
            f"Unknown category {category!r}; expected one of {sorted(VALID_CATEGORY_CODES)}"
        )
    return f'FILTER(STR(?categoryCode) = "{_sparql_escape_literal(category)}")'


async def _fetch_with_retry(
    http: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs: Any,
) -> httpx.Response:
    """Retry 3 times on 5xx + network errors; 4xx (except 429) raise immediately."""
    assert_url_allowed(url)
    last_error: Exception | None = None
    deadline = time.monotonic() + RETRY_TOTAL_BUDGET
    attempts = 0

    for attempt in range(MAX_RETRIES + 1):
        if attempt > 0:
            delay = compute_delay(attempt, last_error)
            # A wait that outlasts the budget is a wait for nobody: the caller
            # has given up by the time it ends. Stop instead of sleeping.
            if delay >= deadline - time.monotonic():
                break
            await asyncio.sleep(delay)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        attempts += 1
        try:
            # httpx bounds each operation and restarts its read timeout with
            # every chunk, so a slowly trickling response outlives a
            # per-operation limit without any single read expiring — a real
            # risk here, where a SPARQL result set can be large.
            # `asyncio.timeout` is the wall-clock deadline the budget promises.
            async with asyncio.timeout(remaining):
                resp = await http.request(method, url, **kwargs)
                resp.raise_for_status()
                return resp
        except TimeoutError as exc:  # the budget is gone, not just this try
            last_error = exc
            break
        except httpx.HTTPStatusError as exc:
            last_error = exc
            status = exc.response.status_code
            if 400 <= status < 500 and status != 429:
                raise
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            last_error = exc

    # OBS-002: log the internal detail server-side, return a generic message to
    # the client so no stacktrace / internal repr leaks through the tool result.
    #
    # `repr(last_error)` and not `str(last_error)` — which this line already had
    # right. `httpx.ConnectTimeout`, `ReadTimeout` and `ConnectError` carry an
    # EMPTY `str()` and are the only errors a real outage produces, so a
    # `str()`-based line would name nothing; `repr` keeps the type. New is which
    # of the two limits ran out: "all attempts used" and "the budget ran out
    # after 2" call for different fixes.
    get_logger().error(
        "upstream_unreachable",
        url=url,
        method=method,
        attempts=attempts,
        limit="attempts" if attempts >= MAX_RETRIES + 1 else "time_budget",
        error=repr(last_error),
    )
    raise UpstreamUnreachableError(
        "Upstream temporarily unavailable after retries; see server logs."
    ) from last_error


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now_iso() -> str:
    """Public re-export."""
    return _utc_now_iso()


class _TTLCache:
    """Simple in-process TTL cache."""

    def __init__(self, default_ttl_seconds: int = 300) -> None:
        self._store: dict[str, tuple[float, Any]] = {}
        self._default_ttl = default_ttl_seconds

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        self._store[key] = (time.monotonic() + ttl, value)

    def clear(self) -> None:
        self._store.clear()


class EnergyDashboardClient:
    """Client for the BFE Energie-Dashboard API."""

    PRODUCTION_MIX = "/strom/strom-produktionsmix"
    CONSUMPTION_FORECAST = "/strom/v2/strom-verbrauch/landesverbrauch-mit-prognose"
    STORAGE_LAKES = "/strom/v2/fuellungsgrad-speicherseen"
    CONSUMER_PRICE_INDEX = "/preise/strom-endverbrauch"

    def __init__(
        self,
        http: httpx.AsyncClient | None = None,
        cache: _TTLCache | None = None,
    ) -> None:
        self._http = http or httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT,
            headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"},
        )
        self._owns_http = http is None
        self._cache = cache or _TTLCache(default_ttl_seconds=600)

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def _get(self, path: str, ttl: int = 600) -> tuple[Any, str]:
        cached = self._cache.get(path)
        if cached is not None:
            return cached, "cached"
        resp = await _fetch_with_retry(self._http, "GET", f"{DASHBOARD_BASE}{path}")
        data = resp.json()
        self._cache.set(path, data, ttl_seconds=ttl)
        return data, "live_api"

    async def get_production_mix(self) -> tuple[dict, str, str]:
        data, prov = await self._get(self.PRODUCTION_MIX)
        return data, prov, _utc_now_iso()

    async def get_consumption_forecast(self) -> tuple[dict, str, str]:
        data, prov = await self._get(self.CONSUMPTION_FORECAST)
        return data, prov, _utc_now_iso()

    async def get_storage_lakes(self) -> tuple[dict, str, str]:
        data, prov = await self._get(self.STORAGE_LAKES)
        return data, prov, _utc_now_iso()

    async def get_consumer_price_index(self) -> tuple[list[dict], str, str]:
        data, prov = await self._get(self.CONSUMER_PRICE_INDEX)
        return data, prov, _utc_now_iso()

    @staticmethod
    def attribution() -> str:
        return ATTRIBUTION_BFE


class ElComSparqlClient:
    """Client for ElCom electricity-price cubes via LINDAS SPARQL."""

    CATEGORIES: list[dict[str, str]] = [
        {"code": "H1", "desc": "Wohnung mit 2 Zimmern (1'600 kWh/a)", "kwh": "1600"},
        {"code": "H2", "desc": "4-Zimmer-Wohnung mit Elektroherd (2'500 kWh/a)", "kwh": "2500"},
        {
            "code": "H3",
            "desc": "4-Zimmer-Wohnung mit Elektroherd und Boiler (4'500 kWh/a)",
            "kwh": "4500",
        },
        {
            "code": "H4",
            "desc": "5-Zimmer-Wohnung mit Elektroherd, Boiler, Tumbler (4'500 kWh/a)",
            "kwh": "4500",
        },
        {
            "code": "H5",
            "desc": "5-Zimmer-Einfamilienhaus mit Elektroherd, Boiler, Tumbler (7'500 kWh/a)",
            "kwh": "7500",
        },
        {
            "code": "H6",
            "desc": "5-Zimmer-Einfamilienhaus mit Elektroherd und Elektroboiler-Heizung (25'000 kWh/a)",
            "kwh": "25000",
        },
        {
            "code": "H7",
            "desc": "5-Zimmer-Einfamilienhaus mit Waermepumpe (13'000 kWh/a)",
            "kwh": "13000",
        },
        {"code": "H8", "desc": "Grosser Haushalt mit hohem Verbrauch (7'500 kWh/a)", "kwh": "7500"},
        {"code": "C1", "desc": "Kleiner Gewerbebetrieb (8'000 kWh/a)", "kwh": "8000"},
        {"code": "C2", "desc": "Mittlerer Gewerbebetrieb (30'000 kWh/a)", "kwh": "30000"},
        {
            "code": "C3",
            "desc": "Groesserer Gewerbebetrieb (150'000 kWh/a, z. B. Schule)",
            "kwh": "150000",
        },
        {
            "code": "C4",
            "desc": "Grosser Gewerbebetrieb mit Niederspannungsmessung (500'000 kWh/a)",
            "kwh": "500000",
        },
        {
            "code": "C5",
            "desc": "Grosser Gewerbebetrieb mit Mittelspannungsmessung (500'000 kWh/a)",
            "kwh": "500000",
        },
        {
            "code": "C6",
            "desc": "Grosser Gewerbebetrieb mit Mittelspannungsmessung (1'500'000 kWh/a)",
            "kwh": "1500000",
        },
        {
            "code": "C7",
            "desc": "Grossbetrieb mit eigener Transformatorenstation (7'500'000 kWh/a)",
            "kwh": "7500000",
        },
    ]

    def __init__(
        self,
        http: httpx.AsyncClient | None = None,
        cache: _TTLCache | None = None,
    ) -> None:
        self._http = http or httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "application/sparql-results+json",
            },
        )
        self._owns_http = http is None
        self._cache = cache or _TTLCache(default_ttl_seconds=3600)

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def _sparql(self, query: str) -> tuple[list[dict], str]:
        cache_key = query.strip()
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached, "cached"
        resp = await _fetch_with_retry(self._http, "GET", LINDAS_SPARQL, params={"query": query})
        bindings = sparql_bindings(resp.json())
        self._cache.set(cache_key, bindings)
        return bindings, "sparql"

    async def get_tariffs_by_municipality(
        self,
        bfs_nr: int,
        category: str | None = None,
        period_from: int | None = None,
        period_to: int | None = None,
        limit: int = 100,
    ) -> tuple[list[dict], str, str]:
        category_filter = _category_filter(category)
        period_filter = ""
        if period_from is not None:
            period_filter += f"FILTER(?period >= {period_from}) "
        if period_to is not None:
            period_filter += f"FILTER(?period <= {period_to}) "
        query = f"""
PREFIX schema: <http://schema.org/>
SELECT ?period ?categoryCode ?productLabel ?operator ?operatorLabel
       ?total ?energy ?gridusage ?charge ?aidfee
       ?energyName ?gridusageName ?munLabel
WHERE {{
  ?obs <https://energy.ld.admin.ch/elcom/electricityprice/dimension/period> ?period ;
       <https://energy.ld.admin.ch/elcom/electricityprice/dimension/municipality> <https://ld.admin.ch/municipality/{bfs_nr}> ;
       <https://energy.ld.admin.ch/elcom/electricityprice/dimension/category> ?category ;
       <https://energy.ld.admin.ch/elcom/electricityprice/dimension/operator> ?operator ;
       <https://energy.ld.admin.ch/elcom/electricityprice/dimension/product> ?product ;
       <https://energy.ld.admin.ch/elcom/electricityprice/measure/total> ?total .
  OPTIONAL {{ ?obs <https://energy.ld.admin.ch/elcom/electricityprice/measure/energy> ?energy }}
  OPTIONAL {{ ?obs <https://energy.ld.admin.ch/elcom/electricityprice/measure/gridusage> ?gridusage }}
  OPTIONAL {{ ?obs <https://energy.ld.admin.ch/elcom/electricityprice/measure/charge> ?charge }}
  OPTIONAL {{ ?obs <https://energy.ld.admin.ch/elcom/electricityprice/measure/aidfee> ?aidfee }}
  OPTIONAL {{ ?obs <https://energy.ld.admin.ch/elcom/electricityprice/measure/energyname> ?energyName }}
  OPTIONAL {{ ?obs <https://energy.ld.admin.ch/elcom/electricityprice/measure/gridusagename> ?gridusageName }}
  BIND(REPLACE(STR(?category), ".*/", "") AS ?categoryCode)
  BIND(REPLACE(STR(?product), ".*/", "") AS ?productLabel)
  OPTIONAL {{ <https://ld.admin.ch/municipality/{bfs_nr}> schema:name ?munLabel }}
  OPTIONAL {{ ?operator schema:name ?operatorLabel }}
  {category_filter}
  {period_filter}
}}
ORDER BY DESC(?period) ?categoryCode
LIMIT {limit}
"""
        bindings, prov = await self._sparql(query)
        return bindings, prov, _utc_now_iso()

    async def get_median_swiss(
        self,
        category: str | None = None,
        period_from: int | None = None,
        period_to: int | None = None,
        limit: int = 200,
    ) -> tuple[list[dict], str, str]:
        category_filter = _category_filter(category)
        period_filter = ""
        if period_from is not None:
            period_filter += f"FILTER(?period >= {period_from}) "
        if period_to is not None:
            period_filter += f"FILTER(?period <= {period_to}) "
        query = f"""
SELECT ?period ?categoryCode ?total
WHERE {{
  ?obs <https://energy.ld.admin.ch/elcom/electricityprice-swiss/dimension/period> ?period ;
       <https://energy.ld.admin.ch/elcom/electricityprice-swiss/dimension/category> ?category ;
       <https://energy.ld.admin.ch/elcom/electricityprice-swiss/measure/total> ?total .
  BIND(REPLACE(STR(?category), ".*/", "") AS ?categoryCode)
  {category_filter}
  {period_filter}
}}
ORDER BY DESC(?period) ?categoryCode
LIMIT {limit}
"""
        bindings, prov = await self._sparql(query)
        return bindings, prov, _utc_now_iso()

    async def get_median_canton(
        self,
        canton: str,
        category: str | None = None,
        period_from: int | None = None,
        period_to: int | None = None,
        limit: int = 200,
    ) -> tuple[list[dict], str, str]:
        category_filter = _category_filter(category)
        period_filter = ""
        if period_from is not None:
            period_filter += f"FILTER(?period >= {period_from}) "
        if period_to is not None:
            period_filter += f"FILTER(?period <= {period_to}) "
        query = f"""
PREFIX schema: <http://schema.org/>
SELECT ?period ?categoryCode ?total ?cantonLabel
WHERE {{
  ?obs <https://energy.ld.admin.ch/elcom/electricityprice-canton/dimension/period> ?period ;
       <https://energy.ld.admin.ch/elcom/electricityprice-canton/dimension/canton> ?cantonURI ;
       <https://energy.ld.admin.ch/elcom/electricityprice-canton/dimension/category> ?category ;
       <https://energy.ld.admin.ch/elcom/electricityprice-canton/measure/total> ?total .
  ?cantonURI schema:name ?cantonLabel .
  FILTER(STR(?cantonLabel) = "{_sparql_escape_literal(canton)}")
  BIND(REPLACE(STR(?category), ".*/", "") AS ?categoryCode)
  {category_filter}
  {period_filter}
}}
ORDER BY DESC(?period) ?categoryCode
LIMIT {limit}
"""
        bindings, prov = await self._sparql(query)
        return bindings, prov, _utc_now_iso()

    @staticmethod
    def attribution() -> str:
        return ATTRIBUTION_ELCOM


class CkanDiscoveryClient:
    """CKAN client for opendata.swiss and Stadt Zuerich OGD."""

    def __init__(
        self,
        http: httpx.AsyncClient | None = None,
        cache: _TTLCache | None = None,
    ) -> None:
        self._http = http or httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT,
            headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"},
        )
        self._owns_http = http is None
        self._cache = cache or _TTLCache(default_ttl_seconds=3600)

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def search_opendata_swiss(
        self,
        query: str,
        rows: int = 20,
        offset: int = 0,
        bfe_only: bool = False,
    ) -> tuple[dict, str, str]:
        params: dict[str, Any] = {"q": query, "rows": rows, "start": offset}
        if bfe_only:
            params["fq"] = "organization:bundesamt-fur-energie-bfe"
        cache_key = f"opendata:{query}:{rows}:{offset}:{bfe_only}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached, "cached", _utc_now_iso()
        resp = await _fetch_with_retry(
            self._http, "GET", f"{OPENDATA_SWISS_CKAN}/package_search", params=params
        )
        data = resp.json()
        self._cache.set(cache_key, data)
        return data, "live_api", _utc_now_iso()

    async def search_zurich(
        self,
        query: str,
        rows: int = 20,
        offset: int = 0,
    ) -> tuple[dict, str, str]:
        params = {"q": query, "rows": rows, "start": offset}
        cache_key = f"zurich:{query}:{rows}:{offset}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached, "cached", _utc_now_iso()
        resp = await _fetch_with_retry(
            self._http, "GET", f"{ZURICH_OGD_CKAN}/package_search", params=params
        )
        data = resp.json()
        self._cache.set(cache_key, data)
        return data, "live_api", _utc_now_iso()

    @staticmethod
    def attribution_opendata() -> str:
        return ATTRIBUTION_OPENDATA_SWISS

    @staticmethod
    def attribution_zurich() -> str:
        return ATTRIBUTION_ZURICH


def sparql_value(binding: dict, key: str) -> Any | None:
    """Extract value from a SPARQL binding dict; coerce numeric datatypes."""
    entry = binding.get(key)
    if entry is None:
        return None
    value = entry.get("value")
    if value is None or value == "":
        return None
    datatype = entry.get("datatype", "")
    if "decimal" in datatype or "float" in datatype or "double" in datatype:
        try:
            return float(value)
        except ValueError:
            return None
    if "integer" in datatype or "int" in datatype:
        try:
            return int(value)
        except ValueError:
            return None
    return value
