"""Die CKAN-Hülle wird bestätigt, nicht angenommen (FID-006).

Beide CKAN-Suchen schrieben `result = data.get("result") or {}` und lasen danach
`result.get("results", [])`. Fällt `result` weg — weil die Quelle ihre Antwort
umbaut oder die Aktion nie richtig war —, dann gelang die Suche, die
Trefferliste war leer, und `consumption_search_zurich` meldete
`match_type: "none"` samt hilfreichem Vorschlag: die exakt gleiche Antwort wie
bei einer korrekten Suche ohne Treffer.

`or {}` war dabei noch etwas weiter gefasst als ein Default — es verschluckte
auch ein `result: null`, also genau den Fall, in dem die Quelle ausdrücklich
sagt, dass sie nichts hat.

Der Portfolio-Durchlauf am 2026-08-07 fand acht Server, die mit CKAN sprechen;
alle acht prüfen das `success`-Envelope, sieben defaulteten `result` danach.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest
import respx

from swiss_electricity_mcp.api_client import (
    LINDAS_SPARQL,
    OPENDATA_SWISS_CKAN,
    ZURICH_OGD_CKAN,
    CkanDiscoveryClient,
    ElComSparqlClient,
    EnergyDashboardClient,
    UpstreamSchemaError,
    sparql_bindings,
)
from swiss_electricity_mcp.server import (
    AppContext,
    consumption_search_zurich,
)


class FakeCtx:
    def __init__(self) -> None:
        self.progress: list[tuple[int, int]] = []
        app = AppContext(
            dashboard=EnergyDashboardClient(),
            elcom=ElComSparqlClient(),
            ckan=CkanDiscoveryClient(),
        )
        self.request_context = SimpleNamespace(lifespan_context=app)

    async def info(self, *args, **kwargs) -> None:
        return None

    async def report_progress(self, progress: int, total: int) -> None:
        self.progress.append((progress, total))


def _zurich(payload):
    return respx.get(f"{ZURICH_OGD_CKAN}/package_search").mock(
        return_value=httpx.Response(200, json=payload)
    )


# --- Der Fund ----------------------------------------------------------------


@respx.mock
async def test_a_missing_result_is_not_a_search_without_hits():
    """Die Kernzusage.

    Vorher: `match_type: "none"` mit Vorschlag — ununterscheidbar von einer
    korrekten Suche ohne Treffer.
    """
    _zurich({"success": True, "help": "https://data.stadt-zuerich.ch/api/3/"})
    with pytest.raises(UpstreamSchemaError):
        await consumption_search_zurich(ctx=FakeCtx(), query="energie", response_format="json")


@respx.mock
async def test_a_null_result_is_rejected_too():
    """Der Fall, den `or {}` zusätzlich zum Default verschluckte.

    `result: null` ist eine ausdrückliche Aussage der Quelle und kein fehlender
    Schlüssel; `data.get("result") or {}` machte aus beidem dasselbe leere
    Objekt.
    """
    _zurich({"success": True, "result": None})
    with pytest.raises(UpstreamSchemaError):
        await consumption_search_zurich(ctx=FakeCtx(), query="energie", response_format="json")


@respx.mock
async def test_a_result_without_results_is_rejected():
    """Die Ebene darunter zählt genauso.

    `package_search` liefert `results` auch bei null Treffern. Fehlt es, ist das
    eine andere Antwort und keine leere Suche.
    """
    _zurich({"success": True, "result": {"count": 0}})
    with pytest.raises(UpstreamSchemaError) as excinfo:
        await consumption_search_zurich(ctx=FakeCtx(), query="energie", response_format="json")
    assert "results" in str(excinfo.value)


@respx.mock
async def test_the_message_names_the_keys_that_are_actually_there():
    """Ohne die vorhandenen Schlüssel ist der nächste Schritt Raten."""
    _zurich({"success": True, "help": "…", "payload": {}})
    with pytest.raises(UpstreamSchemaError) as excinfo:
        await consumption_search_zurich(ctx=FakeCtx(), query="energie", response_format="json")
    message = str(excinfo.value)
    assert "'help'" in message and "'payload'" in message, message
    assert "keine Leermenge" in message


# --- Die Gegenrichtung, und sie ist die wichtigere Hälfte --------------------


@respx.mock
async def test_a_genuinely_empty_search_still_reports_none():
    """Ein Wächter, der die echte Leermenge mitfängt, wird abgeschaltet.

    Das ist zugleich der Test, der die ARCH-003-Zusage dieses Servers schützt:
    null Treffer müssen weiterhin `match_type: "none"` **mit** Vorschlag
    ergeben, nicht eine Ausnahme.
    """
    _zurich({"success": True, "result": {"count": 0, "results": []}})
    payload = json.loads(
        await consumption_search_zurich(ctx=FakeCtx(), query="zzz-nope", response_format="json")
    )
    assert payload["match_type"] == "none"
    assert payload["suggestion"]
    assert payload["total_hits"] == 0


@respx.mock
async def test_a_normal_search_still_passes():
    _zurich(
        {
            "success": True,
            "result": {
                "count": 1,
                "results": [{"name": "strom", "title": "Stromverbrauch", "notes": "…"}],
            },
        }
    )
    payload = json.loads(
        await consumption_search_zurich(ctx=FakeCtx(), query="energie", response_format="json")
    )
    assert payload["match_type"] == "results"


# --- Der Helfer selbst, an beiden Quellen ------------------------------------


def test_the_helper_names_the_action_so_two_sources_stay_apart():
    """Beide Suchen teilen sich den Helfer — die Meldung muss sagen, welche.

    `opendata.swiss` und `data.stadt-zuerich.ch` sind zwei verschiedene
    CKAN-Instanzen. Eine Meldung, die nur «CKAN» sagt, schickt den Leser in das
    falsche Portal.
    """
    from swiss_electricity_mcp.api_client import ckan_result

    for action, host in (
        ("package_search (opendata.swiss)", "opendata.swiss"),
        ("package_search (data.stadt-zuerich.ch)", "data.stadt-zuerich.ch"),
    ):
        with pytest.raises(UpstreamSchemaError) as excinfo:
            ckan_result({"success": True}, action)
        assert host in str(excinfo.value)


def test_the_helper_is_wired_to_both_call_sites():
    """Ein Helfer, der nur an einer der beiden Stellen hängt, halbiert die Zusage."""
    from pathlib import Path

    source = Path(__file__).parent.parent / "src" / "swiss_electricity_mcp" / "server.py"
    text = source.read_text(encoding="utf-8")
    assert text.count("ckan_result(data,") == 2, (
        "beide CKAN-Suchen müssen über den Helfer laufen — opendata.swiss und data.stadt-zuerich.ch"
    )
    assert 'data.get("result") or {}' not in text


# Sanity: die opendata.swiss-Route existiert und zeigt woanders hin als Zürich.
def test_the_two_ckan_hosts_are_distinct():
    assert OPENDATA_SWISS_CKAN != ZURICH_OGD_CKAN


# --- Die zweite Quelle: LINDAS SPARQL ----------------------------------------


class TestSparqlBindings:
    """`resp.json().get("results", {}).get("bindings", [])` — zwei Defaults.

    Fiel einer weg, kamen null Zeilen heraus: aus einem Fehler wurde eine
    gültige Aussage über die Schweizer Stromtarife. Die Form ist hier nicht
    geraten — SPARQL 1.1 schreibt `results.bindings` vor, auch für ein leeres
    Ergebnis. Fehlt es, hat nicht LINDAS nichts gefunden; dann ist die Antwort
    keine SPARQL-Antwort mehr, etwa eine Fehlerseite mit HTTP 200.
    """

    def test_a_missing_results_is_not_an_empty_query(self):
        with pytest.raises(UpstreamSchemaError) as excinfo:
            sparql_bindings({"head": {"vars": ["x"]}})
        message = str(excinfo.value)
        assert "'head'" in message, message
        assert "keine leere Abfrage" in message

    def test_a_missing_bindings_is_rejected(self):
        with pytest.raises(UpstreamSchemaError) as excinfo:
            sparql_bindings({"results": {"distinct": False}})
        assert "bindings" in str(excinfo.value)

    def test_an_html_error_page_with_http_200_is_rejected(self):
        """Der Fall, den `swiss-courts-mcp` unabhängig entdeckt hat.

        Ein Bot-Schutz oder eine Fehlerseite antwortet mit HTTP 200 und einem
        fremden Körper. Ohne Bestätigung liest sich das wie null Treffer.
        """
        with pytest.raises(UpstreamSchemaError) as excinfo:
            sparql_bindings(["<html>", "Service unavailable"])
        assert "list" in str(excinfo.value)

    def test_an_empty_result_set_still_passes(self):
        """Die Gegenrichtung: LINDAS hat geantwortet und nichts gefunden."""
        assert sparql_bindings({"head": {}, "results": {"bindings": []}}) == []

    def test_a_normal_result_set_still_passes(self):
        rows = [{"total": {"value": "23.45"}}]
        assert sparql_bindings({"results": {"bindings": rows}}) == rows

    def test_the_client_uses_the_helper(self):
        """Ein Helfer, der nirgends hängt, ist Dekoration."""
        from pathlib import Path

        source = Path(__file__).parent.parent / "src" / "swiss_electricity_mcp" / "api_client.py"
        body = source.read_text(encoding="utf-8")
        assert "sparql_bindings(resp.json())" in body
        assert LINDAS_SPARQL in body
