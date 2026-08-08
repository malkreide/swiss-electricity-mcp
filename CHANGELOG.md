# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **Alle drei ElCom-Tarif-Werkzeuge lieferten seit einer Umstellung der Quelle
  nichts.** LINDAS hat den Prädikat-Namensraum der Preis-Cubes umgebaut: Der
  Zweig `.../measure/*` existiert nicht mehr — `total`, `energy`, `gridusage`,
  `charge` und `aidfee` stehen heute unter `.../dimension/*`. Ebenso weg sind
  die cube-eigenen Namensräume: `electricityprice-swiss/…` und
  `electricityprice-canton/…` gibt es nicht; alle drei Cubes teilen sich
  `electricityprice/dimension/*` und unterscheiden sich nur noch über
  `cube.link/observationSet`.

  `measure/total` war in jeder der drei Abfragen ein **Pflicht-Tripel**. Das
  Ergebnis war deshalb nicht ein Fehler, sondern HTTP 200 mit **null Zeilen** —
  für jede Gemeinde, jeden Kanton, jedes Jahr. `tariff_get_by_municipality`
  antwortete auf «Was kostet Strom in Zürich?» mit einer leeren, wohlgeformten
  Antwort. Gemessen am 2026-08-07: Zürich (BFS 261) hat 291 Beobachtungen im
  Cube; die Abfrage des Servers fand null.

  Korrigiert und live gegengeprüft: Zürich liefert wieder Tarife (C1, 2026:
  25.83 Rp/kWh, EWZ), der Schweizer Median 25.65 Rp/kWh, Luzern 23.83.

- **Vier von fünf Speicherseen-Regionen lieferten die Schweizer Zahlen.** Das
  Werkzeug bietet `totalCH`, `Wallis`, `Tessin`, `Graubuenden` und `ZentralOst`
  an; die Quelle führt `totalCH`, `wallis`, `tessin`, `graubuenden` und
  `uebrigCH`. Der Zugriff lautete `data.get(region) or data.get("totalCH")` —
  vier der fünf Werte trafen also nie, und der Rückfall lieferte die
  gesamtschweizerischen Werte, während die Antwort weiterhin den Namen der
  Region trug. Richtig aussehende Daten unter falschem Etikett.

  Neu gibt es eine ausgeschriebene Zuordnung; ein fehlender Schlüssel wirft
  `UpstreamSchemaError` mit den tatsächlich vorhandenen Schlüsseln in der
  Meldung, statt still auf etwas anderes auszuweichen.

- **Die Speicherseen-Zeitreihe kam standardmässig leer zurück.** Die Reihe läuft
  in die Zukunft: Nach dem letzten gemessenen Tag folgen Platzhalter ohne
  Messung. Gemessen am 2026-08-07: 455 Einträge, davon 361 mit Wert und **94
  leere am Ende**. Der Standardschnitt `entries[-52:]` traf damit **52 Zeilen
  ohne eine einzige Zahl**.

  Aus demselben Grund war `capacity_gwh` immer `null`: gelesen wurde
  `entries[-1]`, und das ist ein Platzhalter. Der letzte gemessene Tag weist
  8895 GWh aus.

  Beides behoben — die Reihe überspringt Zeilen ohne Messung, die Kapazität
  kommt aus dem letzten Eintrag, der eine hat.

- **Auch die SPARQL-Antworten von LINDAS wurden bei einer Strukturänderung zu
  null Zeilen.** `_sparql` las
  `resp.json().get("results", {}).get("bindings", [])` — zwei Defaults
  hintereinander. Fiel einer weg, kamen null Zeilen heraus, und aus einem
  Fehler wurde eine gültige Aussage über die Schweizer Stromtarife.

  Die Form ist hier nicht geraten: Die SPARQL-1.1-Results-Empfehlung des W3C
  schreibt `results.bindings` vor, **auch für ein leeres Ergebnis**. Fehlt es,
  hat nicht LINDAS nichts gefunden — dann ist die Antwort keine SPARQL-Antwort
  mehr, etwa eine Fehlerseite mit HTTP 200.

  `sparql_bindings()` bestätigt beide Ebenen und wirft sonst
  `UpstreamSchemaError` — denselben Typ, den der CKAN-Pfad seit dem letzten
  Release nutzt. Ein leeres Ergebnis (`bindings: []`) bleibt eine Aussage der
  Quelle.

  Nachtrag zum Portfolio-Durchlauf
  ([`FID-006`](https://github.com/malkreide/mcp-audit-skill/blob/main/checks/FID-006.md)):
  Der CKAN-Sweep reparierte den einen Pfad dieses Servers, LINDAS ist der
  andere.

### Fixed

- **Eine Strukturänderung von CKAN wurde zu «keine Treffer».** Beide
  Datensatz-Suchen — `opendata.swiss` und `data.stadt-zuerich.ch` — schrieben
  `result = data.get("result") or {}` und lasen danach `result.get("results", [])`.

  Fällt `result` weg, gelang die Suche, die Trefferliste war leer, und
  `consumption_search_zurich` meldete `match_type: "none"` samt hilfreichem
  Vorschlag: **die exakt gleiche Antwort wie bei einer korrekten Suche ohne
  Treffer**. Die ARCH-003-Freundlichkeit dieses Servers machte den Ausfall
  dadurch noch überzeugender.

  `or {}` war zudem weiter gefasst als ein blosser Default — es verschluckte
  auch ein `result: null`, also genau den Fall, in dem die Quelle ausdrücklich
  sagt, dass sie nichts hat.

  Beide Stellen laufen jetzt über `ckan_result()`, das `result` **und**
  `results` bestätigt und sonst `UpstreamSchemaError` wirft, mit den tatsächlich
  vorhandenen Schlüsseln in der Meldung. Der Typ steht bewusst neben
  `UpstreamUnreachableError` und nicht darunter: Dort ist die Quelle nicht
  erreichbar, hier hat sie geantwortet und ihre Form geändert — Warten hilft
  beim einen, beim anderen nie.

  Die Meldung nennt die **Aktion samt Host**, weil sich zwei verschiedene
  CKAN-Instanzen denselben Helfer teilen; eine Meldung, die nur «CKAN» sagt,
  schickt den Leser in das falsche Portal.

  Eine echte Leermenge (`count: 0` bei vorhandenem `results`) bleibt
  unverändert `match_type: "none"` mit Vorschlag — ein Wächter, der die
  mitfängt, wird nach dem zweiten Fehlalarm abgeschaltet.

  Gefunden im Portfolio-Durchlauf zu
  [`FID-006`](https://github.com/malkreide/mcp-audit-skill/blob/main/checks/FID-006.md)
  am 2026-08-07: Acht Server im Portfolio sprechen mit CKAN, alle acht prüfen
  das `success`-Envelope, sieben defaulteten `result` danach.

### Fixed

- **The retry had six defects, all inherited from the shared template.** This
  server copied its retry from `reference/retry_backoff.py` in
  [mcp-data-source-probe-skill](https://github.com/malkreide/mcp-data-source-probe-skill),
  and the template shipped these until 2026-08-07. A sweep across eleven
  servers found that none read `Retry-After` and none jittered — one template,
  eleven copies, not eleven independent omissions.
  1. **No jitter.** The ladder was deterministic, so every client that hit the
     same outage retried in lockstep and the load returned as a wave exactly
     when the source recovered — the retry storm extending the outage it was
     meant to bridge. Now spread into `[0.5x, 1.5x]`.
  2. **`Retry-After` was never read.** A 429 or 503 answers the very question
     the backoff curve guesses at. Both RFC 9110 §10.2.3 forms are now read
     (delta-seconds and HTTP-date); an unparseable header yields `None` and
     falls back to the curve — it must never crash on the error path. The
     jitter on top is one-sided `[1.0x, 1.25x]`: the source said *when*, so
     later is polite and earlier ignores the value just read.
  3. **No cap on a single wait**, and the cap now binds *after* the jitter.
     `min(cap, base) * jitter` and `min(cap, base * jitter)` both contain a cap
     and a jitter; only the second is bounded — 20s times 1.5 is 30s.
  4. **The budget counted attempts, not seconds.** Four attempts against an
     upstream that takes 30s to time out is two minutes inside one tool call,
     and an attempt count never says so. Now 25s for the whole call, anchored
     on the MCP SDK's `MCP_DEFAULT_TIMEOUT = 30.0`.
  5. **Nothing held that budget.** It is now an `asyncio.timeout` wall-clock
     deadline rather than an httpx timeout: httpx bounds each *operation*, and
     its read timeout restarts with every chunk, so a slowly trickling response
     outlived the budget without any single read expiring.
  6. **Point six did not apply here.** The client-facing message is generic
     (OBS-002) and the log line already used `repr(last_error)` rather than
     `str(last_error)` — so this server never had the empty-`str()` problem the
     sibling servers did: `httpx.ConnectTimeout`, `ReadTimeout` and
     `ConnectError` all have a blank `str()`, and `repr` keeps the type. The
     log now also records which of the two limits ran out.

  New `tests/test_retry_policy.py`: `Retry-After` in both forms plus the
  refusal cases, the jitter spread, that the cap binds after jittering, and the
  one-sided `Retry-After` jitter.

### Added

- **Aufgezeichnete Fixture-Herkunft.** `scripts/record_fixtures.py` holt neun
  Antworten von den echten Quellen — die drei ElCom-Abfragen über LINDAS, die
  vier Endpunkte des BFE-Energiedashboards und die beiden CKAN-Suchen — und
  schreibt `tests/fixtures/PROVENANCE.md` mit Quelle, Datum, Auswahlregel und
  SHA-256 je Datei.

  **Die Anfragen baut der Produktivcode.** Das Skript ruft die Client-Klassen
  auf und fängt die Antwort über einen httpx-Transport ab, statt die
  SPARQL-Abfragen daneben noch einmal zu tippen. Eine Fixture, die eine leicht
  andere Frage beantwortet als der Server stellt, belegt die falsche Antwort —
  unauffällig, weil sie plausibel aussieht. Bei 40 Zeilen SPARQL ist «leicht
  anders» der Normalfall.

  Zwei Auswahlregeln sind bewusst mehr als «die ersten N», und die zweite ist
  eine Korrektur an mir selbst:

  - Die Speicherseen-Reihe behält die Zeilen **ohne** Messung. Ohne sie könnte
    kein Test zeigen, dass das Werkzeug sie überspringt.
  - Was als Messung zählt, steht je Datei ausgeschrieben. Die erste Fassung
    nahm «irgendein Feld ausser `date` ist nicht null» — falsch, denn die
    Zukunftszeilen tragen sehr wohl Werte (die Fünfjahres-Referenzkurven), nur
    keine Messung. Das generische Kriterium hielt sie für echt und schnitt
    genau die Zeilen weg, wegen derer es die Fixture gibt.

  Das Skript bricht laut ab, wenn eine ElCom-Abfrage nichts findet, wenn ein
  `LIMIT` nicht mehr wirkt, wenn CKAN mehr liefert als `rows` erlaubt oder wenn
  eine gekürzte Zeitreihe kein Messfeld hinterlegt hat.

  `tests/test_recorded_sources.py` hält Abfragen und Verarbeitung dagegen;
  `tests/fixture_data.py` lädt und behandelt einen fehlenden Namen als Fehler
  statt als leere Struktur.

## [0.2.5] - 2026-08-02

### Fixed

- **`structlog` carried no upper bound, and the index already serves a major past
  the floor.** The declared range was `structlog>=24.1.0`; PyPI has been serving
  `26.1.0`. The artefact does not change — the resolver's answer to the next
  fresh install does, and that is exactly how `swiss-energy-mcp` 0.3.3 became
  uninstallable when `mcp` 2.0.0 removed the module it imported.

  Now `structlog>=24.1.0,<27`. The bound is measured rather than guessed: this package
  installs and imports against `structlog 26.1.0` today, so the cap admits what
  demonstrably works and stops only the next, unknown major.

A dependency range only reaches users through a new release, hence the
version bump. No code changed.

## [0.2.4] - 2026-07-30

### Fixed

- **The User-Agent reports the actual package version again.** The published
  `0.2.3` sent `swiss-electricity-mcp/0.2.0` to every upstream — the version string was
  hardcoded and had been left behind by earlier bumps. The version now comes
  from the package metadata, so it can no longer drift from the package.

- **HTTP-Modus wies unter jedem echten Hostnamen mit 421 ab (SEC-005).**
  `build_http_app()` rief `mcp.streamable_http_app()` ohne `host` auf. Unter
  mcp 2.x ist das kein neutraler Default: das SDK leitet daraus seine
  Host-Allow-List ab und aktiviert bei loopback-artigem Wert automatisch
  `127.0.0.1:*`. Da das Argument selbst auf `127.0.0.1` defaultet, galt das auch
  für den `SWISS_ELECTRICITY_HOST=0.0.0.0`-Bind, den dieses Modul für Container
  dokumentiert. Vor der Migration ging `host` an den `FastMCP`-Konstruktor, wo
  dieselbe Logik den echten Bind sah und den Schutz korrekt ausliess.

  Der Bind reist jetzt in die App, und eine echte Allow-List wird aus dem neuen
  `SWISS_ELECTRICITY_ALLOWED_HOSTS` gebaut. Ohne diese Variable bleibt der
  Schutz auf einem Nicht-Loopback-Bind bewusst aus und der Aufrufer warnt — eine
  geratene Liste wäre genau der 421-Fall.

- **`SWISS_ELECTRICITY_CORS_ORIGINS` funktionierte nie in der dokumentierten
  Form.** Vorbestehender Fehler, den das zweite Listen-Feld sichtbar gemacht
  hat: pydantic-settings JSON-dekodiert komplex typisierte Felder aus der
  Umgebung, *bevor* ein `mode="before"`-Validator läuft. Eine kommagetrennte
  Liste löste damit `SettingsError` aus, und `_split_csv` war für Env-Eingaben
  unerreichbar — toter Code. Beide Felder tragen jetzt `NoDecode`.

  14 neue Tests, darunter der tragende Fall „richtiger Hostname, falscher Port":
  nur er unterscheidet eine portgenaue Allow-List von einer, die alles
  durchlässt. Mutationsgetestet in beide Richtungen — `NoDecode` entfernen bricht
  die CSV-Tests, den `host`-Kwarg entfernen reproduziert das 421.

  Geprüft mit dem wörtlichen CI-Kommando (`pytest -m "not live" -q`):
  58 passed, 3 deselected; `ruff check src/ tests/` clean.

## [0.2.0] - 2026-06-03

Audit-remediation release. Closes all critical/high findings from the
`mcp-audit-skill` audit; the re-audit reports **production-ready**
(36 pass · 0 fail · 2 partial · 6 todo, catalog hash `091f446b`,
run-id `2026-06-03T191138-Z-swiss-electricity-mcp`).

### Changed

- **ARCH-004**: Configuration is centralised in a Pydantic-Settings object
  (`config.py`); the shared HTTP clients moved from module-level globals into the
  lifespan context and are accessed by tools via `ctx.request_context.lifespan_context`.

### Documentation

- **OPS-002**: ASCII architecture diagram in the README.
- **OPS-003**: Phase-1 declaration + `docs/roadmap.md` with phase-transition
  criteria.
- **ARCH-008**: README rationale for exposing Tools only (no Resources/Prompts).
- **SEC-019 / SEC-013 / SEC-008**: `docs/security-posture.md` — lethal-trifecta
  assessment, secret-management stance (none required), supply-chain trust.

### Changed

- **ARCH-007**: `tariff_compare_municipalities` fetches municipalities
  concurrently (`asyncio.gather`) instead of sequentially.
- **ARCH-003**: search tools return `match_type` (`results`/`none`) and an
  actionable `suggestion` on zero hits instead of a silent empty list.

### Observability

- **OBS-003 / OBS-004**: Structured JSON logging via `structlog`, written to
  **stderr** so the stdio JSON-RPC channel stays clean. Level via
  `SWISS_ELECTRICITY_LOG_LEVEL`.
- **OBS-006**: Opt-in OpenTelemetry tracing — per-tool spans plus httpx
  auto-instrumentation, enabled when `OTEL_EXPORTER_OTLP_ENDPOINT` is set and
  the `otel` extra is installed. No-op otherwise.
- **OBS-002**: Upstream errors and status-probe failures are logged with full
  detail server-side but return a generic message to the client (no leaked
  stacktrace / internal repr).
- **OBS-001**: Added execution- and protocol-error-path tests.

### SDK

- **SDK-003**: SPARQL-backed tools accept `ctx: Context`; `tariff_compare_*`
  reports per-municipality progress, others emit `ctx.info` start events.
- **SDK-004**: Streamable-HTTP transport now runs behind CORS middleware that
  exposes/allows `Mcp-Session-Id`; origins via `SWISS_ELECTRICITY_CORS_ORIGINS`
  (never a wildcard).

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

### Added

- **ARCH-011 / OPS-001**: CI workflows — `test.yml` (ruff + `pytest -m "not live"`
  on Python 3.11–3.13) and `publish.yml` (PyPI OIDC Trusted Publisher on release).
- **ARCH-005**: `secret-scan.yml` runs Gitleaks on every push and PR.
- **ARCH-012**: Dependabot (`pip` + `github-actions`, weekly) and a
  "MCP protocol version" section + update policy in the README.

### Changed

- **OPS-001**: Tests split into `tests/test_unit.py` (mocked, CI) and
  `tests/test_live.py` (live, excluded from CI).
- **ARCH-012**: `mcp[cli]` pinned to `>=1.2.0,<2.0.0`.

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
