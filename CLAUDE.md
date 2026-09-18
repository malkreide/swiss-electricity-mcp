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
  als Entwarnung für die gesperrte nehmen. Das ist dieselbe Asymmetrie wie
  bei der verschwundenen Codex-Meldung weiter unten.

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

Ein Codex-Review auf einem PR wird beantwortet oder behoben, nie ignoriert.

## Wenn Codex gar nicht erst hinsieht

Die Zeile oben unterstellt, dass es einen Befund geben *kann*. Das ist nicht
immer so, und man sieht es dem PR nicht an.

Am 21.8.2026 war das Code-Review-Kontingent zwischen 08:41 und 09:48
aufgebraucht — davor echte Reviews, danach in 30 Repos nur noch:

```
You have reached your Codex usage limits for code reviews.
```

**Der Wortlaut ist nicht stabil.** Am 18.9.2026 lautete dieselbe Meldung auf
`swiss-electricity-mcp` PR #76:

```
You have reached your Codex usage limits. You can see your limits in the
[Codex usage dashboard](https://chatgpt.com/codex/cloud/settings/usage).
```

Sechzehn Minuten später, auf PR #77 desselben Repos, eine **dritte** Fassung:

```
You have reached your Codex usage limits for code reviews. You can see your
limits in the [Codex usage dashboard](https://chatgpt.com/codex/cloud/settings/usage).
```

Wer auf eine dieser Zeichenketten prüft — und das ist die naheliegende
Automatisierung —, übersieht die anderen. **Auf `usage limits` prüfen, nicht
auf den ganzen Satz.**

Die drei Fassungen unterscheiden sich auf **zwei** Achsen, und nur eine davon
trägt Bedeutung:

- *Der Dashboard-Satz* fehlt nur in der Fassung vom 21.8. und steht in beiden
  vom 18.9. Das sieht nach einer Vorlagenänderung zwischen den Daten aus, nicht
  nach einer Aussage.
- *«for code reviews»* steht dort, wo ein **Code-Review** abgelehnt wurde
  (21.8. nach Review-Auslösern; 18.9. um 06:54:43Z, zwei Sekunden nachdem PR #77
  von Draft auf ready ging), und fehlt dort, wo etwas **anderes** abgelehnt
  wurde (18.9. um 06:38:37Z, im Review-Thread nach einer Antwort). Drei
  Beobachtungen, alle drei konsistent.

Falls das trägt, sagt der Zusatz mit, *welcher* Topf leer ist — Code-Reviews
haben laut Codex einen eigenen. Und er stützt nebenbei die offene Frage weiter
unten, was die Thread-Meldung ausgelöst hat: Ohne «for code reviews» war es
offenbar kein Review-Versuch, sondern der Versuch, auf die Antwort zu
antworten. Drei Beobachtungen sind kein Beleg, aber sie zeigen, worauf beim
nächsten Mal zu achten ist.

**Die Meldung kommt schnell.** Zwei Sekunden nach dem Auslöser auf PR #77,
zehn Sekunden auf PR #76. Ein echter Lauf brauchte dagegen acht Sekunden bis
zur `🔄 Running`-Tabelle und danach 73 bis 80 Sekunden bis `✅ Completed`. Wer
binnen weniger Sekunden einen Bot-Kommentar sieht, hat eher eine Absage vor
sich als ein Urteil — ein Anhaltspunkt, kein Beweis.

**Und sie wechselt den Zustellweg.** Am 18.9. kam sie um 06:38:37Z als
Review-Kommentar im Thread und um 06:54:43Z als gewöhnlicher Issue-Kommentar.
Zwei Meldungen desselben Typs, sechzehn Minuten auseinander, in zwei
verschiedenen Abfragen — deshalb die drei Abfragen weiter unten.

Wie lange die Sperre dauerte, geben die Beobachtungen nur als Spanne her. Vier
Zeitpunkte sind belegt: letzter gelungener Review am 21.8. um 08:41, erste
Limit-Meldung um 09:48, letzte beobachtete Limit-Meldung am 22.8. um 11:03,
erste *andere* Meldung am 23.8. um 08:22.

Zwischen erster und letzter Limit-Meldung liegen **25 h 15 min**. Das ist der
Abstand zweier Fehlschläge, nicht die Dauer einer Sperre. Wer ihn Untergrenze
nennt, hat die durchgehende Erschöpfung schon vorausgesetzt, die er belegen
soll: Öffnete sich das Fenster zwischendurch und schloss es sich durch neue
Auslöser wieder, waren es zwei kurze Sperren und nie eine von 25 Stunden.
Untergrenze einer *einzelnen* Sperre sind die 25 h 15 min nur unter genau dieser
Annahme — und die ist unbelegt.

Nach oben trägt die Rechnung dagegen. Die längste mit den Beobachtungen
verträgliche Sperre reicht vom letzten Erfolg um 08:41 bis zur abweichenden
Meldung um 08:22, also **47 h 41 min**; länger kann keine einzelne gewesen sein.
Wer stattdessen ab der ersten Limit-Meldung rechnet, unterschlägt die 67
Minuten, in denen das Kontingent schon weg gewesen sein kann, und nennt die
Spanne zwischen zwei Beobachtungen eine Obergrenze.

Beobachtungspunkte sind keine Messreihe — die 21 Stunden vor der abweichenden
Meldung liefen ganz ohne Codex-Auslöser, dort hat niemand gemessen.

In der Zwischenzeit sind 32 PRs mit formal erfülltem Häkchen gemergt worden,
ohne dass jemand hineingesehen hat, und am 22.8. noch einmal 43.

**Vier** Gründe, warum Codex schweigt, und nur einer davon ist harmlos:

- **Kein Befund** — dann schreibt er einen gewöhnlichen Issue-Kommentar:

  ```
  Codex Review: Didn't find any major issues. Swish!
  ```

  Der Schlusssatz wechselt bei jedem Lauf («Delightful!», «Keep it up!»,
  «More of your lovely PRs please.»); stabil ist nur der Satz davor. Der
  Infokasten, den Codex unter jeden Review setzt, behauptet weiterhin eine
  Reaktion («otherwise it will react with 👍») — am 23.8. kam in sechs Repos
  die Meldung und in keinem die Reaktion. Der Kasten ist keine Quelle. Am
  18.9.2026 behauptete er auf `swiss-electricity-mcp` PR #75 zusätzlich eine
  Reaktion *während* des Laufs («reacts with 👀 while any review is running»);
  gemessen wurde zweimal `reactions.total_count: 0` — einmal bei laufendem,
  einmal bei fertigem Review. Beide Reaktions-Behauptungen des Kastens sind
  damit unabhängig voneinander widerlegt.
- **Der PR ist ein Draft** — darauf läuft Codex nicht an.
- **Das Kontingent ist weg** — dann schreibt er die Meldung oben.
- **Für das Repo fehlt eine Environment** — dann schreibt er:

  ```
  To use Codex here, create an environment for this repo.
  ```

Der vierte kam erst zum Vorschein, als der dritte wegfiel, und das ist kein
Zufall: Die Prüfungen liegen hintereinander. Dass es diese Reihenfolge ist und
nicht die umgekehrte, lässt sich an einem einzigen Repo ablesen — in
`swiss-public-data-mcp` bekam PR #54 am 22.8. um 10:56:55 die Kontingent-Meldung
und PR #56 am 23.8. um 08:22:20 die Environment-Meldung. Läge die
Environment-Prüfung vorn, hätte #54 sie schon am Vortag gesehen; die Environment
fehlte ja bereits. Zwei Meldungen aus demselben Repo schlagen hier jede
Vermutung über die Reihenfolge.

Praktisch heisst das: **Eine verschwundene Limit-Meldung ist keine Entwarnung.**
Sie kann bedeuten, dass das Kontingent wieder da ist — und dass jetzt etwas
anderes den Review verhindert. Belegt ist eine Prüfung erst durch ein
Review-Objekt **oder** eine Befundlos-Meldung. Wer nur das Objekt gelten lässt,
zählt jeden befundlosen Review als ungeprüft — und baut sich denselben Fehlalarm
ein, den dieser Abschnitt verhindern soll, nur in die andere Richtung.

«Kein Kommentar» heisst also nicht «geprüft und sauber». Unterscheiden lässt es
sich an der Form: Ein Review **mit** Befund ist ein Review-Objekt
(«💡 Codex Review», mit Commit-Angabe); ein Review **ohne** Befund und die
beiden Ausfallmeldungen — Kontingent wie Environment — sind gewöhnliche
Issue-Kommentare und trennen sich nur im Text — wobei die beiden
Ausfallmeldungen auch in einem Review-Thread stehen können, siehe unten. Beim Draft gibt es überhaupt
nichts, weil Codex nicht anläuft; ein kommentarloser Draft ist deshalb kein
Beleg, sondern ein nicht durchgeführter Test.

Das sind **drei** verschiedene Abfragen, nicht zwei: `get_reviews` fürs Objekt,
`get_comments` für die Issue-Kommentare und `get_review_comments` für die
Kommentare *in* einem Review-Thread. Wer nur eine nimmt, übersieht den Rest.
Genau so ist die Limit-Meldung zuerst durchgerutscht.

**Die dritte Abfrage fehlte hier zwei Fassungen lang**, und die Regel darüber
war mit ihr falsch: Am 18.9.2026 kam die Kontingent-Meldung auf
`swiss-electricity-mcp` PR #76 nicht als Issue-Kommentar, sondern als
Review-Kommentar im Thread des Befundes — auf `CLAUDE.md` Zeile 335, als
Antwort auf eine Antwort. `get_comments` hätte sie nicht gefunden; dort stand
zur selben Zeit unverändert die Zusammenfassungstabelle. Die Ausfallmeldungen
sind also nicht an die Kommentarart gebunden, sondern folgen dem Ort, an dem
Codex gerade etwas zu sagen versucht.

Was diese Meldung **ausgelöst** hat, ist offen. Sie kam zehn Sekunden nach
einer Antwort in ihrem Thread, und der Infokasten sagt, Codex könne Fragen
beantworten («Codex can also answer questions or update the PR») — eine
Antwort im Thread als Auslöser liegt also nahe. Dagegen steht, dass eine
zweite Antwort 88 Sekunden später keine weitere Meldung brachte. Beides passt
auch zu «Codex versucht es nach erschöpftem Kontingent kein zweites Mal».
Zwei Beobachtungen trennen das nicht.

Der Kommentarzähler allein reicht ohnehin nicht: `comments: 1` kann die
Befundlos-, die Kontingent-, die Environment-Meldung **oder** die
Status-Zusammenfassung von unten sein — vier gegensätzliche Bedeutungen unter
derselben Zahl, darunter eine, die noch gar kein Urteil ist. Den Text lesen,
nicht die Zahl. Und einen unbekannten Text wörtlich zitieren, statt ihn in eine
der bekannten Schubladen zu zwingen: Dieser Abschnitt musste schon zweimal
wachsen — von drei auf vier Gründe, und jetzt von drei auf vier Texte —, und die
👍-Reaktion stand hier zwei Fassungen lang als Tatsache.

**Die vierte Form: eine Status-Tabelle, die sich selbst überschreibt.** Am
18.9.2026 trug `swiss-electricity-mcp` PR #75 genau einen Kommentar von
`chatgpt-codex-connector[bot]`, beginnend mit dem Marker
`<!-- codex-pull-request-review-summary -->`:

```
## Codex Review Summary

| Review | Status | Commit | Review trigger |
| 📝 **Code Review** | 🔄 **Running** since 2026-09-18T06:07:37Z | `f78ff46` | Draft marked ready |
```

Neunzig Sekunden später stand in **demselben** Kommentar — gleiche `id`
`5725925275`, gleiches `created_at` 06:07:39Z, `updated_at` von 06:07:39Z auf
06:08:58Z gewandert:

```
| 📝 **Code Review** | ✅ **Completed** 2026-09-18T06:08:57Z | `f78ff46` | Draft marked ready |
```

Das ist die gefährlichste der vier, weil sie als einzige ihre Bedeutung
*ändert*, ohne dass sich Zähler, `id` oder `created_at` bewegen. Ein Blick
während des Laufs und ein Blick danach liefern denselben Kommentar mit
entgegengesetzter Aussage.

**Erkannt wird das am Status-Feld, nicht am Zeitstempel: nachfassen, bis ein
Endzustand dasteht.** `🔄 Running` gegen `✅ Completed` ist die Unterscheidung;
`updated_at` sagt nur, dass der Kommentar überschrieben *wurde*, nicht wohin.
Ein bewegter Zeitstempel ist damit kein Beleg für einen Abschluss — er ist
nicht einmal gerichtet.

`updated_at` behält eine schmalere, richtige Aufgabe: es **datiert** eine
Momentaufnahme. Wer die Tabelle abschreibt — in eine Notiz, einen Bericht, eine
Statuszeile —, schreibt einen Zwischenstand ab, und ohne den Zeitstempel daneben
steht später ein Urteil, das nie eines war. `created_at` leistet auch das nicht:
es bleibt beim ersten Schreiben stehen.

Zwei Dinge, die hier naheliegen und **nicht gemessen** sind. Ob ein zweiter
Review denselben Kommentar wiederverwendet und ihn auf `🔄 Running`
zurücksetzt: Die Kopfzeile sagt «This comment shows the *latest* Codex review
activity on this pull request», und die `id` blieb innerhalb eines Laufs
stabil — beobachtet wurde aber auf beiden PRs nur je **ein** Lauf, das
Überschreiben also nur innerhalb eines Lebenszyklus (`Running` → `Completed`).
Und ob ein blosser Push einen Review auslöst: Der Infokasten listet nur «open
a PR for review», «mark a draft as ready» und «@codex review» — gemessen ist es
nicht.

Hier stand zwei Fassungen lang eine Messung, die keine war: Nach drei Pushes
auf den offenen PR #76 (`ee0df1f`, `d792650`, `ea6257e`) blieb die Tabelle auf
`✅ Completed` für den **vorherigen** Commit `4dc4e8f` stehen, und daraus war
geschlossen worden, ein Push löse keinen Review aus. Das Kontingent war zu
diesem Zeitpunkt aber bereits erschöpft: belegt spätestens für 06:38:37Z, und
wann es eintrat, ist offen — gut möglich, dass der Review von `4dc4e8f` selbst
es verbrauchte, der um 06:36:36Z endete. Der erste Push lag dazwischen, die
beiden anderen danach.

**Ein Prüfer, der ohnehin nicht antworten kann, misst nichts.** Es war also
nicht «Push löst nicht aus» gemessen, sondern «ein erschöpftes Kontingent
antwortet nicht» — dasselbe wie die 39 Repos mit «Label fehlt» weiter oben, nur
in einem anderen Werkzeug: die eigene Erschöpfung gemessen und für einen Befund
über die Quelle gehalten. Es fehlte die Positivkontrolle.

Wie die Messung gehen müsste: erst durch einen echten Lauf zeigen, dass Codex
antwortfähig ist — ein PR auf «ready», bis `✅ Completed` dasteht —, dann einen
zweiten Commit pushen und den Commit **in der Tabelle** lesen. Bleibt er auf
dem alten Stand, sagt das etwas über Pushes. Ohne den vorangegangenen
erfolgreichen Lauf sagt es nichts.

Der Reihenfolge wegen: Beide Sätze standen hier schon einmal als Tatsache, in
derselben Fassung, die den Fehler unten korrigierte. Wer eine Regel
zurechtrückt, baut dabei gern die nächste unbelegte ein. Und der zweite Anlauf
war auch noch nicht der letzte: Er ersetzte den unbelegten Satz durch eine
Messung ohne Positivkontrolle — eine Fehlerform, die schon zweimal in dieser
Datei steht, hier aber nicht wiedererkannt wurde, weil sie diesmal nicht von
einem Statuscode kam, sondern von einem ausbleibenden Kommentar.

Diese Fassung ist die zweite. Die erste machte `updated_at` zur Erkennungsregel
und behauptete, «Codex hat nichts geschrieben» und «Codex war noch nicht fertig»
seien nur am Zeitstempel zu trennen — beides falsch: Die beiden Fälle trennt
schon, ob überhaupt ein Kommentar da ist, und ein bewegter Zeitstempel belegt
keinen Endzustand. Aufgefallen ist es durch einen Codex-Review (P2) auf
`swiss-electricity-mcp` PR #76 — also auf genau dem PR, der diesen Abschnitt
einführte. Der Abschnitt über die Grenzen einer Momentaufnahme hatte selbst eine
Momentaufnahme zur Regel erhoben.

Die Tabelle ist **kein fünfter Grund fürs Schweigen** — genau andersherum: sie
ist der Beleg, dass er hingesehen *hat*, mitsamt Commit-SHA und Auslöser. Beim
Aufschreiben war sie zuerst in die Vierer-Liste oben einsortiert worden, und
das ist falsch: dort stehen Gründe, warum kein Review stattfindet, hier steht
einer, der stattgefunden hat. Dieselbe Verwechslung wie bei `lotId` und beim
403 — nicht der Text entscheidet, in welche Liste etwas gehört, sondern was er
über die *Quelle* aussagt.

Was die Beobachtung **nicht** hergibt: ob `✅ Completed` ohne Begleitkommentar
«kein Befund» heisst. Weder ein Review-Objekt noch die «Swish!»-Meldung kam,
`get_reviews` blieb durchgehend `[]`. Möglich, dass diese Codex-Fassung die
Befundlos-Meldung durch die Tabelle ersetzt hat; möglich auch, dass beides
nebeneinander existiert und hier nur eines auftrat. Eine einzelne Beobachtung
an einem PR trennt das nicht. Bis dahin gilt die Regel oben unverändert: belegt
ist Befundlosigkeit durch ein Review-Objekt oder die Befundlos-Meldung — und
`✅ Completed` ist keines von beidem.

Und ein befundloser Lauf ist kein Freispruch. Am 23.8. lief derselbe Text durch
42 Reviews: 36 meldeten denselben P2-Befund, 6 die Befundlos-Meldung — gleiche
Eingabe, gegenteiliges Urteil, alles in denselben neun Minuten. Ein sauberer
Lauf sagt damit etwas über den Lauf, nicht über den Text. Wer sein Häkchen
daran hängt, hängt es an einen Münzwurf.

Portfolio-weit nachsehen:

```
search_pull_requests: user:malkreide commenter:chatgpt-codex-connector[bot] updated:>=<Datum>
```

Findet nur, wo er *kommentiert* hat. Repos ohne PR-Aktivität tauchen nicht auf
— das ist kein Beleg, dass dort geprüft wurde.

Zweiter Weg, den Prüfer zu verlieren, ganz ohne Kontingentproblem: zu schnell
mergen. Am 21./22.8. lagen zwischen «ready for review» und Merge mehrfach drei
bis fünf Sekunden. Codex wird beim Umschalten von Draft auf ready ausgelöst und
braucht danach Zeit; wer sofort mergt, hat das Häkchen gesetzt und den Review
nicht abgewartet.

Am 18.9.2026 ist derselbe Ablauf auf `swiss-electricity-mcp` PR #75 sekundengenau
protokolliert:

| Zeit (UTC) | Ereignis |
|---|---|
| 06:07:29 | Draft → «ready for review» |
| 06:07:32 | **gemergt** |
| 06:07:37 | Codex startet den Review |
| 06:08:57 | Codex ist fertig |

Der Merge lag **fünf Sekunden vor** dem Start der Prüfung und 85 Sekunden vor
ihrem Ende. Das Häkchen «kein offener Befund beim Merge» war zum Zeitpunkt des
Merges nicht bloss ungesetzt, es war nicht setzbar.

Zwei Dinge, die dieser Fall zusätzlich zeigt. Erstens: **Der Merge bricht den
Review nicht ab.** Codex lief auf dem geschlossenen PR zu Ende, das Ergebnis ist
also nachlesbar — nur gated es nichts mehr, und ein Befund träfe Code, der
bereits in `main` steht. Zweitens: **Wer eine Minute nach dem Merge nachsieht,
liest womöglich `🔄 Running` und hält es für Schweigen.** Das ist der
praktische Grund für die Status-Regel oben: nachfassen, bis ein Endzustand
dasteht.

Das Kontingent hängt am Konto, nicht am Repo, und Code-Reviews haben einen
eigenen Topf — nur GitHub-getriggerte Reviews zählen hinein. ChatGPT-Pläne
fahren ein rollendes Fünf-Stunden-Fenster plus Wochenlimits; welches greift,
steht im Codex-Dashboard. Welches hier griff, ist **offen**. Die Lücke oben
schliesst das Fünf-Stunden-Fenster nicht aus: Es kann sich zwischendurch
geöffnet und durch neue Auslöser wieder erschöpft haben. Das auszuschliessen
bräuchte den Nachweis, dass in der ganzen Spanne kein einziger Review durchlief
— den gibt es nicht, weil nur Fehlschläge beobachtet wurden. Eine lange Reihe
von Fehlschlägen belegt eine lange Reihe von Fehlschlägen, nicht ihre Ursache.

Zeigt das Dashboard freies Kontingent, während Reviews weiter scheitern, ist
das ein bekannter Fehler bei mehreren verbundenen Konten — dann den
GitHub-Connector in den Codex-Einstellungen trennen und neu verbinden.

Die Environment legt man unter `chatgpt.com/codex/cloud/settings/environments`
an, und zwar **je Repo**. Die Meldung sagt es selbst («for this repo»), und am
23.8. war es genau so: In `swiss-public-data-mcp` fehlte sie, dort kam kein
Review; in den übrigen Repos lief Codex am selben Morgen durch. Eine
Environment fürs Konto genügt also nicht — wer eine anlegt und den Rest für
erledigt hält, mergt weiter Ungeprüftes.

---

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

**ruff: eine Quelle, plus der Hook.** Der Pin `0.16.3` steht im dev-Extra von
`pyproject.toml`. `.pre-commit-config.yaml` trägt dieselbe Zahl ein zweites Mal
(`rev: v0.16.3`), weil pre-commit `pyproject.toml` nicht lesen kann — beide
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
