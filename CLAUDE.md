# CLAUDE.md

## Vor der Arbeit

Klon-Aktualität prüfen: `git fetch origin main && git rev-list --count HEAD..origin/main`

Ein veralteter Klon erzeugt eine rote CI, deren Ursache nicht im Diff steht. Am
3.8.2026 zweimal passiert — beide Male fehlten genau die Commits, die das Gate
einführten, an dem der Branch scheiterte.

Gates lokal fahren, mit der GEPINNTEN ruff-Version aus der CI. Eine andere
Version meldet Abweichungen, die niemand verursacht hat.

## Tests

Gegenprobe ist Pflicht. Ein Test, der grün bleibt, wenn man die Implementierung
entfernt, prüft nichts. Jede neue Zusicherung einzeln neutralisieren und zeigen,
dass genau die zugehörigen Tests fallen.

Zwei Fallen, die beide grün blieben:

- Eine Fake-Uhr, die nur beim Schlafen vorrückt, kann eine Zusicherung über
  echte Zeit nicht widerlegen.
- `monkeypatch.setattr(modul.asyncio, "sleep", ...)` greift ins Modul `asyncio`
  selbst und entschärft die Mechanik im ganzen Prozess. Patche einen
  Modul-Alias (`_sleep = asyncio.sleep`), nicht das fremde Modul.

Handgeschriebene Fixtures kodieren die Annahme des Autors und können sie nicht
widerlegen. Mindestens eine aufgezeichnete Antwort pro externem Endpunkt, mit
Aufnahmedatum.

## Wenn etwas rot ist

Roter Live-Test: erst die Quelle abfragen, dann einordnen. Nicht aus der
Fehlermeldung schliessen. Am 3.8.2026 hiess "nicht gefunden" nicht, dass der
Datensatz weg war, sondern dass die Quelle die Schreibweise ihrer Kopfzeile
gewechselt hatte — vier von sechs Datensätzen produktiv kaputt, alle Unit-Tests
grün.

PR ohne jeden Check ist selten ein Repo ohne CI, meistens ein Merge-Konflikt:
GitHub berechnet dafür keinen Merge-Commit und startet nichts.

Ein Codex-Review auf einem PR wird beantwortet oder behoben, nie ignoriert.

---

## Dieses Repo

**ruff:** `0.16.1`, an zwei Stellen gepinnt — `.github/workflows/test.yml`
(Schritt «Install pinned ruff») und `.pre-commit-config.yaml` (`rev: v0.16.1`).
Beide müssen dieselbe Version nennen; wer eine hochzieht, zieht die andere im
selben Commit mit. Weichen sie ab, ist **das** der erste Befund, bevor
irgendein Lint-Ergebnis gedeutet wird.

`pip install -e ".[dev]"` installiert nach `ruff>=0.4.0` (pyproject) irgendeine
neuere Version. Wer ohne pre-commit arbeitet, installiert `ruff==0.16.1`
explizit — und prüft `ruff --version`: Ein ruff in `~/.local/bin` beschattet
die gepinnte Version im PATH, ohne dass der `pip install` etwas meldet.

**Gates, wörtlich aus `test.yml`** (Matrix: Python 3.11 / 3.12 / 3.13):

```bash
ruff check src/ tests/ scripts/
ruff format --check src/ tests/ scripts/
pytest -m "not live" -q
python scripts/check_version_sync.py
```

Dazu läuft auf jedem PR `secret-scan.yml` (Gitleaks, voller History-Scan).

**Live-Tests:** `.github/workflows/live-tests.yml` hat einen echten
cron-Trigger (`23 5 * * 1`, wöchentlich montags) plus `workflow_dispatch`.
DRIFT-005 ist damit erfüllt — die Quelle wird planmässig abgefragt, nicht nur
per `-m "not live"` aus der PR-CI ausgeschlossen. `schedule` greift nur auf
`main`: Änderungen an dieser Datei wirken erst nach dem Merge, vorher von Hand
auslösen.

**Fixtures:** `scripts/record_fixtures.py` erzeugt sie, Aufnahmedatum steht in
`tests/fixtures/PROVENANCE.md`. Nicht von Hand pflegen.
