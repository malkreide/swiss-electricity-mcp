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
- *«for code reviews»* steht dort, wo ein **Code-Review** abgelehnt wurde, und
  fehlt dort, wo etwas **anderes** abgelehnt wurde. Sechs Beobachtungen, alle
  konsistent:

  | Zeit (UTC) | Anlass | Zusatz |
  |---|---|---|
  | 21.8. | Review-Auslöser, 30 Repos | ja |
  | 18.9. 06:38:37 | Antwort in einem Review-Thread | **nein** |
  | 18.9. 06:54:43 | `swiss-electricity-mcp` #77 auf ready | ja |
  | 18.9. 07:01:59 | `swiss-electricity-mcp` #78 auf ready | ja |
  | 18.9. 07:57:05 | `swiss-electricity-mcp` #79 auf ready | ja |
  | 18.9. 08:33:16 | `bakom-mcp` #97 auf ready | ja |
  | 18.9. 14:37:35 | `swiss-electricity-mcp` #84 auf ready | ja |
  | 18.9. 14:44:21 | `swiss-electricity-mcp` #85 auf ready | ja |

Falls das trägt, sagt der Zusatz mit, *welcher* Topf leer ist — Code-Reviews
haben laut Codex einen eigenen. Und er stützt nebenbei die offene Frage weiter
unten, was die Thread-Meldung ausgelöst hat: Ohne «for code reviews» war es
offenbar kein Review-Versuch, sondern der Versuch, auf die Antwort zu
antworten. Drei Beobachtungen sind kein Beleg, aber sie zeigen, worauf beim
nächsten Mal zu achten ist.

**Die Meldung kommt schnell.** Zwischen Auslöser und Absage lagen 2 bis 10
Sekunden (2 s auf #77, 5 s auf #78, 2 s auf #79, 3 s auf `bakom-mcp` #97,
10 s auf #76, 5 s auf #84). Ein echter Lauf brauchte dagegen 6 bis 8 Sekunden
bis zur `🔄 Running`-Tabelle und danach 67 bis 723 Sekunden bis `✅ Completed`. Wer
binnen weniger Sekunden einen Bot-Kommentar sieht, hat eher eine Absage vor
sich als ein Urteil — ein Anhaltspunkt, kein Beweis.

**Die Laufdauer taugt nicht als Schwelle.** Sie stand an einem einzigen Tag
nacheinander auf 73–80, 71–80, 67–80, 67–128 und schliesslich **67–723**
Sekunden. Zuerst verdoppelte der Lauf auf PR #82 mit 128 s das Maximum fast,
dann brauchte der auf PR #83 **zwölf Minuten** — das Fünffache davon, und mehr
als das Zehnfache der Untergrenze. Viermal an einem Tag nach aussen korrigiert,
jedes Mal mit demselben Ergebnis: Die Zahl beschreibt die bisher gesehenen
Läufe, nicht das System. Wer daraus eine Regel macht («länger als X heisst
hängengeblieben»), misst seine eigene Stichprobe.

Beim Lauf auf #83 war das keine Theorie. Nach neuneinhalb Minuten stand die
Tabelle unverändert auf `🔄 Running`, `updated_at` noch auf der Sekunde des
Anlegens — während auf #75 nach 90 Sekunden längst `✅ Completed` dort stand.
Die Versuchung, das für einen hängengebliebenen Lauf zu halten und eine neue
Kategorie aufzumachen, war gross. Zwei Minuten später kam ein vollständiger
Review mit Befund. **Ein Lauf ist nicht tot, nur weil er länger dauert als der
längste, den man kennt.**

**Und sie wechselt den Zustellweg.** Am 18.9. kam sie um 06:38:37Z als
Review-Kommentar im Thread und um 06:54:43Z als gewöhnlicher Issue-Kommentar.
Zwei Meldungen desselben Typs, sechzehn Minuten auseinander, in zwei
verschiedenen Abfragen — deshalb die drei Abfragen weiter unten.

**Fünf belegte Sperrzeitpunkte am 18.9.**, über zwei Repos: 06:38:37Z,
06:54:43Z, 07:01:59Z, 07:57:05Z und 08:33:16Z. Das sind
**Beobachtungspunkte, keine Dauer.** Zwischen ihnen wurde nicht gemessen, und
der Abstand zweier Fehlschläge ist keine Untergrenze einer einzelnen Sperre —
dieselbe Rechnung wie bei der Augustsperre weiter oben, und derselbe Fehler,
wenn man sie unterlässt. Jeder der fünf Punkte ist zugleich eine
fehlgeschlagene Positivkontrolle: An keinem lief ein Review an.

**Und dann lief wieder einer.** Um 12:39:08Z startete auf PR #80 ein echter
Review, 71 Sekunden später stand er auf `✅ Completed`. Die Sperre endete also
**zwischen 08:33:16Z und 12:39:08Z** — ein Intervall, keine Dauer: In den gut
vier Stunden dazwischen wurde nicht gemessen, sie kann jederzeit darin gefallen
sein. Das ist die Beobachtung, die dem Augustfall oben fehlt, wo nur
Fehlschläge notiert wurden und die Rechnung deshalb bis heute offen ist. Wer
eine Sperre eingrenzen will, braucht beides: den letzten belegten Fehlschlag
**und** den ersten belegten Erfolg.

**Und dann war es wieder weg.** Vier Reviews liefen nach dem Ende der
Vormittagssperre — 12:39:08Z (#80), 12:49:08Z (#81), 13:04:05Z (#82),
13:14:38Z (#83). Um 14:37:35Z kam auf #84 wieder die Kontingent-Meldung. Die
Erschöpfung fiel also **zwischen 13:14:38Z und 14:37:35Z**, 83 Minuten, in
denen nicht gemessen wurde. Und das passt zum rollenden Fünf-Stunden-Fenster,
beweist es aber nicht: Vier Läufe verbrauchen etwas, wie viel, sagt keine
dieser Beobachtungen.

Sieben Minuten später, um 14:44:21Z, kam auf PR #85 dieselbe Meldung. Das ist
ein **zweiter Beobachtungspunkt, keine Dauer** — und der Reflex, aus 14:37:35Z
und 14:44:21Z «mindestens sieben Minuten» zu machen, ist derselbe, den die
Augustrechnung weiter unten schon einmal falsch gemacht hat. Die obere Grenze
dieser zweiten Sperre ist **offen**: Der erste Erfolg danach wurde nicht
beobachtet, und ohne ihn lässt sie sich nicht schliessen. Von der ersten Sperre
des Tages unterscheidet sie genau das.

**Die Untergrenze ist der Start des letzten Laufs, nicht sein Ende.** Beim
Aufschreiben stand hier zuerst 13:26:41Z, der Zeitpunkt, an dem der Lauf auf
#83 auf `✅ Completed` sprang. Das ist falsch, und zwar auf die Art, die diese
Datei überall sonst anmahnt: Geprüft wird das Kontingent, wenn ein Auslöser
angenommen wird. Dass ein bereits laufender Review zu Ende geht, sagt über den
Kontingentstand in jenem Moment nichts — der Lauf wurde nur nicht abgebrochen,
und dass ein Merge ihn nicht abbricht, steht weiter unten als eigener Befund.
Die späteren zwölf Minuten dem gemessenen Fenster zuzuschlagen hiesse, eine
Vermutung als Messpunkt zu führen.

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
  gemessen wurde `reactions.total_count: 0` in **jeder** Ablesung des
  Tages. Entscheidend ist nicht deren Anzahl, sondern welche Zustände
  darunter sind: vier
  **echte** Läufe im Zustand `🔄 Running` (dort behauptet der Kasten 👀) und
  vier **echte** Läufe im Zustand `✅ Completed` ohne Befund (dort behauptet er
  👍). Beide Behauptungen sind damit genau in den Zuständen widerlegt, für die
  sie aufgestellt werden — nicht bloss an Absagen, wo ohnehin nichts zu
  erwarten wäre.
- **Der PR ist ein Draft** — darauf läuft kein Review an. Schweigen ist das
  aber nicht zwingend, siehe unten.
- **Das Kontingent ist weg** — dann schreibt er die Meldung oben.
- **Für das Repo fehlt eine Environment** — dann schreibt er:

  ```
  To use Codex here, create an environment for this repo.
  ```

  Der Umkehrschluss gilt nicht: Dieselbe Meldung kam auch dort, wo die
  Environment nachweislich vorhanden war, siehe unten.

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
Ausfallmeldungen auch in einem Review-Thread stehen können, siehe unten.
Auf einem Draft läuft kein Review an; ein kommentarloser Draft ist deshalb
kein Beleg, sondern ein nicht
durchgeführter Test. Dass dort **überhaupt nichts** komme, stimmt allerdings
nicht — siehe den Abschnitt zur Environment-Meldung.

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

Was hier naheliegt und **nicht gemessen** ist: ob ein zweiter Review denselben
Kommentar wiederverwendet und ihn auf `🔄 Running` zurücksetzt. Die Kopfzeile
sagt «This comment shows the *latest* Codex review activity on this pull
request», und die `id` blieb innerhalb eines Laufs stabil — beobachtet wurde
aber pro PR nur je **ein** Lauf, das Überschreiben also nur innerhalb eines
Lebenszyklus (`Running` → `Completed`). Die Frage bleibt offen, weil nie ein
zweiter Lauf auf demselben PR zustande kam.

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

**Am 18.9. um 13:07Z ist die Messung dann gelaufen, mit Positivkontrolle, und
das Ergebnis ist eindeutig: Ein blosser Push löst keinen Review aus.**

Die Anordnung, in dieser Reihenfolge:

| Zeit (UTC) | Schritt |
|---|---|
| 13:03:58 | PR #82 auf «ready» |
| 13:04:05 | Review startet — **Positivkontrolle**: Codex ist antwortfähig |
| 13:06:13 | `✅ Completed` für Commit `e0118f4`, kein Befund |
| ~13:07 | Push `e0118f4` → `57ec2f4` auf den **offenen** PR |
| 13:09:46 | PR gemergt |
| danach | Tabelle nennt weiterhin `e0118f4`, `updated_at` unverändert 13:06:14Z |

Der Kommentar wurde nach dem Push nicht mehr angefasst — kein neuer Lauf, kein
Rücksprung auf `🔄 Running`, kein zweiter Kommentar. Damit stimmt der
Infokasten ausnahmsweise: Ein Push steht nicht auf seiner Auslöser-Liste, und
er löst auch nichts aus.

**Der Lauf davor allein trägt das nicht** — so stand es hier zuerst, und ein
Codex-Review (P2) auf PR #83 hat es umgeworfen. Eine Positivkontrolle *vor* dem
Push belegt Antwortfähigkeit vor dem Push. Sie schliesst nicht aus, dass gerade
dieser Kontrolllauf den Rest des Kontingents verbrauchte und der Push auf ein
leeres traf — exakt die Lage, die diese Datei für `4dc4e8f` beschreibt, wo der
Lauf um 06:36:36Z endete und die Erschöpfung zwei Minuten später belegt war.
Wer mit einer Vorher-Kontrolle arbeitet, hat den Confounder also nur um einen
Lauf nach hinten geschoben.

Zwei Belege schliessen die Lücke, und sie sind unabhängig voneinander.

- **Eine Nachher-Kontrolle.** Um 13:14:38Z lief auf PR #83 ein Review an, mit
  dem Auslöser `Draft marked ready` — nach dem Push von ~13:07 und nach dem
  Merge von #82. Das Kontingent war danach also da. Was dieser Beleg nicht
  deckt: die siebeneinhalb Minuten dazwischen. Dass es genau im
  Zweieinhalb-Minuten-Fenster leer war und bis 13:14 zurückkehrte, ist mit ihm
  verträglich — nur spricht nichts dafür.
- **Die Absage bleibt nicht aus.** Das ist der stärkere Beleg, weil er vom
  Kontingentstand gar nicht abhängt. Ein Auslöser auf leeres Kontingent
  erzeugte in jedem beobachteten Fall binnen 2 bis 10 Sekunden eine Meldung —
  fünfmal am 18.9., in 30 Repos am 21.8. Wäre ein Push ein Auslöser, müsste
  also *eines von beiden* gekommen sein: ein Lauf bei vorhandenem Kontingent
  oder eine Absage bei leerem. Gekommen ist nichts. Beide Zweige von «Push ist
  ein Auslöser» sind damit ausgeschlossen, ohne dass man den Kontingentstand
  kennen muss.

Die Prämisse des zweiten Belegs gehört benannt: Sie ruht auf den *bekannten*
Auslösern — ready-Umschaltung und Antwort im Thread. Dass ein bislang
unbekannter Auslöser bei leerem Kontingent stumm bliebe, ist nicht geprüft und
auch nicht prüfbar, solange man ihn nicht kennt. Der Zirkel ist real, nur
schmal: Er verlangt einen Auslöser, der sich in beiden Zuständen anders verhält
als jeder beobachtete.

Und was sie nicht deckt: Das Fenster zwischen Push und Merge betrug rund
zweieinhalb Minuten. **Jeder** an diesem Tag beobachtete Lauf startete 6 bis
8 Sekunden nach seinem Auslöser — zuletzt der auf #83, sieben Sekunden nach dem
Klick auf «ready», und der brauchte danach zwölf Minuten. Die *Start*verzögerung
ist also stabil, während die Laufdauer es nicht ist; für dieses Fenster zählt
nur die erste. Ein ausgelöster Lauf wäre damit längst sichtbar
gewesen — ein stark verzögerter Trigger jenseits dieser zweieinhalb Minuten
bleibt unbeobachtet.

Der Reihenfolge wegen, und sie ist der eigentliche Lehrsatz dieses Abschnitts:
**Die Push-Frage wurde viermal beantwortet, dreimal falsch.** Erst als blosse
Behauptung. Dann als Messung ohne Positivkontrolle — eine Fehlerform, die schon
zweimal in dieser Datei steht, hier aber nicht wiedererkannt wurde, weil sie
diesmal nicht von einem Statuscode kam, sondern von einem ausbleibenden
Kommentar. Dann mit einer Positivkontrolle, die *vor* dem Push lag und den
Confounder damit nur um einen Lauf verschob; das fiel nicht selbst auf, sondern
durch den P2-Befund auf PR #83. Erst der vierte Anlauf steht.

Jeder dieser drei Fehlgriffe entstand beim Korrigieren des vorigen. Wer eine
Regel zurechtrückt, baut dabei gern die nächste unbelegte ein — und je näher
die Korrektur an der richtigen Antwort liegt, desto schwerer fällt es, die
verbliebene Lücke noch zu sehen. Der dritte Anlauf sah aus wie sauberes
Vorgehen: Er benannte seine Positivkontrolle ausdrücklich. Er benannte nur die
falsche.

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

Ob `✅ Completed` ohne Begleitkommentar «kein Befund» heisst, stand hier
zuerst als offene Frage. Sechs beobachtete Läufe am 18.9. ordnen sich sauber:

| PR | Ausgang | Was kam |
|---|---|---|
| #75 | kein Befund | nur die Tabelle auf `✅ Completed` |
| #76 | ein P2-Befund | **Review-Objekt** plus Tabelle |
| #80 | kein Befund | nur die Tabelle auf `✅ Completed` |
| #81 | kein Befund | nur die Tabelle auf `✅ Completed` |
| #82 | kein Befund | nur die Tabelle auf `✅ Completed` |
| #83 | ein P2-Befund | **Review-Objekt** plus Tabelle |

Die «Swish!»-Meldung kam in **keinem** der sechs. Das stützt deutlich, dass
diese Codex-Fassung sie durch die Tabelle ersetzt hat — bewiesen ist es nicht:
Sechs Läufe an einem Tag in einem Repo schliessen nicht aus, dass beide Formen
nebeneinander existieren und die eine hier nur nicht auftrat. Praktisch heisst
das trotzdem: Ein `✅ Completed` **ohne** Review-Objekt ist hier das Signal für
«geprüft, nichts gefunden» — und wer weiterhin auf die «Swish!»-Zeile wartet,
wartet auf einen Text, den diese Fassung nicht mehr schreibt.

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
bereits in `main` steht. Am selben Tag ein zweites Mal auf PR #80: ready
12:39:02Z, gemergt 12:39:07Z, Review-Start 12:39:08Z — der Merge lag **eine
Sekunde vor** dem Start, und der Lauf ging trotzdem bis `✅ Completed` durch.
Ein drittes Mal auf PR #81: ready 12:49:01Z, gemergt 12:49:04Z, Review-Start
12:49:08Z — vier Sekunden nach dem Merge angelaufen, 67 Sekunden später fertig.
Drei Belege an drei PRs: Der Merge beendet den Lauf nicht, er nimmt ihm nur die
Wirkung. Zweitens: **Wer eine Minute nach dem Merge nachsieht,
liest womöglich `🔄 Running` und hält es für Schweigen.** Das ist der
praktische Grund für die Status-Regel oben: nachfassen, bis ein Endzustand
dasteht.

**Auch die Absage erreicht den geschlossenen PR.** Am 18.9. auf PR #84:
`merged_at` 14:37:33Z, Kontingent-Meldung 14:37:35Z — zwei Sekunden **nach**
dem Merge. Der ready-Zeitpunkt liegt nur als Webhook-Zustellung vor (~14:37:30Z)
und ist hier nicht aus der API belegt; die Spanne ready→Merge ist also rund drei
Sekunden, aber nicht auf die Sekunde gemessen. Die beiden anderen Zeitpunkte
sind es.

Das ist **kein vierter Beleg** für den Satz oben, und der Unterschied ist der
ganze Punkt: Dort läuft ein Review weiter, hier lief nie einer. Gemeinsam ist
beiden nur, dass ein geschlossener PR weiterhin beschrieben wird; die Aussage
über die *Quelle* ist eine andere. Wer das zusammenwirft, hat wieder nach dem
Text sortiert statt nach dem, was er belegt — dieselbe Verwechslung wie bei
`lotId` und beim 403.

**Zwei Fehler zugleich, und nur einer war sichtbar.** Derselbe PR ist auch ein
weiterer Fall von «zu schnell gemergt» — rund drei Sekunden zwischen ready und
Merge, bei 6 bis 8 Sekunden allein bis zum Start eines Laufs, also im selben
Band wie die Fälle vom 21./22.8. Wer nur das sieht, schreibt «Review nicht
abgewartet» auf und hat die Hälfte. Das Kontingent war zu diesem Zeitpunkt
erschöpft — geprüft worden wäre der PR auch bei ruhigem Warten nicht. Zwei
unabhängige Ausfälle fielen zusammen, und der zweite kam nur ans Licht, weil
jemand den Text des Bot-Kommentars gelesen hat statt bloss seine Abwesenheit
oder seine Ankunftszeit. Genau dafür steht die Regel weiter oben: **den Text
lesen, nicht die Zahl.**

Das Kontingent hängt am Konto, nicht am Repo — am 18.9. erstmals an zwei
Repos **derselben** Sperre nachgemessen: `swiss-electricity-mcp` von 06:38:37Z
bis 07:57:05Z und `bakom-mcp` um 08:33:16Z, mit wortgleicher Meldung. Das
**stützt** den Satz, beweist ihn aber nicht: Ob `bakom-mcp` an jenem Tag eigene
Codex-Aktivität hatte, wurde nicht geprüft, ein separat erschöpfter eigener
Topf ist also nicht ausgeschlossen. Und Code-Reviews haben einen
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

**Die Meldung sagt aber nicht, warum sie kommt.** Am 18.9.2026 um 13:11:34Z
entstand `swiss-electricity-mcp` PR #83 als **Draft**. Vierzehn Sekunden später,
um 13:11:48Z, stand dort:

```
To use Codex here, create an environment for this repo.
```

Kein Umschalten auf «ready», kein `@codex review`, keine Zusammenfassungstabelle
— und im selben Repo war gut fünf Minuten vorher ein Review sauber durchgelaufen
(PR #82, 13:04:05Z bis 13:06:13Z). Die Positivkontrolle kam um 13:14:31Z: PR #83
auf «ready» gesetzt, sieben Sekunden später startete der Review mit dem Auslöser
`Draft marked ready`. **Die Environment existiert.** Die Meldung von 13:11:48Z
stand trotzdem da, und sie steht unverändert im PR — `updated_at` gleich
`created_at`, niemand hat sie zurückgenommen.

Zwei Gegenproben im selben Repo, beide am selben Vormittag: #81 und #82 waren
ebenfalls Drafts und trugen **keine** solche Meldung. Sie ist also weder eine
Eigenschaft des Repos noch eine des Draft-Zustands, sondern etwas
Vorübergehendes.

Daraus zwei Korrekturen weiter oben in diesem Abschnitt:

- **«Beim Draft gibt es überhaupt nichts» war falsch.** Richtig bleibt, dass auf
  einem Draft kein Review anläuft — eine Tabelle kam nicht. Codex schreibt dort
  aber trotzdem. Ein Kommentar auf einem Draft ist deshalb kein Beleg, dass
  geprüft wurde; genau die umgekehrte Verwechslung wie beim kommentarlosen
  Draft, und sie fällt leichter, weil ein Kommentar nach Arbeit aussieht.
- **Von der Environment-Meldung nicht auf eine fehlende Environment
  schliessen.** Der 23.8. in `swiss-public-data-mcp` bleibt ein Fall, in dem
  beides zusammenfiel; er belegt nicht, dass der Text seine Ursache nennt.
  Belegt ist jetzt das Gegenteil: derselbe Text, wo die Environment
  nachweislich arbeitet.

Was die Meldung *stattdessen* anzeigt, ist offen. Die naheliegende Vermutung —
Codex lehnt den Draft ab und greift dafür zur falschen Vorlage — verträgt sich
schlecht mit den beiden Gegenproben: #81 und #82 waren ebenfalls Drafts und
bekamen nichts. Eine vorübergehende Störung passt besser, ist aber ebenso
wenig gemessen. Gemessen ist allein, dass der Wortlaut hier nicht zutraf.

Das ist dieselbe Figur wie beim 403 weiter oben, zum dritten Mal in dieser
Datei: eine Störung, die als Auskunft über die Quelle daherkommt. Dort war eine
Sperre als Fund-Fehlschlag verpackt, hier ist eine Absage als
Konfigurationsmangel verpackt. Wer dem Wortlaut folgt, legt eine Environment an,
die es längst gibt — und hält das Problem danach für gelöst. Der Handgriff ist
derselbe wie überall in diesem Abschnitt: **erst die Positivkontrolle, dann die
Einordnung.** Sie kostete hier einen einzigen Klick auf «ready».

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
