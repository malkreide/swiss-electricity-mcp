"""Die Verarbeitung gegen aufgezeichnete Antworten der echten Quellen halten.

WARUM ES DIESE DATEI GIBT. Die uebrigen Testmodule pruefen gegen
handgeschriebene Payloads. Die stammen aus derselben Lektuere der Doku wie der
Produktivcode; wo beide irren, irren beide gleich, und die Suite bleibt gruen.

Genau so sind zwei Fehler unbemerkt geblieben, und beide sind Namensfehler:

* Die ElCom-Cubes haben ihren Praedikat-Namensraum gewechselt. Die Abfragen
  fragten weiter nach `.../measure/total`, bekamen HTTP 200 und **null Zeilen**
  — fuer jede Gemeinde, jeden Kanton, jedes Jahr.
* Vier der fuenf angebotenen Speicherseen-Regionen trafen keinen Schluessel der
  Quelle. Der Rueckfall lieferte die Schweizer Zahlen, und die Antwort trug
  trotzdem den Namen der Region.

Beides sieht in einer erfundenen Fixture nicht anders aus als der Erfolg, denn
die erfundene Fixture benutzt dieselben Namen wie der Code.

WAS SIE NICHT KOENNEN: Sie sind ein datierter Ausschnitt, kein Abonnement.
Wechselt LINDAS morgen erneut den Namensraum, faellt das hier nicht auf —
dafuer ist die Live-Suite da.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from types import SimpleNamespace

import httpx
import pytest

from swiss_electricity_mcp import api_client, server
from tests.fixture_data import FIXTURES, bindings, payload

ELCOM_NS = "https://energy.ld.admin.ch/elcom/electricityprice/dimension/"


class _Capture(httpx.AsyncBaseTransport):
    """Faengt die Abfrage ab, die der Produktivcode baut."""

    def __init__(self, response: dict) -> None:
        self.queries: list[str] = []
        self._response = response

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.queries.append(dict(httpx.QueryParams(request.url.query.decode())).get("query", ""))
        return httpx.Response(200, json=self._response, request=request)


async def _query_for(method: str, *args, **kwargs) -> str:
    """Die SPARQL-Abfrage, die eine Client-Methode absendet."""
    capture = _Capture({"results": {"bindings": []}})
    client = api_client.ElComSparqlClient(http=httpx.AsyncClient(transport=capture))
    try:
        await getattr(client, method)(*args, **kwargs)
    finally:
        await client.aclose()
    return capture.queries[-1]


# ---------------------------------------------------------------------------
# Der ElCom-Namensraum
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,args",
    [
        ("get_tariffs_by_municipality", (261,)),
        ("get_median_swiss", ()),
        ("get_median_canton", ("Luzern",)),
    ],
)
async def test_no_query_asks_for_a_namespace_that_is_gone(method, args):
    """Kein `measure/`, kein cube-eigener Namensraum.

    Beides gab es einmal und gibt es nicht mehr. Eine Abfrage dagegen ist kein
    Fehler: Sie bekommt HTTP 200 und null Zeilen, und das Werkzeug meldet
    «keine Daten» — ein Ausfall, der wie eine Antwort aussieht.
    """
    query = await _query_for(method, *args)
    assert "/elcom/electricityprice/measure/" not in query, "der `measure/`-Namensraum ist weg"
    for gone in ("electricityprice-swiss/dimension", "electricityprice-canton/dimension"):
        assert gone not in query, f"`{gone}` gibt es nicht mehr; alle Cubes teilen sich einen"


@pytest.mark.parametrize(
    "method,args,cube",
    [
        ("get_median_swiss", (), api_client.ELCOM_CUBE_SWISS),
        ("get_median_canton", ("Luzern",), api_client.ELCOM_CUBE_CANTON),
    ],
)
async def test_the_median_queries_name_their_cube(method, args, cube):
    """Ohne Eingrenzung waere der Median ueber die falsche Grundmenge.

    Seit alle drei Cubes denselben Praedikat-Namensraum benutzen, unterscheidet
    sie nur noch `cube.link/observationSet`. Fehlt die Klammer, kaemen die
    Gemeinde-Beobachtungen mit — und nichts an der Antwort wuerde es verraten.
    """
    query = await _query_for(method, *args)
    assert cube in query, f"Abfrage grenzt den Cube {cube} nicht ein"
    assert "cube.link/observationSet" in query


def test_the_recorded_answer_actually_has_rows():
    """Die Fixture belegt, dass die Abfrage etwas findet.

    Vor der Korrektur war die echte Antwort auf dieselbe Frage leer. Genau
    deshalb ist eine aufgezeichnete Antwort hier mehr wert als eine erfundene:
    Eine erfundene haette nie leer sein koennen.
    """
    for name in (
        "lindas_tariffs_municipality.json",
        "lindas_median_swiss.json",
        "lindas_median_canton.json",
    ):
        rows = bindings(name)
        assert rows, f"{name}: keine Zeilen — dann prueft die Fixture nichts"
        assert api_client.sparql_value(rows[0], "total") is not None, (
            f"{name}: erste Zeile ohne `total`"
        )


def test_recorded_bindings_parse_into_values():
    """Die aufgezeichneten Werte kommen als Zahlen an, nicht als Strings."""
    rows = bindings("lindas_tariffs_municipality.json")
    total = api_client.sparql_value(rows[0], "total")
    assert isinstance(total, (int, float)), f"total ist {type(total).__name__}: {total!r}"
    assert 0 < float(total) < 200, f"Rappen pro kWh ausserhalb jedes plausiblen Bereichs: {total}"
    period = api_client.sparql_value(rows[0], "period")
    assert int(period) >= 2000, period


# ---------------------------------------------------------------------------
# Die Periodengrenzen
# ---------------------------------------------------------------------------

# Ein Vergleich, der `?period` unverpackt gegen etwas haelt. Die Form, die den
# Ausfall erzeugt hat; `STR(?period)` und `DESC(?period)` trifft sie nicht.
_ROHER_PERIODENVERGLEICH = re.compile(r"\?period\s*(?:<=|>=|<|>|=)")

_PERIODEN_ABFRAGEN = [
    ("get_tariffs_by_municipality", (261,)),
    ("get_median_swiss", ()),
    ("get_median_canton", ("Luzern",)),
]


def test_the_recorded_answer_types_period_as_gyear():
    """Die Praemisse der drei Tests darunter, aus der Quelle statt aus dem Kopf.

    Sie sagen, `?period` duerfe nicht unverpackt verglichen werden. Warum nicht,
    steht hier: Die Quelle liefert die Periode als `gYear`, nicht als Zahl. Ohne
    diesen Beleg waeren es drei Tests, die eine Annahme gegen sich selbst
    pruefen.
    """
    gyear = "http://www.w3.org/2001/XMLSchema#gYear"
    for name in (
        "lindas_tariffs_municipality.json",
        "lindas_median_swiss.json",
        "lindas_median_canton.json",
    ):
        for row in bindings(name):
            assert row["period"]["datatype"] == gyear, (
                f"{name}: `period` ist {row['period'].get('datatype')!r}. "
                "Wechselt die Quelle den Typ, ist der Filter neu zu belegen."
            )


@pytest.mark.parametrize("method,args", _PERIODEN_ABFRAGEN)
async def test_period_bounds_never_compare_the_raw_term(method, args):
    """`FILTER(?period >= 2019)` vergleicht gYear mit Integer.

    Das ist nach SPARQL 1.1 kein Vergleich, sondern ein Typfehler, und ein
    FILTER mit fehlgeschlagenem Ausdruck verwirft die Zeile. Die Antwort ist
    HTTP 200 mit null Zeilen — wieder ein Ausfall in der Form einer Auskunft.
    Alle drei ElCom-Werkzeuge lieferten so leere Ergebnisse, sobald jemand einen
    Zeitraum angab, und keine Fixture konnte es sehen: Aufgezeichnet wurde ohne
    Periodenfilter.
    """
    query = await _query_for(method, *args, period_from=2019, period_to=2025)
    treffer = _ROHER_PERIODENVERGLEICH.search(query)
    assert treffer is None, f"unverpackter Periodenvergleich: {treffer.group(0)!r}"
    assert api_client._PERIOD_AS_INT in query, "die Periode wird nicht numerisch verglichen"


@pytest.mark.parametrize("method,args", _PERIODEN_ABFRAGEN)
async def test_both_period_bounds_reach_the_query(method, args):
    """Eine stillschweigend fallengelassene Grenze liefert zu viel, nicht zu wenig.

    Und zu viel faellt niemandem auf: Die Antwort ist nicht leer, sie umfasst
    nur einen anderen Zeitraum als den erfragten.
    """
    query = await _query_for(method, *args, period_from=2019, period_to=2025)
    assert f"{api_client._PERIOD_AS_INT} >= 2019" in query, "untere Grenze fehlt"
    assert f"{api_client._PERIOD_AS_INT} <= 2025" in query, "obere Grenze fehlt"

    ohne = await _query_for(method, *args)
    assert ">= 2019" not in ohne and "<= 2025" not in ohne, (
        "ohne Grenzen darf kein Periodenfilter in der Abfrage stehen"
    )


@pytest.mark.parametrize("method,args", _PERIODEN_ABFRAGEN)
async def test_a_query_using_xsd_declares_the_prefix(method, args):
    """Fuseki kennt `xsd:` vordefiniert. Das ist keine Zusicherung von SPARQL 1.1.

    Faellt die Deklaration weg, laeuft es gegen LINDAS weiter und gegen jeden
    anderen Endpunkt nicht mehr — ein Fehler, den ausgerechnet die Quelle
    verdeckt, gegen die geprueft wird.
    """
    query = await _query_for(method, *args, period_from=2019)
    assert "xsd:" in query, "Test prueft nichts mehr: die Abfrage benutzt gar kein `xsd:`"
    assert api_client.SPARQL_PREFIX_XSD in query, "`xsd:` benutzt, aber nicht deklariert"


@pytest.mark.parametrize("bound", [2019.7, "2019", True, None.__class__])
def test_a_non_integer_period_bound_is_refused(bound):
    """Die Grenzen landen unquotiert in der Abfrage.

    `server.py` typisiert sie als `int`, der Client ist aber auch direkt
    aufrufbar. Ein `int()`-Cast machte aus 2019.7 klaglos 2019 und beantwortete
    eine andere Frage als die gestellte.
    """
    with pytest.raises(ValueError):
        api_client._period_filter(bound, None)
    with pytest.raises(ValueError):
        api_client._period_filter(None, bound)


def test_the_recording_itself_went_through_the_period_filter():
    """Die Aufnahme muss die Klausel benutzen, sonst belegt sie nichts ueber sie.

    Aufgezeichnet wurde urspruenglich ohne Periodengrenze. Deshalb konnte keine
    Fixture den kaputten Vergleich sehen, und deshalb ist der Ausfall erst der
    Live-Suite aufgefallen — Wochen spaeter. `record_fixtures.py` setzt die
    Grenze nun, und `record()` bricht bei einer leeren Antwort laut ab: Der
    Fehler faellt dann beim Aufzeichnen auf statt im Betrieb.

    Geprueft wird die aufgezeichnete Abfrage, nicht die Antwort. Ob der Filter
    gewirkt hat, sieht man einer Zeile nicht an; ob er in der Abfrage stand,
    schon.
    """
    provenance = (FIXTURES / "PROVENANCE.md").read_text(encoding="utf-8")
    quellen = [
        urllib.parse.unquote_plus(zeile)
        for zeile in provenance.splitlines()
        if zeile.startswith("- **Quelle:**") and "lindas.admin.ch" in zeile
    ]
    assert len(quellen) == 3, f"drei LINDAS-Aufnahmen erwartet, {len(quellen)} gefunden"
    for quelle in quellen:
        assert api_client._PERIOD_AS_INT in quelle, (
            "aufgezeichnete LINDAS-Abfrage ohne Periodenfilter — "
            "neu aufzeichnen mit `python scripts/record_fixtures.py`"
        )
        assert api_client.SPARQL_PREFIX_XSD in quelle, "aufgezeichnete Abfrage ohne `xsd:`-Praefix"


async def _storage_lakes_from_fixture(
    *,
    region: str = "totalCH",
    limit_weeks: int = 52,
    response_format: str = "json",
    payload_override: dict | None = None,
) -> str:
    """Ruft das Werkzeug mit der aufgezeichneten Antwort auf.

    Geprueft wird am Werkzeug, nicht am Ausschnitt: Dass die Fixture die
    Platzhalter traegt, sagt nichts darueber, ob der Server sie ueberspringt.
    """
    data = (
        payload_override
        if payload_override is not None
        else payload("dashboard_storage_lakes.json")
    )

    class _Ctx:
        def __init__(self) -> None:
            dashboard = api_client.EnergyDashboardClient()

            async def _fixed() -> tuple[dict, str, str]:
                return data, "live_api", "2026-08-07T00:00:00Z"

            dashboard.get_storage_lakes = _fixed  # type: ignore[method-assign]
            app = server.AppContext(
                dashboard=dashboard,
                elcom=api_client.ElComSparqlClient(),
                ckan=api_client.CkanDiscoveryClient(),
            )
            self.request_context = SimpleNamespace(lifespan_context=app)

        async def info(self, *args, **kwargs) -> None:
            return None

        async def report_progress(self, *args, **kwargs) -> None:
            return None

    return await server.dashboard_get_storage_lakes(
        ctx=_Ctx(), region=region, limit_weeks=limit_weeks, response_format=response_format
    )


# ---------------------------------------------------------------------------
# Die Speicherseen-Regionen
# ---------------------------------------------------------------------------


def test_every_offered_region_maps_to_a_key_the_source_has():
    """Was das Werkzeug anbietet, muss die Quelle auch fuehren.

    Vier der fuenf Werte trafen frueher keinen Schluessel. Der stille Rueckfall
    auf `totalCH` lieferte daraufhin Schweizer Zahlen unter dem Namen der
    Region — richtig aussehende Daten mit falschem Etikett.
    """
    data = payload("dashboard_storage_lakes.json")
    for region, key in server.STORAGE_LAKE_REGION_KEYS.items():
        assert key in data, f"Region {region!r} zeigt auf {key!r}, die Quelle fuehrt {sorted(data)}"


def test_the_offered_regions_are_the_documented_ones():
    """Die Zuordnung deckt genau die Werte ab, die das Werkzeug annimmt.

    Ein Wert ohne Eintrag flaege beim Aufruf als `KeyError` — laut, aber erst
    beim Nutzer. Hier faellt es vorher auf.
    """
    documented = {"totalCH", "Wallis", "Tessin", "Graubuenden", "ZentralOst"}
    assert set(server.STORAGE_LAKE_REGION_KEYS) == documented


def test_the_regions_are_not_all_the_same_block():
    """Die Gegenprobe: Die Zuordnung darf nicht alles auf `totalCH` schicken.

    Eine Abbildung, die jede Region auf denselben Schluessel legt, bestuende
    den Test darueber und waere genau der alte Fehler mit einer Tabelle davor.
    """
    data = payload("dashboard_storage_lakes.json")
    keys = set(server.STORAGE_LAKE_REGION_KEYS.values())
    assert len(keys) == len(server.STORAGE_LAKE_REGION_KEYS), "zwei Regionen auf einem Schluessel"
    fills = {key: (data[key].get("currentEntry") or {}).get("speicherstandProzent") for key in keys}
    assert len({v for v in fills.values() if v is not None}) > 1, (
        f"alle Regionen melden denselben Fuellstand: {fills}"
    )


# ---------------------------------------------------------------------------
# Die uebrigen Quellen
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["ckan_opendata_swiss_search.json", "ckan_zurich_search.json"])
def test_ckan_count_is_the_catalogue_not_the_page(name):
    """`count` ist der Bestand, `results` die Seite."""
    result = api_client.ckan_result(payload(name), "package_search")
    assert result["results"], "keine Treffer aufgezeichnet"
    assert result["count"] > len(result["results"]), (
        f"count={result['count']} bei {len(result['results'])} Treffern — "
        "die Fixture belegt den Unterschied nicht mehr"
    )


def test_ckan_shape_change_is_loud():
    """Eine Antwort ohne `result` ist keine Leermenge (FID-006)."""
    with pytest.raises(api_client.UpstreamSchemaError):
        api_client.ckan_result({"success": True, "help": "…"}, "package_search")


def test_the_fixture_still_carries_the_placeholders():
    """Ohne die Zeilen ohne Messung prueft alles darunter nichts.

    Die Auswahlregel im Aufzeichnungsskript behaelt sie ausdruecklich. Faellt
    dieser Test, ist die Fixture beim letzten Lauf harmlos geworden.
    """
    entries = payload("dashboard_storage_lakes.json")["totalCH"]["entries"]
    real = [e for e in entries if e.get("speicherstandProzent") is not None]
    empty = [e for e in entries if e.get("speicherstandProzent") is None]
    assert real, "keine Zeile mit Messung"
    assert empty, "keine Platzhalter — dann laesst sich der Fehler nicht festhalten"
    assert entries[-1].get("speicherstandProzent") is None, (
        "die Reihe endet nicht mehr auf einem Platzhalter — Zuschnitt pruefen"
    )
    # Und der Grund, warum «alles null» das falsche Kriterium war: Die
    # Platzhalter tragen sehr wohl Werte, nur keine Messung.
    assert any(e.get("fiveYearMittelwert") is not None for e in empty), (
        "Platzhalter ohne Referenzkurven — dann war das Messfeld-Kriterium unnoetig"
    )


async def test_the_series_skips_the_rows_without_a_measurement():
    """Die Standardantwort darf nicht aus lauter Leerzeilen bestehen.

    Gemessen am 2026-08-07: 455 Eintraege, davon 361 mit Messung und **94
    Platzhalter am Ende**. `entries[-52:]` — der Standardschnitt — traf damit
    52 Zeilen ohne eine einzige Zahl. Die Antwort war formal in Ordnung und
    inhaltlich leer, und nichts daran sagte es.
    """
    out = json.loads(
        await _storage_lakes_from_fixture(region="totalCH", limit_weeks=52, response_format="json")
    )
    series = out["series"]
    assert series, "leere Reihe"
    assert all(row["speicherstand_prozent"] is not None for row in series), (
        f"{sum(1 for r in series if r['speicherstand_prozent'] is None)} von "
        f"{len(series)} Zeilen ohne Messung"
    )


async def test_the_capacity_comes_from_a_row_that_has_one():
    """`capacity_gwh` kam immer als `null` zurueck.

    Gelesen wurde `entries[-1]`, und der letzte Eintrag ist ein Platzhalter.
    Der letzte gemessene Tag weist 8895 GWh aus.
    """
    out = json.loads(await _storage_lakes_from_fixture())
    assert out["capacity_gwh"] is not None, "Kapazitaet weiterhin null"
    assert out["capacity_gwh"] > 1000, out["capacity_gwh"]


async def test_a_region_the_source_does_not_have_is_loud():
    """Kein stiller Rueckfall mehr auf die Schweizer Zahlen."""
    with pytest.raises(api_client.UpstreamSchemaError) as excinfo:
        await _storage_lakes_from_fixture(
            payload_override={"totalCH": {"entries": []}}, region="Wallis"
        )
    assert "wallis" in str(excinfo.value)
