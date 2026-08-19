# SessionStart-Hook: Klon-Aktualität

`session-start.sh` meldet beim Sessionstart, wie viele Commits der ausgecheckte
Stand hinter `origin/<default-branch>` liegt.

## Warum

Ein veralteter Klon hat am 3.8.2026 zweimal eine rote CI erzeugt, deren Ursache
nicht im Diff stand — die fehlenden Commits waren jeweils genau die, die das
Gate einführten, an dem der Branch scheiterte. Die Prüfung kostet eine Sekunde
und ersetzt eine Fehlersuche in den falschen Dateien.

## Zusicherungen

Nach Wichtigkeit geordnet:

1. **Der Hook blockiert die Session nie.** Kein Netz, kein Remote, detached
   HEAD, flatterndes DNS, fehlendes `git`, fehlendes `timeout` — jeder dieser
   Fälle endet still mit Exit 0. Ein Hook, der bei Netzproblemen die Arbeit
   anhält, wird nach dem zweiten Mal abgeschaltet und schützt danach gar
   nichts. Deshalb steht dort bewusst kein `set -e` und kein `ERR`-Trap:
   fehlschlagende Kommandos sind erwartete Zwischenstände, keine Abbrüche.
   Zugangsdaten werden nie erfragt (`GIT_TERMINAL_PROMPT=0`, `ssh -oBatchMode=yes`),
   weil ein Passwort-Prompt exakt der Hänger wäre, den der Hook vermeiden soll.
2. **Kurzes Timeout.** Jedes Netz-Kommando läuft unter `timeout` (Fetch 5 s,
   `ls-remote` 4 s, je mit `-k 2`). Fehlt `timeout` im Bild, geht der Hook gar
   nicht erst ins Netz — lieber keine Meldung als eine hängende Session.
3. **Ausgabe nur bei fehlenden Commits.** Bei 0 schweigt er, ebenso bei jeder
   unerwarteten `rev-list`-Ausgabe.
4. **Der Default-Branch wird ermittelt, nicht als `main` angenommen.** Zuerst
   das lokal von `git clone` gesetzte `refs/remotes/origin/HEAD` (kostenlos),
   sonst `git ls-remote --symref origin HEAD`. Bleibt beides leer, schweigt der
   Hook, statt zu raten. Mindestens ein Repo im Portfolio nutzt `master`
   (`openlex-mcp`, `swiss-courts-mcp`, `swisstopo-mcp`), und genau die
   Annahme `main` hat schon einmal einen Branch 15 Commits alt werden lassen.

## Manuell prüfen

```bash
CLAUDE_PROJECT_DIR="$PWD" .claude/hooks/session-start.sh; echo "exit=$?"
```

Erwartet: auf aktuellem Stand keine Ausgabe, `exit=0`.
