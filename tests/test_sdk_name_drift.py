"""Drift-Wache: die Doku nennt die Server-Klasse, die der Code benutzt.

Anlass: Nach dem Wechsel auf `mcp[cli]>=2` (`MCPServer` statt `FastMCP`) stand
im Architektur-Diagramm von README.md noch «FastMCP server». Kein Gate sah es;
aufgefallen ist es beim Abgleich mit dem Notion-Eintrag, behoben in PR #84.
`test_protocol_version.py` bewacht nur den Protokoll-Abschnitt der READMEs.

Zwei Haelften, weil jede allein an einem Fall vorbeilaeuft:

  - Negativ: kein «FastMCP» in einer versionierten Datei ausser der History.
    Gescannt wird `git ls-files`, nicht eine Liste bekannter Doku-Dateien —
    eine neue Datei unter docs/ ist damit ohne Zutun erfasst.
  - Positiv: Die Klasse, die `server.mcp` zur Laufzeit tatsaechlich ist, steht
    im Architektur-Diagramm von README.md. Eine Sperrliste kennt nur den alten
    Namen; benennt das SDK `MCPServer` eines Tages um, bliebe sie gruen,
    waehrend das Diagramm wieder veraltet.

Nur Standardbibliothek plus das Paket selbst, kein Netz.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve().relative_to(REPO).as_posix()

ALTER_NAME = re.compile(rb"fastmcp", re.IGNORECASE)

# History, nicht Beschreibung des Ist-Zustands. Hier darf der alte Name stehen,
# und er muss es sogar: CHANGELOG und die datierten Audit-Berichte vom
# 2026-06-03 beschreiben den Server, wie er damals war.
HISTORIE = (
    "CHANGELOG.md",
    "audits/",
    SELF,  # nennt den Namen zwangslaeufig
)


def _versionierte_dateien() -> list[str]:
    """Alles, was git kennt. Scheitert laut statt still leer zu liefern."""
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO,
        capture_output=True,
        check=True,
    ).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def _ist_historie(pfad: str) -> bool:
    return any(pfad == h or (h.endswith("/") and pfad.startswith(h)) for h in HISTORIE)


def _treffer(inhalt: bytes) -> list[int]:
    """Zeilennummern (1-basiert) mit dem alten Namen."""
    return [i for i, zeile in enumerate(inhalt.splitlines(), 1) if ALTER_NAME.search(zeile)]


def _architektur_diagramm() -> str:
    """Der erste Codeblock im Abschnitt «## Architecture» von README.md."""
    text = (REPO / "README.md").read_text(encoding="utf-8")
    teile = text.split("\n## Architecture\n", 1)
    assert len(teile) == 2, "README.md hat keinen Abschnitt «## Architecture»"
    abschnitt = teile[1].split("\n## ", 1)[0]
    block = re.search(r"```[^\n]*\n(.*?)\n```", abschnitt, re.S)
    assert block, "Abschnitt «## Architecture» in README.md hat kein Diagramm"
    return block.group(1)


# --- Negativ -----------------------------------------------------------------


def test_kein_alter_sdk_name_ausserhalb_der_historie():
    funde = []
    for pfad in _versionierte_dateien():
        if _ist_historie(pfad):
            continue
        datei = REPO / pfad
        if not datei.is_file():  # geloescht, aber noch nicht committet
            continue
        funde += [f"{pfad}:{n}" for n in _treffer(datei.read_bytes())]
    assert not funde, (
        "«FastMCP» ausserhalb der History — der Server laeuft nicht mehr darauf "
        "(welche Klasse er ist, steht in src/swiss_electricity_mcp/server.py):\n  "
        + "\n  ".join(funde)
    )


def test_scan_sieht_die_dateien_auf_die_es_ankommt():
    """Positivkontrolle: ein leerer Scan waere ebenfalls gruen."""
    gescannt = {p for p in _versionierte_dateien() if not _ist_historie(p)}
    for pflicht in (
        "README.md",
        "README.de.md",
        "EXAMPLES.md",
        "CLAUDE.md",
        "src/swiss_electricity_mcp/server.py",
        "docs/roadmap.md",
    ):
        assert pflicht in gescannt, pflicht


def test_historie_ist_eng_gefasst():
    """Die Ausnahme darf nicht die Doku schlucken, die sie schuetzen soll."""
    for pfad in ("README.md", "docs/roadmap.md", "src/swiss_electricity_mcp/server.py"):
        assert not _ist_historie(pfad), pfad
    assert _ist_historie("audits/2026-06-03T175129-Z-swiss-electricity-mcp/audit-report.md")
    assert not _ist_historie("audits.md")


def test_muster_findet_die_formen_des_alten_namens():
    probe = b"ok\nFastMCP server\nfrom mcp.server.fastmcp import Context\nok\nFASTMCP\n"
    assert _treffer(probe) == [2, 3, 5]
    assert _treffer(b"MCPServer (mcp)\nmcp_server\n") == []


# --- Positiv -----------------------------------------------------------------


def test_diagramm_nennt_die_klasse_die_der_server_ist():
    from swiss_electricity_mcp import server

    klasse = type(server.mcp).__name__
    assert klasse in _architektur_diagramm(), (
        f"server.mcp ist ein {klasse}, das Architektur-Diagramm in README.md "
        "nennt diesen Namen nicht"
    )


def test_klasse_kommt_aus_dem_sdk_nicht_aus_einem_wrapper():
    """Sonst stuende im Diagramm ein Name, den im SDK niemand findet."""
    from swiss_electricity_mcp import server

    assert type(server.mcp).__module__.startswith("mcp."), type(server.mcp).__module__
