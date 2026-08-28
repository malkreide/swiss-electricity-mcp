#!/usr/bin/env python3
"""Zeichnet die Unit-Test-Fixtures von den echten Quellen dieses Servers auf.

    python scripts/record_fixtures.py

WARUM ES DIESES SKRIPT GIBT. Ein handgeschriebener Mock kodiert die Annahme
seines Autors und kann sie deshalb prinzipiell nicht widerlegen: Produktivcode
und Fixture stammen aus demselben Kopf, derselben Stunde, derselben Lektuere der
Doku. Wo beide irren, irren beide gleich, und die Suite bleibt gruen.

Ohne Aufzeichnungsdatum ist «aufgezeichnet» nach zwei Jahren von «ausgedacht»
nicht mehr zu unterscheiden — die Datei sieht gleich aus.

**Die Anfragen baut hier der Produktivcode selbst.** Das Skript ruft
`ElComSparqlClient` und `DashboardClient` auf und faengt die Antwort ueber einen
httpx-Transport ab, statt die SPARQL-Abfragen daneben noch einmal zu tippen.
Eine Fixture, die eine leicht andere Frage beantwortet als der Server stellt,
belegt die falsche Antwort — und zwar unauffaellig, weil sie plausibel aussieht.
Bei 40 Zeilen SPARQL ist «leicht anders» der Normalfall, nicht die Ausnahme.

**Es sind Ausschnitte, keine Vollabzuege.** Die Auswahlregel je Datei steht in
`tests/fixtures/PROVENANCE.md`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from swiss_electricity_mcp import api_client  # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

# Zuerich. Eine feste Gemeinde, damit jede Aufzeichnung dieselbe Frage stellt —
# «hier» oder «die erste beste» erzeugt bei jedem Lauf einen anderen Diff.
BFS_NR = 261
BFS_NAME = "Zürich"
CANTON = "Luzern"
SPARQL_LIMIT = 5

# Die Aufzeichnung laeuft MIT Periodengrenze, und das ist der Zweck, nicht ein
# Detail der Auswahl. Ohne sie hat keine Fixture je die FILTER-Klausel gesehen —
# und genau dort stand ein Vergleich, der `xsd:gYear` gegen einen Integer hielt
# und deshalb fuer jede Gemeinde, jeden Kanton und jedes Jahr null Zeilen ergab.
# Die Unit-Tests blieben gruen, weil die Klausel in keiner Aufnahme vorkam.
#
# Mit der Grenze bricht `record()` beim naechsten Mal laut ab, statt eine leere
# Antwort aufzuzeichnen. Nur eine Untergrenze: Eine Obergrenze muesste jedes
# Jahr nachgezogen werden, und `ORDER BY DESC(?period)` liefert ohnehin die
# neuesten Zeilen, sodass der Inhalt der Fixture derselbe bleibt.
PERIOD_FROM = 2019
CKAN_ROWS = 3
CKAN_QUERY = "strom"


# Wie viele Wochen-/Tageswerte eine Zeitreihe in der Fixture behaelt.
SERIES_KEEP = 12
# Wie viele der leeren Zukunfts-Platzhalter mitkommen. Sie sind der Grund,
# warum es die Fixture gibt — ohne sie liesse sich der Fehler nicht festhalten.
PLACEHOLDER_KEEP = 3


# Welches Feld eine Messung ausmacht — je Datei ausgeschrieben, nicht geraten.
#
# Der erste Versuch hier war ein generisches «irgendein Feld ausser `date` ist
# nicht null». Das ist falsch: Die Speicherseen-Platzhalter fuer kuenftige Tage
# tragen sehr wohl Werte — die Fuenfjahres-Referenzkurven `fiveYearMin/Max/
# Mittelwert` —, nur keine Messung. Das Praedikat hielt sie deshalb fuer echt
# und schnitt genau die Zeilen weg, wegen derer es die Fixture gibt.
MEASUREMENT_FIELD = {
    "dashboard_storage_lakes.json": "speicherstandProzent",
    "dashboard_consumption_forecast.json": "landesverbrauch",
}


def _trim_series(payload: Any, name: str) -> str:
    """Kuerzt lange `entries`-Listen und sagt, um wie viel.

    Die Speicherseen-Antwort ist knapp 1 MB, fast ausschliesslich Tageswerte.
    Fuer die Form genuegen wenige — aber die urspruengliche Laenge gehoert in
    die Auswahlregel, sonst behauptet die Fixture stillschweigend, die Reihe
    sei kurz.

    Gekuerzt wird vom ENDE her, aber **nicht stumpf**: Die Reihe laeuft in die
    Zukunft und endet mit Zeilen ohne Messung. Die letzten N Eintraege waeren
    also lauter Platzhalter. Behalten werden deshalb die letzten N **mit**
    Messung und die letzten paar **ohne** — genau deren Zusammenspiel ist der
    Fehler, gegen den die Tests hier stehen.
    """
    field = MEASUREMENT_FIELD.get(name)
    notes: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "entries" and isinstance(value, list) and len(value) > SERIES_KEEP:
                    if field is None:
                        raise SystemExit(
                            f"{name}: lange `entries` unter `{path}`, aber kein "
                            "Messfeld in MEASUREMENT_FIELD eingetragen. Erst "
                            "nachtragen — geraten wird hier nicht."
                        )
                    real = [e for e in value if e.get(field) is not None]
                    empty = [e for e in value if e.get(field) is None]
                    if not real:
                        raise SystemExit(
                            f"{name}: `{path}{key}` hat keinen Eintrag mit "
                            f"`{field}` — Feldname oder Quelle pruefen"
                        )
                    kept = real[-SERIES_KEEP:] + empty[-PLACEHOLDER_KEEP:]
                    notes.append(
                        f"`{path}{key}` von {len(value)} auf {len(kept)}: die letzten "
                        f"{len(real[-SERIES_KEEP:])} mit `{field}` plus "
                        f"{len(empty[-PLACEHOLDER_KEEP:])} der {len(empty)} Zeilen ohne"
                    )
                    node[key] = kept
                else:
                    walk(value, f"{path}{key}.")

    walk(payload, "")
    if not notes:
        return " — vollstaendig, wie die Quelle sie liefert"
    return (
        " — Zeitreihen gekuerzt ("
        + "; ".join(notes)
        + "). Die Zeilen ohne Messung bleiben absichtlich drin: Der Produktivcode "
        "schneidet mit `entries[-limit_weeks:]`, und ohne sie liesse sich nicht "
        "pruefen, dass er sie ueberspringt"
    )


class _Recorder(httpx.AsyncBaseTransport):
    """Laesst den echten Verkehr durch und legt jede Antwort beiseite.

    So baut der Produktivcode die Anfrage und dieses Skript sieht nur zu. Der
    Alternativweg — die Abfrage hier nachbauen — waere genau der Fehler, gegen
    den die ganze Uebung angeht, eine Ebene hoeher.
    """

    def __init__(self) -> None:
        # `trust_env=True` ist Sache des Clients, nicht des Transports: Ein von
        # Hand gebauter `AsyncHTTPTransport` liest `HTTPS_PROXY` NICHT. Ohne
        # diese Zeile scheitert jeder Aufruf hinter einem Proxy — und zwar als
        # «Quelle nicht erreichbar», was nach einem Befund an der Quelle
        # aussieht statt nach einem Fehler im Skript.
        self._inner = httpx.AsyncHTTPTransport(
            proxy=os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or None,
            verify=os.environ.get("SSL_CERT_FILE") or True,
        )
        self.calls: list[tuple[httpx.Request, bytes]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        body = await response.aread()
        await response.aclose()
        self.calls.append((request, body))
        # `aread()` liefert den ENTPACKTEN Rumpf. Die Kopfzeilen unveraendert
        # weiterzureichen hiesse, entpackte Bytes mit `content-encoding: gzip`
        # zu etikettieren — httpx versucht dann ein zweites Mal zu entpacken und
        # scheitert. Beide Laengen-/Kodierungsangaben beschreiben ab hier den
        # falschen Rumpf und muessen weg.
        headers = [
            (k, v)
            for k, v in response.headers.raw
            if k.lower() not in (b"content-encoding", b"content-length")
        ]
        return httpx.Response(response.status_code, headers=headers, content=body, request=request)

    def last(self) -> tuple[httpx.Request, bytes]:
        if not self.calls:
            raise SystemExit("Kein Aufruf aufgezeichnet — hat der Cache zugeschlagen?")
        return self.calls[-1]


async def record() -> int:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    recorded_at = datetime.now(UTC).strftime("%Y-%m-%d")
    entries: list[dict] = []

    def write(name: str, body: bytes, request: httpx.Request, rule: str) -> None:
        text = body.decode("utf-8")
        # Neu einruecken, damit der Diff beim naechsten Aufzeichnen lesbar
        # bleibt; am Inhalt aendert das nichts.
        text = json.dumps(json.loads(text), ensure_ascii=False, indent=2) + "\n"
        (FIXTURES / name).write_text(text, encoding="utf-8")
        entries.append(
            {
                "name": name,
                "url": str(request.url),
                "rule": rule,
                "bytes": len(text.encode("utf-8")),
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
        )
        print(f"ok  {name:<34} {len(text.encode('utf-8')):>8} B")

    recorder = _Recorder()
    http = httpx.AsyncClient(
        transport=recorder,
        timeout=httpx.Timeout(120.0, connect=15.0),
        headers={
            "User-Agent": api_client.DEFAULT_USER_AGENT,
            "Accept": "application/sparql-results+json",
        },
    )
    dashboard_http = httpx.AsyncClient(
        transport=recorder,
        timeout=httpx.Timeout(120.0, connect=15.0),
        headers={"User-Agent": api_client.DEFAULT_USER_AGENT, "Accept": "application/json"},
    )

    try:
        # 1) ElCom-Tarife ueber LINDAS. Die Abfrage baut der Produktivcode.
        elcom = api_client.ElComSparqlClient(http=http)

        bindings, _, _ = await elcom.get_tariffs_by_municipality(
            BFS_NR, period_from=PERIOD_FROM, limit=SPARQL_LIMIT
        )
        if not bindings:
            raise SystemExit(
                f"LINDAS: keine Tarife fuer BFS {BFS_NR} ({BFS_NAME}) ab {PERIOD_FROM} — "
                "Gemeinde, Cube, Periodenfilter oder Abfrage pruefen"
            )
        if len(bindings) > SPARQL_LIMIT:
            raise SystemExit(
                f"LINDAS: {len(bindings)} Zeilen trotz LIMIT {SPARQL_LIMIT} — "
                "der Parameter wirkt nicht mehr"
            )
        request, body = recorder.last()
        write(
            "lindas_tariffs_municipality.json",
            body,
            request,
            f"Tarife der Gemeinde {BFS_NAME} (BFS {BFS_NR}) ab {PERIOD_FROM}, "
            f"{len(bindings)} Zeilen bei LIMIT {SPARQL_LIMIT}. Die SPARQL-Abfrage stammt aus "
            "`get_tariffs_by_municipality` und ist nicht daneben nachgebaut",
        )

        bindings, _, _ = await elcom.get_median_swiss(period_from=PERIOD_FROM, limit=SPARQL_LIMIT)
        if not bindings:
            raise SystemExit(
                f"LINDAS: kein Schweizer Median ab {PERIOD_FROM} — Cube oder Periodenfilter geaendert?"
            )
        request, body = recorder.last()
        write(
            "lindas_median_swiss.json",
            body,
            request,
            f"Schweizer Medianpreise ab {PERIOD_FROM}, {len(bindings)} Zeilen bei "
            f"LIMIT {SPARQL_LIMIT}; Abfrage aus `get_median_swiss`",
        )

        bindings, _, _ = await elcom.get_median_canton(
            CANTON, period_from=PERIOD_FROM, limit=SPARQL_LIMIT
        )
        if not bindings:
            raise SystemExit(
                f"LINDAS: keine Kantonsmediane ab {PERIOD_FROM} — Cube oder Periodenfilter geaendert?"
            )
        request, body = recorder.last()
        write(
            "lindas_median_canton.json",
            body,
            request,
            f"Medianpreise des Kantons {CANTON} ab {PERIOD_FROM}, {len(bindings)} Zeilen "
            f"bei LIMIT {SPARQL_LIMIT}; Abfrage aus `get_median_canton`",
        )

        # 2) Das Energiedashboard des BFE.
        dashboard = api_client.EnergyDashboardClient(http=dashboard_http)
        for label, coro in (
            ("production_mix", dashboard.get_production_mix()),
            ("consumption_forecast", dashboard.get_consumption_forecast()),
            ("storage_lakes", dashboard.get_storage_lakes()),
            ("consumer_price_index", dashboard.get_consumer_price_index()),
        ):
            data, _, _ = await coro
            if not data:
                raise SystemExit(f"Dashboard {label}: leere Antwort")
            request, body = recorder.last()
            payload = json.loads(body)
            note = _trim_series(payload, f"dashboard_{label}.json")
            shape = (
                f"Liste mit {len(data)} Eintraegen"
                if isinstance(data, list)
                else f"Objekt mit den Schluesseln {sorted(data)}"
            )
            write(
                f"dashboard_{label}.json",
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                request,
                f"{shape}{note}",
            )

        # 3) Die beiden CKAN-Kataloge. Beide senden `rows` explizit — ohne den
        #    Parameter liefert CKAN eine willkuerliche Teilmenge und nennt sie
        #    nicht so.
        catalog = api_client.CkanDiscoveryClient(http=dashboard_http)
        for label, coro in (
            ("opendata_swiss", catalog.search_opendata_swiss(CKAN_QUERY, rows=CKAN_ROWS)),
            ("zurich", catalog.search_zurich(CKAN_QUERY, rows=CKAN_ROWS)),
        ):
            data, _, _ = await coro
            result = (data or {}).get("result") or {}
            results = result.get("results") or []
            if not results:
                raise SystemExit(f"CKAN {label}: keine Treffer fuer «{CKAN_QUERY}»")
            if len(results) > CKAN_ROWS:
                raise SystemExit(
                    f"CKAN {label}: {len(results)} Treffer trotz rows={CKAN_ROWS} — "
                    "der Parameter wirkt nicht mehr"
                )
            request, body = recorder.last()
            write(
                f"ckan_{label}_search.json",
                body,
                request,
                f"Suche «{CKAN_QUERY}» mit explizitem rows={CKAN_ROWS}; "
                f"`count` ist der echte Gesamtbestand ({result.get('count')}), "
                f"`results` sind {len(results)}",
            )
    finally:
        await http.aclose()
        await dashboard_http.aclose()

    _write_provenance(recorded_at, entries)
    print(f"\nPROVENANCE.md geschrieben, Aufzeichnungsdatum {recorded_at}")
    return 0


def _write_provenance(recorded_at: str, entries: list[dict[str, Any]]) -> None:
    lines = [
        "# Herkunft der Fixtures",
        "",
        "**Erzeugt von `scripts/record_fixtures.py`. Nicht von Hand pflegen.**",
        "",
        f"Aufgezeichnet am **{recorded_at}**.",
        "",
        "Ohne Datum ist «aufgezeichnet» nach zwei Jahren von «ausgedacht» nicht",
        "mehr zu unterscheiden — die Datei sieht gleich aus.",
        "",
        "## Die Anfragen baut der Produktivcode",
        "",
        "Das Skript ruft `ElComSparqlClient` und `DashboardClient` auf und faengt",
        "die Antwort ueber einen httpx-Transport ab, statt die SPARQL-Abfragen",
        "daneben noch einmal zu tippen. Eine Fixture, die eine leicht andere Frage",
        "beantwortet als der Server stellt, belegt die falsche Antwort — und zwar",
        "unauffaellig, weil sie plausibel aussieht. Bei 40 Zeilen SPARQL ist",
        "«leicht anders» der Normalfall, nicht die Ausnahme.",
        "",
        "Die vollstaendige Abfrage steht deshalb in der `url` jeder Datei unten.",
        "",
        "**Es sind Ausschnitte, keine Vollabzuege.** Wo eine Suche gekuerzt ist,",
        "bleibt `count` auf dem echten Wert: Er sagt, wie viel **nicht** in der",
        "Datei steht.",
        "",
        f"**Feste Gemeinde:** BFS {BFS_NR} ({BFS_NAME}). Eine Auswahl, die vom Ort",
        "oder Tag des Laufs abhaengt, erzeugt bei jedem Aufzeichnen einen anderen",
        "Diff und laesst sich nicht mehr nachvollziehen.",
        "",
    ]
    for e in entries:
        lines += [
            f"## `{e['name']}`",
            "",
            f"- **Quelle:** `{e['url']}`",
            f"- **Aufgezeichnet:** {recorded_at}",
            f"- **Auswahl:** {e['rule']}",
            f"- **Groesse:** {e['bytes']} B",
            f"- **SHA-256:** `{e['sha256']}`",
            "",
        ]
    (FIXTURES / "PROVENANCE.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(record()))
    except httpx.HTTPError as exc:
        print(f"FEHLER: Quelle nicht erreichbar: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
