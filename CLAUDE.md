# CLAUDE.md

## Vor der Arbeit

Klon-Aktualität prüfen — Standard-Branch ermitteln, nicht `main` annehmen:

```bash
B=$(git ls-remote --symref origin HEAD | sed -n 's|^ref: refs/heads/\([^[:space:]]*\).*|\1|p')
git fetch origin "${B:?Standard-Branch nicht ermittelbar}" &&
  git rev-list --count HEAD..FETCH_HEAD
```

Drei Server im Portfolio heissen ihren Standard-Branch `master`
(`openlex-mcp`, `swiss-courts-mcp`, `swisstopo-mcp`); dort scheitert ein fest
verdrahtetes `origin/main` mit «couldn't find remote ref main». Wer das für ein
Netzproblem hält, arbeitet weiter auf genau dem veralteten Klon, vor dem dieser
Absatz warnt. Den `:?`-Schutz nicht weglassen: Bei leerem `B` fetcht git still
den Remote-HEAD und endet mit 0.

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

**ruff: eine Quelle, plus der Hook.** Der Pin `0.16.1` steht im dev-Extra von
`pyproject.toml`. `.pre-commit-config.yaml` trägt dieselbe Zahl ein zweites Mal
(`rev: v0.16.1`), weil pre-commit `pyproject.toml` nicht lesen kann — beide
zusammen bumpen. Die Workflows pinnen **nicht** selbst.

`scripts/check_version_sync.py` erzwingt beides: Gleichstand der zwei Stellen
und Abwesenheit eines eigenen CI-Pins. Nur der Gleichstand wäre zu schwach —
ein wieder eingefügter Install-Schritt in einem Workflow liefe nach dem
dev-Extra und überschriebe es, ohne dass sich eine der beiden Zahlen ändert.
Der Vergleich bliebe grün, und in der CI liefe trotzdem eine andere Version.
Der Guard meldet ausserdem, wenn `pyproject.toml` lose statt exakt pinnt.

`ruff --version` trotzdem prüfen: Ein ruff in `~/.local/bin` beschattet die
gepinnte Version im PATH, ohne dass der `pip install` etwas meldet.

**Gates, wörtlich aus `test.yml`** (Matrix: Python 3.11 / 3.12 / 3.13):

```bash
ruff check src/ tests/ scripts/
ruff format --check src/ tests/ scripts/
pytest -m "not live" -q
python scripts/check_version_sync.py
```

Alle vier laufen in **einem** Job (`lint-and-test`), auf allen drei Versionen.
Kein separater lint-Job, keine `if: matrix.python-version`-Ausnahme — ein
grünes 3.13 heisst hier wirklich, dass alles auf 3.13 lief. (Nicht überall im
Portfolio so: `swiss-food-safety-mcp` gated zwei Gates auf 3.11.)

Die Matrix hat `fail-fast: false`. Eine rote 3.11 stoppt 3.12 und 3.13 also
nicht, und genau das ist beim Einordnen der Unterschied zwischen
«versionsabhängig» und «überall kaputt». Mit dem Standard `fail-fast: true`
stünden die anderen beiden auf `cancelled` und sagten nichts.

Dazu läuft auf jedem PR `secret-scan.yml` (Gitleaks, voller History-Scan).

**Live-Tests:** `.github/workflows/live-tests.yml` hat einen echten
cron-Trigger (`23 5 * * 1`, wöchentlich montags) plus `workflow_dispatch`.
DRIFT-005 ist damit erfüllt — die Quelle wird planmässig abgefragt, nicht nur
per `-m "not live"` aus der PR-CI ausgeschlossen. `schedule` greift nur auf
`main`: Änderungen an dieser Datei wirken erst nach dem Merge, vorher von Hand
auslösen.

**Fixtures:** `scripts/record_fixtures.py` erzeugt sie, Aufnahmedatum steht in
`tests/fixtures/PROVENANCE.md`. Nicht von Hand pflegen.
