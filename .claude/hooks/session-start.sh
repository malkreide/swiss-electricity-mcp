#!/bin/bash
# SessionStart: meldet, wie viele Commits der Klon hinter dem Default-Branch liegt.
#
# Oberste Regel: Dieser Hook blockiert die Session NIE. Kein Netz, kein Remote,
# detached HEAD, flatterndes DNS, fehlendes git — jeder dieser Faelle endet
# still mit Exit 0. Ein Hook, der bei Netzproblemen die Arbeit anhaelt, wird
# nach dem zweiten Mal abgeschaltet und schuetzt danach gar nichts.
#
# Grund fuer die Pruefung: siehe .claude/hooks/README.md
#
# Bewusst KEIN `set -e`: ein fehlschlagendes Kommando darf hier nicht abbrechen,
# sondern muss in den stillen Pfad laufen.
set -u

# Auch ein Signal (z. B. Timeout von aussen) endet als Erfolg.
# Kein ERR-Trap: fehlschlagende Kommandos sind hier erwartete Zwischenstaende
# (etwa ein nicht gesetztes origin/HEAD, das den Fallback ausloesen soll).
trap 'exit 0' TERM INT HUP

FETCH_TIMEOUT=5   # Sekunden bis das Netz-Kommando abgeschnitten wird
LSREMOTE_TIMEOUT=4

# Niemals nach Zugangsdaten fragen — ein Prompt waere ein Haenger.
export GIT_TERMINAL_PROMPT=0
export GIT_ASKPASS=true
export SSH_ASKPASS=true
export SSH_ASKPASS_REQUIRE=never
export GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -oBatchMode=yes -oStrictHostKeyChecking=accept-new}"

# Netz-Kommandos nur mit harter Zeitschranke. Fehlt `timeout`, wird gar nicht
# erst ins Netz gegangen — lieber keine Meldung als eine haengende Session.
if command -v timeout >/dev/null 2>&1; then
  net() { timeout -k 2 "$1" "${@:2}"; }
else
  net() { return 1; }
fi

command -v git >/dev/null 2>&1 || exit 0

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
git rev-parse --verify --quiet HEAD >/dev/null 2>&1 || exit 0   # frisches Repo ohne Commit
git remote get-url origin >/dev/null 2>&1 || exit 0             # kein Remote

# Default-Branch ermitteln, nicht "main" annehmen: mindestens ein Repo im
# Portfolio nutzt "master", und genau diese Annahme hat schon einmal einen
# Branch 15 Commits alt werden lassen.
# Erst der lokal von `git clone` gesetzte origin/HEAD (kostenlos), sonst das
# Remote fragen. Bleibt beides leer, wird geschwiegen statt geraten.
branch=$(git symbolic-ref --short --quiet refs/remotes/origin/HEAD 2>/dev/null)
branch=${branch#origin/}
if [ -z "$branch" ]; then
  branch=$(net "$LSREMOTE_TIMEOUT" git ls-remote --symref origin HEAD 2>/dev/null |
    sed -n 's|^ref: refs/heads/\([^[:space:]]*\).*|\1|p')
fi
[ -n "$branch" ] || exit 0

net "$FETCH_TIMEOUT" git fetch --quiet origin "$branch" >/dev/null 2>&1 || exit 0

behind=$(git rev-list --count HEAD..FETCH_HEAD 2>/dev/null) || exit 0
case "$behind" in
  ''|*[!0-9]*) exit 0 ;;   # unerwartete Ausgabe: schweigen
  0) exit 0 ;;             # aktuell: schweigen
esac

if [ "$behind" -eq 1 ]; then commits="Commit"; else commits="Commits"; fi
printf 'Klon-Aktualitaet: Der ausgecheckte Stand liegt %s %s hinter origin/%s.\n' \
  "$behind" "$commits" "$branch"
printf 'Vor der Arbeit aktualisieren (z. B. `git merge FETCH_HEAD`) — sonst kann eine\n'
printf 'rote CI entstehen, deren Ursache nicht im Diff steht: es fehlen dann genau die\n'
printf 'Commits, die das Gate eingefuehrt haben, an dem der Branch scheitert.\n'

exit 0
