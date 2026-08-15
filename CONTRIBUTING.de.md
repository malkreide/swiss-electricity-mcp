# 🤝 Mitwirken an swiss-electricity-mcp

🌍 **Read this in your language:** [🇬🇧 English](CONTRIBUTING.md)

Teil des [Swiss Public Data MCP Portfolio](https://github.com/malkreide/swiss-public-data-mcp).
Dieses Portfolio folgt gemeinsamen Konventionen, damit sich alle Server sauber zu
mehrquelligen KI-Agent-Workflows kombinieren lassen.

## Portfolio-Konventionen

- **No-Auth-First**: Phase-1-Server nutzen ausschliesslich unauthentifizierte öffentliche Endpunkte.
- **Live-Probe vor Code**: jeder neue Endpunkt wird gegen den realen Upstream
  validiert, bevor er in den Client aufgenommen wird.
- **Envelope-Disziplin**: jedes Pydantic-Response erbt von `ResponseEnvelope`
  mit `source` + `provenance` + `retrieved_at` — versehentliches Weglassen ist unmöglich.
- **Retry-with-Backoff**: 3 Retries, 2/4/8 Sekunden, 5xx + 429 werden wiederholt.
- **Dual-Transport**: stdio für Claude Desktop, Streamable HTTP für die Cloud.
- **Zweisprachige Dokumentation**: englisches `README.md` primär, deutsches `README.de.md`
  als Spiegel in Schweizer Schreibweise (kein Eszett).
- **CI**: ruff + pytest (ohne `@pytest.mark.live`) bei jedem Push.
- **Release**: getaggtes Release auf GitHub löst die PyPI-Veröffentlichung via OIDC aus.

## Setup

```bash
git clone https://github.com/malkreide/swiss-electricity-mcp.git
cd swiss-electricity-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Tests

```bash
# Unit-Tests (gemockt, schnell)
PYTHONPATH=src pytest tests/ -m "not live" -v

# Live-Tests (gegen reale Upstreams — nur bei Bedarf)
PYTHONPATH=src pytest tests/ -m live -v
```

## Lint

```bash
ruff check src tests
```

## Ein Tool hinzufügen

1. Endpunkt live prüfen (`curl`, Antwortform, Status, Latenz checken).
2. Ein Pydantic-Response-Modell in `models.py` ergänzen (von `ResponseEnvelope` erben).
3. Die Client-Methode in `api_client.py` ergänzen (`_fetch_with_retry` verwenden).
4. Das `@mcp.tool` in `server.py` registrieren mit deutschem Docstring + englischer
   Tool-Beschreibung.
5. Einen gemockten Happy-Path-Test und mindestens einen Live-Test in
   `tests/test_server.py` ergänzen.
6. `CHANGELOG.md` aktualisieren.

## Releasing

1. `version` in `pyproject.toml` und `__init__.py` erhöhen.
2. `CHANGELOG.md` mit einem neuen Abschnitt aktualisieren.
3. Committen, pushen, ein GitHub-Release mit Tag `v0.X.Y` erstellen.
4. GitHub Actions veröffentlicht automatisch auf PyPI.

## Code-Stil

- Schweizer Schreibweise in benutzersichtbaren Strings verwenden (kein Eszett).
- Feldbeschreibungen in Modellen: Deutsch zuerst (da es die Quellsprache der
  meisten Datensätze ist), Englisch in den Tool-Beschreibungen für LLM-Klarheit.

## Die Live-Suite: wann sie läuft, und wer ein rotes Ergebnis sieht

**Kadenz:** jeden Montag um 05:23 UTC, dazu jederzeit von Hand über *Actions → Live-Tests → Run
workflow*. Siehe [`.github/workflows/live-tests.yml`](.github/workflows/live-tests.yml).

**Wer es sieht:** Ein roter Lauf öffnet ein Issue mit dem Label `upstream` und dem stabilen Titel «Live-Tests gegen energiedashboard.admin.ch rot (<Datum>)». Ein zweiter roter Lauf erkennt das offene Issue am Titelanfang und hängt sich an denselben Thread, statt ein zweites aufzumachen. Wird die Suite wieder grün, schliesst sich das Issue selbst.

**Drei Antworten, nicht zwei.** `scripts/classify_live_run.py` liest das JUnit-XML statt des
Exit-Codes und unterscheidet: `clear` (gelaufen, grün), `finding` (gelaufen,
etwas gefallen) und `unknown` (nicht gelaufen — Installation gescheitert, null
Tests eingesammelt, alle übersprungen). Ein `unknown` schliesst nie ein Issue:
Zuzumachen hiesse zu behaupten, der Vergleich sei gelaufen.

**Ein roter Live-Lauf heisst nicht zwingend «unser Fehler».** Er heisst: Der
Vertrag mit der Quelle hat sich geändert, oder die Quelle ist gerade aus. Beides
gehört gesehen, nur das Erste gehört gefixt. Bitte den Lauf lesen, bevor der Job
deaktiviert wird — so stirbt dieser Check, und er ist der einzige im Repo, der
einer falschen Grundannahme über energiedashboard.admin.ch widersprechen kann. Jeder andere Test
prüft gegen eine Fixture, und die Fixture ist aus derselben Annahme geschrieben
wie der Code.
