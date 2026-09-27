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

Das Werkzeug der Gegenprobe braucht selbst eine Positivkontrolle. Am 27.9.2026
meldete ein Mutations-Skript für alle 19 Mutationen «kein Test rot» — nicht,
weil die Tests nichts prüften, sondern weil es mit dem System-Python lief, das
kein pytest hat. Die leere Liste der roten Tests sah genauso aus wie ein
Befund, und «Basis: grün» ebenfalls. Vor dem Auswerten sicherstellen, dass
pytest überhaupt eine Zeile `N passed` ausgegeben hat.

## Wenn etwas rot ist

Roter Live-Test: erst die Quelle abfragen, dann einordnen. Nicht aus der
Fehlermeldung schliessen. Am 3.8.2026 hiess "nicht gefunden" nicht, dass der
Datensatz weg war, sondern dass die Quelle die Schreibweise ihrer Kopfzeile
gewechselt hatte — vier von sechs Datensätzen produktiv kaputt, alle Unit-Tests
grün.

**Ein 4xx ist kein Nein.** Am 29.8.2026 antwortete `past-publications` in
`swiss-procurement-mcp` auf jede Publikation mit Losen mit HTTP 400. Daraus war
geschlossen worden, die Quelle verweigere diese Auskunft; der Befund stand
datiert im Fixture-Nachweis, ein Test bestätigte ihn, alles blieb grün. Die
Spec desselben Endpunkts führt einen als *optional* deklarierten Parameter
`lotId` — für Publikationen mit Losen ist er Pflicht. Mit ihm antwortet
dieselbe Publikation mit 200. Ein Projekt trug sieben Vorgängerpublikationen,
die der Server als «Quelle nicht erreichbar» wegwarf.

Drei Handgriffe daraus:

- **Die Parameterliste der Spec durchgehen, bevor ein Statuscode eingeordnet
  wird.** «Optional» heisst dort oft «optional für die Mehrheit».
- **Einer deterministischen Absage keinen Wiederholungsrat geben.** «Nicht
  erreichbar, bitte später erneut» ist bei einem 400 falsch und liest sich für
  das Modell wie eine Störung. Den Status mitführen und den fehlenden
  Parameter benennen — den Status, nicht den Antwortkörper.
- **Beide Antworten aufzeichnen, mit und ohne den Parameter.** Eine
  Aufzeichnung nur des Fehlschlags kann nicht zeigen, dass er vermeidbar war;
  dass nur der 400er aufgezeichnet war, ist der Grund, warum der falsche
  Befund nicht auffiel.

**Und ein 403 ist gar keine Auskunft.** Am 29.8.2026 sollten für 42 Repos die
Dependabot-Labels nachgemessen werden. Alle 13 Abfragen des ersten Stapels
kamen zurück als:

```
Failed to find label: API rate limit already exceeded for user ID 8864492.
```

Der gefährliche Teil steht vorn: Das Werkzeug verpackt eine Sperre als
Fund-Fehlschlag. Wer die Zeile überfliegt oder nur auf ein leeres Ergebnis
prüft, zählt 39 Repos als «Label fehlt» und hat seine eigene Erschöpfung
gemessen. Das Limit hängt am Konto, nicht am Repo — derselbe Vormittag hatte
es mit 42 eröffneten und 42 gemergten PRs verbraucht.

Das ist der Absatz darüber, andersherum gelesen: dort war ein 400 eine echte,
wiederholbare Antwort und galt als Störung; hier ist eine Störung als Antwort
verpackt. Entscheidend ist nie der Statuscode, sondern ob die Quelle überhaupt
geantwortet hat.

- **Positivkontrolle im selben Repo.** Ein «nicht gefunden» wird erst dadurch
  zur Messung, dass eine gleichzeitige Abfrage etwas findet.
- **Die Messung entlang der Sperre teilen.** `raw.githubusercontent.com` ist
  ein CDN und nicht die REST-API. Um 11:19:27 UTC lieferte es für
  `register-mcp` HTTP 200, während die Label-Abfrage desselben Repos in
  derselben Minute die Sperre meldete. Alle 42 `dependabot.yml` kamen so
  durch, während die Label-Hälfte stand.
- **Am Token vorbei geht es nicht.** Beide Umwege enden am Agent-Proxy, und
  jeder mit einer eigenen irreführenden Begründung. `api.github.com` ohne
  Zugangsdaten:

  ```
  GitHub access is not enabled for this session. An org admin must connect
  the Claude GitHub App for this organization.
  ```

  Das ist keine Aussage über die Organisation, sondern das, was ohne Token
  kommt. Wer ihr folgt, sucht einen Admin für ein Problem, das keiner hat.
  Die HTML-Seite `github.com/<owner>/<repo>/labels` fällt ebenfalls, aber
  anders:

  ```
  This GitHub API path is not available: sessions are bound to their
  configured repositories. Use repository-scoped endpoints
  (repos/{owner}/{repo}/...).
  ```

  Der Proxy behandelt also auch `github.com` als API-Pfad; die zweite Meldung
  klingt nach einem Scope-Problem und ist doch nur dieselbe Sackgasse. Den
  Token aus der Umgebung in einen curl-Header zu setzen, blockiert der
  Klassifikator. Ob es überhaupt hülfe, ist offen: die Sperre nennt ein
  Nutzerkonto, und ob der Token zu diesem gehört, wurde nie geprüft.
- **Die Sperre gilt nicht dem Dienst, sondern dem Zugangspfad.** Unmittelbar
  nachdem eine Abfrage der Checks eines PR sauber durchlief, meldete die
  Label-Abfrage weiter die Sperre. Von einem blockierten Werkzeug also nicht
  auf «GitHub ist zu» schliessen — und umgekehrt eine gelungene Abfrage nicht
  als Entwarnung für die gesperrte nehmen.

Wann die Sperre fällt, geben diese Beobachtungen nicht her. Die Meldung nennt
keinen Zeitpunkt, und die `X-RateLimit`-Kopfzeilen sind hinter dem Proxy nicht
zu sehen. Belegt sind drei gesperrte Zeitpunkte — 11:14, 11:16 und 11:19 UTC.
Wer daraus eine Dauer macht, hat sie erfunden.

**Dieselbe Falle bei einer Konfigurationsoption: die Vorgabe lesen, bevor man
einen Schlüssel für wirkungslos hält.** Am 29.8.2026 fielen die
`labels:`-Zeilen aus den `dependabot.yml` des Portfolios, begründet mit
«Dependabot legt Labels nicht an». Eine Messung danach zeigte, dass
`dependencies` in 36 von 42 Repos sehr wohl existiert, 35 davon mit GitHubs
Standardbeschreibung. Das las sich zuerst wie ein Beleg, dass die Aktion
falsch war.

Die Optionsreferenz kehrt es um:

```
Dependabot creates these default labels automatically, as necessary in
your repository.

If you define more than one package manager, an additional label for the
ecosystem or language is added to each pull request.

The labels specified are used instead of the default labels.
```

Ohne `labels:` vergibt Dependabot also `dependencies` — und, sobald mehr als
ein Paketmanager deklariert ist, zusätzlich ein Ökosystem-Label — und legt sie
selbst an; eine eigene Liste **ersetzt** diesen Satz, und «if any of these
labels is not defined in the repository, it is ignored». Die Zeile war nicht
wirkungslos — sie tauschte einen sich selbst pflegenden Vorgabesatz gegen eine
starre Liste.

**Die Bedingung nicht weglassen.** Bei nur einem Paketmanager steht das
Ökosystem-Label gar nicht zu; wer es dort trotzdem erwartet, schreibt genau
den Fehlbefund auf, gegen den dieser Abschnitt geschrieben ist — der Abschnitt
liefe an sich selbst vorbei. Im Portfolio deklariert jede `dependabot.yml`
zwei (`pip` und `github-actions`), die Bedingung ist hier also überall
erfüllt; anderswo nicht unbedingt. Aufgefallen ist die fehlende Bedingung
nicht beim Schreiben, sondern durch einen Codex-Review auf
`swiss-environment-mcp` PR #113 — vierzehn Sekunden vor dem Merge desselben
PR.

Was das kostet, ist an `openlex-mcp` gemessen: zwei Ökosysteme deklariert,
also stünden `dependencies` **und** ein Ökosystem-Label zu; vorhanden ist nur
das erste, `github-actions` und `github_actions` fehlen beide (Kontrolle `bug`
vorhanden). `register-mcp` ist die Gegenprobe: dort existieren alle vier
deklarierten Namen mit handgeschriebener Beschreibung, die Liste ist gewollt
und vollständig.

**Dreimal falsch eingeordnet, in drei Richtungen.** Erst die Zeile für bloss
wirkungslos gehalten. Dann die gefundenen Labels für einen Widerspruch. Dann,
auf denselben Fund gestützt, einen richtigen PR geschlossen mit dem Argument,
das Label existiere ja — obwohl es existiert, *weil* die Vorgabe es anlegt.
Der dritte Fehler ist der teuerste, weil er wie eine Messung aussah.

Was die Messung **nicht** hergibt: wer die 36 Labels angelegt hat. Die
Referenz sagt, Dependabot tue es; die Objekt-IDs liegen aber so dicht
beieinander, dass sie eher aus einem Stapellauf stammen. Beides passt zum
Befund, keines ist belegt — die Herkunft blieb ungemessen.

Beim Aufräumen gilt deshalb dieselbe Frage wie bei `lotId`: Was ist die
*Vorgabe*, wenn man das Ding weglässt — nicht bloss, ob der aktuelle Wert
etwas bewirkt.

**`results[0]` ist nur so verlässlich wie die Zusicherung danach.** Pinnt die
Abfrage einen bekannten Datensatz, ist der erste Treffer eine Drift-Wache und
in Ordnung. Hängt die Zusicherung dagegen davon ab, *welche* Variante die
Quelle heute zuoberst hat, prüft der Test den Tag: am 25.8.2026 rot, weil die
neueste Zürcher Publikation zufällig Lose hatte, am 26.8. grün, ohne dass sich
etwas geändert hätte. Den Fall gezielt wählen und beide Zweige fahren.

PR ohne jeden Check ist selten ein Repo ohne CI, meistens ein Merge-Konflikt:
GitHub berechnet dafür keinen Merge-Commit und startet nichts.

**Bei einem blockierten PR nennt der Merge-Versuch den Blocker, jede Ableitung
rät.** `mergeable_state: blocked` bei grüner CI heisst: ein required Kontext
fehlt oder steht nicht auf grün. Welcher, sagt die Einstellung — und die sperrt
der Agent-Proxy mit HTTP 403, ein MCP-Werkzeug dafür gibt es nicht. Der Ausweg
ist nicht Indizienarbeit, sondern ein Merge-Versuch über die API:

```
PUT /repos/<owner>/<repo>/pulls/<n>/merge
405 Required status check "Codex hat diesen Head geprueft" is expected.
```

Der Name steht dort wörtlich so, wie er in der Branch Protection eingetragen
ist. Scheitert der Versuch, kostet er nichts.

Am 24./25.9.2026 über drei Repos vermessen, nachdem ein Gate-Workflow entfernt
worden war und seinen required Kontext ohne Berichterstatter zurückliess:

| Repo | eingetragener Kontext | Art |
|---|---|---|
| `register-mcp` | `Codex hat den PR angesehen` | Check-Run |
| `srgssr-mcp` | `review-abgeschlossen` | Check-Run |
| `fedlex-mcp` | `Codex hat diesen Head geprueft` | Check-Run |

**Warum Ableiten hier systematisch fehlgeht.** GitHub nimmt als Check-Run-Name
den **Job**-Namen, nicht den des Workflows. Zwei der drei Kontexte enthalten die
Zeichenfolge «codex-gate» nicht, obwohl sie aus `codex-gate.yml` stammen; wer in
den Einstellungen danach sucht, findet nichts und hält die Regel für abwesend.
Trug der Job kein `name:`, nimmt GitHub die Job-ID — daher `review-abgeschlossen`.

Zwei Fehlschlüsse sind dabei belegt, beide aus **einer** Beobachtung gezogen:

- Aus einem Commit-Status auf den required Kontext geschlossen. In `fedlex-mcp`
  stand der Status `codex-gate` auf dem Head auf `success` und blockierte
  nichts, während der fehlende Check-Run den Merge hielt. Am Kontroll-PR waren
  beide rot — dort ist nicht zu unterscheiden, welcher von beiden eingetragen
  ist. Genommen wurde der auffälligere.
- Aus einer Check-Run-Liste auf den required Kontext geschlossen. Die Liste
  zeigt, was **berichtet** wurde; eingetragen sein kann ein Name, der gerade
  gar nicht erscheint. Genau das ist der Fall, um den es geht.

**Ein Vorbehalt, der zur Methode gehört:** Die Absage nennt immer nur den
**ersten** fehlenden Kontext. Ist ein zweiter eingetragen, zeigt ihn erst der
nächste Versuch. Nach jeder Änderung an der Einstellung also erneut versuchen,
bis der Merge durchgeht oder ein neuer Name fällt.

Die Kosten der Ableitung sind gemessen: ein Arbeitstag, an dem der PR-Text den
falschen Namen trug und in den Einstellungen nach einer Zeichenfolge gesucht
wurde, die dort nicht steht.

## Wenn zwei Agenten dasselbe tun

Vor dem Anlegen eines Branches mit vorgegebenem Namen prüfen, ob es ihn schon
gibt:

```bash
git ls-remote --heads origin claude/<name> | wc -l
```

Steht dort `1`, arbeitet jemand anderes daran — mit Schreibrecht auf denselben
Ref.

Ein PR mit leerem Diff wird geschlossen, nicht gemergt. Der Test ist
`get_files` auf dem PR: kommt `[]` zurück, ändert er nichts. Ein grüner Check
sagt dazu nichts — die CI prüft den Head, nicht die Differenz zur Basis.

Am 21.8.2026 liefen zwei Sessions dieselbe Aufgabe über 45 Repos, auf den
Branches `claude/codex-review-audit-templates-9sn6mx` und
`claude/codex-review-audit-7ioh56`. Wo die eine zuerst nach `main` kam, wurde
`main` in den Branch der anderen gemergt und der add/add-Konflikt zugunsten
von `main` aufgelöst. Übrig blieben 14 PRs, die durch sämtliche Gates grün
liefen und nichts enthielten; sie wurden gemergt und hinterliessen leere
Merge-Commits. Mit den zwei Folge-PRs, die aus demselben Grund gegenstandslos
waren, waren 16 der 59 PRs jenes Tages reine Reibung.

Dieselbe Klasse wie der handgeschriebene Stub, der denselben Feldnamen annahm
wie der Code: Nichts ist rot, weil nichts geprüft wird, worauf es ankommt.

## Dieses Repo

**ruff: eine Quelle, plus der Hook.** Der Pin steht im dev-Extra von
`pyproject.toml`. `.pre-commit-config.yaml` trägt dieselbe Zahl ein zweites
Mal (als `rev:`), weil pre-commit `pyproject.toml` nicht lesen kann — beide
zusammen bumpen. Die Version steht bewusst nicht hier;
`tests/test_ruff_pin_doku.py` hält sie draussen. Die Workflows pinnen
**nicht** selbst.

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
python scripts/check_ruff_pin.py
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

Der Lauf hat zwei Ziele. `main` installiert den Quellcode (`pip install -e`),
`pypi` das neueste Paket von PyPI und fährt dagegen die Suite **seines**
Release-Tags, mit entferntem `src/` und belegtem Import aus `site-packages`.
Jedes Ziel führt sein eigenes Issue. `main` grün und `pypi` rot heisst: der Fix
liegt im Quellcode, nicht im Paket — ein Release ist fällig. Genau das sah bis
2026-09-27 niemand; 0.2.5 lag sieben Wochen kaputt auf PyPI, während dieser Lauf
grün war. Gemessen mit den `run:`-Blöcken des Workflows: Suite v0.2.5 gegen
Paket 0.2.5 → `finding` an `test_elcom_zurich_tariffs_live`, 0.3.0 → `clear`.
`tests/test_live_artifact_workflow.py` hält den Aufbau fest.

**Release-Gate:** `publish.yml` fährt `scripts/check_release_artifacts.py`
im `build`-Job zwischen `python -m build` und dem Upload des Artefakts. Es
prüft das gebaute Wheel (mcp-name-Marker in der METADATA, description ≤ 100,
server.json = pyproject, Tag = gebaute Version); scheitert es, erreicht nichts
PyPI oder die Registry. Das Skript ist eine Kopie aus dem Skill `github-repo`,
mit unveränderter Logik — Änderungen dort nachziehen. Es prüft Metadaten,
nicht Verhalten: dass 0.2.5 sieben Wochen lang kaputt auf PyPI lag, während
`main` repariert war, hätte es nicht gefunden. `tests/test_release_gate.py`
fährt es zusätzlich gegen die echten Quelldateien, damit ein Fund schon im PR
auffällt und nicht erst beim Tag.

**Lieferkette in `publish.yml`:** Jede Action steht auf einem Commit-SHA mit
`# vX.Y.Z` dahinter; Dependabot (github-actions, monatlich) hebt beides
gemeinsam an. `mcp-publisher` kennt Dependabot nicht — Anheben von Hand:

```bash
V=1.8.1   # neue Version aus: git ls-remote --tags https://github.com/modelcontextprotocol/registry
curl -fsSLO "https://github.com/modelcontextprotocol/registry/releases/download/v$V/registry_${V}_checksums.txt"
grep ' mcp-publisher_linux_amd64.tar.gz$' "registry_${V}_checksums.txt"
```

Den Hash nach `MCP_PUBLISHER_SHA256`, die Version nach `MCP_PUBLISHER_VERSION`.
Dann das Archiv laden, `sha256sum -c`, entpacken und `./mcp-publisher --version`
lesen: der dort genannte Commit muss der des Tags sein. Die checksums-Datei ist
Quelle beim Anheben, nicht Prüfung zur Laufzeit — zur Laufzeit gilt nur der Hash
im Workflow. `releases/latest` löst hinter dem Agent-Proxy nicht auf (403); die
Version aus `git ls-remote --tags` nehmen. `tests/test_publish_hardening.py`
hält SHA-Pins, Versionskommentare, feste Version und Prüfsumme vor dem Entpacken
und die Timeouts fest.

**SDK-Name in der Doku:** `tests/test_sdk_name_drift.py` scannt alle
versionierten Dateien auf den Namen der SDK-Klasse vor dem Wechsel auf
`mcp[cli]>=2` (Muster `ALTER_NAME` im Test) — ausser `CHANGELOG.md` und `audits/`,
die den Server beschreiben, wie er war — und prüft, dass die Klasse, die
`server.mcp` zur Laufzeit ist, im Architektur-Diagramm von `README.md` steht.
Wer den alten Namen bewusst in eine neue Datei schreibt (etwa eine
Migrationsnotiz), trägt sie in `HISTORIE` ein; nicht die Wache abschwächen.
Auch dieser Absatz fiel ihr beim Schreiben zum Opfer, deshalb nennt er den
Namen nicht.

**Fixtures:** `scripts/record_fixtures.py` erzeugt sie, Aufnahmedatum steht in
`tests/fixtures/PROVENANCE.md`. Nicht von Hand pflegen.

**`pin_audit.py` steht an drei Stellen.** `swiss-electricity-mcp`, `bakom-mcp`
und `register-mcp` halten byteweise dieselbe `scripts/pin_audit.py` samt
`tests/test_pin_audit.py`. Wer eine ändert, ändert alle drei im selben Commit —
sonst misst der eine Server anders als der andere, und das ist genau die Drift,
gegen die das Werkzeug gebaut ist. Kein Gate erzwingt das, es gibt nur diesen
Absatz. Aus dem Verzeichnis, in dem die Server nebeneinander liegen:

```bash
sha256sum */scripts/pin_audit.py */tests/test_pin_audit.py |
  awk '{print $1}' | sort | uniq -c
```

Erwartet: **zwei** Zeilen mit je **3**. Die Anzahl mitlesen, nicht nur die Zahl
der Zeilen — findet der Glob nur ein Repo, stehen dort auch zwei Zeilen, und
«einig» hiesse dann bloss, dass nichts verglichen wurde.

**Der SessionStart-Hook steht an drei Stellen.** `swiss-electricity-mcp`,
`bakom-mcp` und `register-mcp` halten byteweise dieselben drei Dateien:
`.claude/hooks/check-clone-freshness.sh`, `.claude/hooks/README.md` und
`tests/test_session_start_hook.py`. Wer eine ändert, ändert alle drei im selben
Commit — sonst driften die Fassungen auseinander, und genau das war der
Ausgangszustand: drei eigenständige Implementierungen mit drei Dateinamen, von
denen eine ohne `timeout` im PATH ungebremst ins Netz ging und die Session
anhalten konnte. `.claude/settings.json` ist bewusst **nicht** Teil der Regel
(dort steht Repo-Eigenes); geprüft wird es stattdessen vom Test, der die
Registrierung des Hooks nachweist.

Kein Gate erzwingt die Gleichheit, es gibt nur diesen Absatz. Aus dem
Verzeichnis, in dem die Server nebeneinander liegen:

```bash
sha256sum */.claude/hooks/check-clone-freshness.sh */.claude/hooks/README.md \
          */tests/test_session_start_hook.py |
  awk '{print $1}' | sort | uniq -c
```

Erwartet: **drei** Zeilen mit je **3**. Die Anzahl mitlesen, nicht nur die Zahl
der Zeilen — findet der Glob nur ein Repo, stehen dort auch drei Zeilen, und
«einig» hiesse dann bloss, dass nichts verglichen wurde.
