"""Lieferkette von .github/workflows/publish.yml.

Der Workflow haelt das OIDC-Token fuer PyPI und die MCP Registry. Was er
ausfuehrt, entscheidet also, wer im Namen dieses Servers publiziert. Drei
Zusicherungen, jede gegen einen Zustand, der bis 2026-09-27 bestand:

  - Jede Action auf einen Commit-SHA gepinnt. Vorher `@v7`, `@v8` und
    `pypa/gh-action-pypi-publish@release/v1` — ein Branch, der mit jedem Push
    wandert. Der Versionskommentar dahinter ist Pflicht: an ihm hebt Dependabot
    SHA und Version gemeinsam an, und ohne ihn liest niemand, was gepinnt ist.
  - `mcp-publisher` mit fester Version und fester Pruefsumme. Vorher
    `releases/latest` per `curl | tar`, ungeprueft.
  - `timeout-minutes` auf jedem Job. Vorher keiner; der GitHub-Standard ist
    sechs Stunden.

Als Text gelesen wie die anderen Workflow-Tests (kein PyYAML im dev-Extra).
Nur Standardbibliothek, kein Netz — ob ein SHA wirklich zum genannten Tag
gehoert, prueft dieser Test nicht; das steht im PR-Nachweis.
"""

from __future__ import annotations

import re
from pathlib import Path

PUBLISH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "publish.yml"

USES = re.compile(r"^\s*(?:-\s+)?uses:\s*(?P<ref>\S+)(?P<rest>.*)$", re.M)
SHA_PIN = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
VERSION_COMMENT = re.compile(r"^\s+#\s+v\d+\.\d+\.\d+\s*$")


def _text() -> str:
    return PUBLISH.read_text(encoding="utf-8")


def _code(text: str) -> str:
    """Ohne Kommentarzeilen: ein `uses:` im Kommentar ist kein Aufruf."""
    return "\n".join(z for z in text.splitlines() if not z.lstrip().startswith("#"))


def _jobs(text: str) -> dict[str, str]:
    teil = text.split("\njobs:\n", 1)[1]
    return {
        m.group(1): m.group(2)
        for m in re.finditer(r"^  ([\w-]+):\n(.*?)(?=^  [\w-]+:\n|\Z)", teil, re.M | re.S)
    }


def _install_step(text: str) -> str:
    m = re.search(r"- name: Install mcp-publisher\n(.*?)(?=\n      - |\Z)", text, re.S)
    assert m, "Schritt «Install mcp-publisher» fehlt"
    return m.group(1)


# --- Actions -------------------------------------------------------------------


def test_jede_action_ist_auf_einen_commit_gepinnt():
    aufrufe = list(USES.finditer(_code(_text())))
    assert len(aufrufe) >= 6, "Positivkontrolle: der Scan findet die Aufrufe nicht"
    ungepinnt = [m["ref"] for m in aufrufe if not SHA_PIN.match(m["ref"])]
    assert not ungepinnt, f"nicht auf einen Commit-SHA gepinnt: {ungepinnt}"


def test_jeder_pin_nennt_seine_version():
    ohne = [m["ref"] for m in USES.finditer(_code(_text())) if not VERSION_COMMENT.match(m["rest"])]
    assert not ohne, f"SHA ohne Versionskommentar (# vX.Y.Z): {ohne}"


def test_kein_branch_und_kein_bewegliches_ziel():
    code = _code(_text())
    for beweglich in ("@release/", "@main", "@master", "releases/latest"):
        assert beweglich not in code, beweglich


# --- mcp-publisher ------------------------------------------------------------


def test_mcp_publisher_hat_feste_version_und_pruefsumme():
    schritt = _install_step(_text())
    assert re.search(r'MCP_PUBLISHER_VERSION: "\d+\.\d+\.\d+"', schritt)
    assert re.search(r'MCP_PUBLISHER_SHA256: "[0-9a-f]{64}"', schritt)
    assert "releases/download/v${MCP_PUBLISHER_VERSION}/" in schritt


def test_pruefsumme_wird_vor_dem_entpacken_geprueft():
    run = _code(_install_step(_text()))
    assert "| tar" not in run, "kein curl | tar: das Archiv muss erst geprueft werden"
    pruefung = run.find("sha256sum -c")
    entpacken = run.find("tar xzf")
    assert pruefung != -1, "keine Pruefsummen-Kontrolle"
    assert entpacken != -1, "kein Entpacken gefunden"
    assert pruefung < entpacken


def test_mcp_publisher_laeuft_erst_nach_der_installation():
    text = _text()
    assert text.find("- name: Install mcp-publisher") < text.find("./mcp-publisher login")


# --- Timeouts -----------------------------------------------------------------


def test_jeder_job_hat_ein_timeout():
    jobs = _jobs(_text())
    assert set(jobs) == {"build", "publish", "publish-mcp"}, sorted(jobs)
    for name, body in jobs.items():
        m = re.search(r"^    timeout-minutes: (\d+)$", body, re.M)
        assert m, f"Job {name} ohne timeout-minutes"
        assert 1 <= int(m.group(1)) <= 30, (name, m.group(1))
