"""Der Live-Lauf prueft auch das veroeffentlichte Paket, nicht nur `main`.

Anlass: 0.2.5 lieferte rund sieben Wochen lang fuer alle drei Tarif-Werkzeuge
leere Antworten, waehrend `.github/workflows/live-tests.yml` jeden Montag gruen
war. Der Lauf installierte mit `pip install -e` den Quellcode von `main`, und
dort lag der Fix seit 2026-08-07. Geprueft wurde, was niemand installiert.

Seither hat der Lauf zwei Ziele (`main` und `pypi`). Gemessen am 2026-09-27 mit
den `run:`-Bloecken dieses Workflows: die Suite des Tags v0.2.5 gegen das
PyPI-Paket 0.2.5 faellt an `test_elcom_zurich_tariffs_live` (Einordnung
`finding`), dieselbe Suite fuer 0.3.0 ist gruen (`clear`).

Diese Tests halten fest, was den `pypi`-Zweig zu einer Messung des Artefakts
macht und nicht zu einer zweiten Messung von `main`:

  - installiert wird von PyPI, ohne `-e` und ohne festgenagelte Version;
  - die Suite kommt vom Tag der installierten Version, nicht von `main`;
  - `src/` ist vor dem Lauf entfernt, und der Import ist belegt, nicht
    angenommen;
  - jedes Ziel fuehrt sein eigenes Issue — ein gruener `main` schliesst das
    Issue zum Paket nicht.

Als Text gelesen wie die anderen Workflow-Tests (kein PyYAML im dev-Extra).
"""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "live-tests.yml"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _ohne_kommentare(block: str) -> str:
    return "\n".join(z for z in block.splitlines() if not z.lstrip().startswith("#"))


def _steps() -> list[str]:
    teil = _text().split("\n    steps:\n", 1)[1]
    return [_ohne_kommentare(s) for s in re.split(r"^      - ", teil, flags=re.M)[1:]]


def _step(name: str) -> tuple[int, str]:
    treffer = [(i, s) for i, s in enumerate(_steps()) if f"name: {name}" in s]
    assert len(treffer) == 1, f"Schritt «{name}» nicht genau einmal gefunden"
    return treffer[0]


def _matrix() -> list[dict[str, str]]:
    block = _text().split("        include:\n", 1)[1].split("\n    steps:", 1)[0]
    eintraege = re.split(r"^          - ", block, flags=re.M)[1:]
    return [dict(re.findall(r"(\w+): \"?([^\"\n]+)\"?", e)) for e in eintraege]


# --- Matrix -------------------------------------------------------------------


def test_zwei_ziele_mit_eigenem_issue():
    ziele = {m["target"]: m for m in _matrix()}
    assert set(ziele) == {"main", "pypi"}
    assert ziele["main"]["prefix"] != ziele["pypi"]["prefix"]
    assert ziele["pypi"]["suite_dir"] == "released"


def test_ein_ziel_bricht_das_andere_nicht_ab():
    assert re.search(r"^      fail-fast: false$", _text(), re.M)


# --- pypi-Zweig ---------------------------------------------------------------


def test_pypi_installiert_das_neueste_paket_ohne_quellcode():
    _, s = _step("Veroeffentlichtes Paket installieren (pypi)")
    assert "if: matrix.target == 'pypi'" in s
    assert 'pip install --no-cache-dir "swiss-electricity-mcp[dev]"' in s
    assert " -e " not in s, "editable waere wieder der Quellcode"
    assert "swiss-electricity-mcp[dev]==" not in s, (
        "festgenagelt waere nicht das, was Nutzer bekommen"
    )
    assert "id: pkg" in s


def test_pypi_nimmt_die_suite_des_release_tags():
    _, s = _step("Suite des Release-Tags holen (pypi)")
    assert "if: matrix.target == 'pypi'" in s
    assert "ref: v${{ steps.pkg.outputs.version }}" in s
    assert "path: released" in s


def test_pypi_entfernt_src_und_belegt_den_import():
    _, s = _step("Quellcode entfernen, Import pruefen (pypi)")
    assert "if: matrix.target == 'pypi'" in s
    assert "working-directory: released" in s
    entfernen = s.find("rm -rf src")
    beleg = s.find('assert "site-packages" in m.__file__')
    assert entfernen != -1 and beleg != -1
    assert entfernen < beleg
    assert 'md.version("swiss-electricity-mcp") == os.environ["PKG_VERSION"]' in s


def test_reihenfolge_installieren_holen_pruefen_laufen():
    reihe = [
        _step("Veroeffentlichtes Paket installieren (pypi)")[0],
        _step("Suite des Release-Tags holen (pypi)")[0],
        _step("Quellcode entfernen, Import pruefen (pypi)")[0],
        _step("Live-Suite")[0],
    ]
    assert reihe == sorted(reihe), reihe


def test_suite_laeuft_im_verzeichnis_des_ziels():
    _, s = _step("Live-Suite")
    assert "working-directory: ${{ matrix.suite_dir }}" in s
    assert '--junitxml="$OUT/live-report.xml"' in s


# --- main-Zweig ---------------------------------------------------------------


def test_editable_install_nur_fuer_main():
    _, s = _step("Install dependencies (main, aus dem Quellcode)")
    assert "if: matrix.target == 'main'" in s
    assert 'pip install -e ".[dev]"' in s
    editable = [x for x in _steps() if "pip install -e" in x]
    assert len(editable) == 1, "ein zweites -e wuerde auch den pypi-Zweig treffen"


# --- Issues -------------------------------------------------------------------


def test_issue_praefix_kommt_aus_der_matrix():
    text = _text()
    assert "LIVE_PREFIX: ${{ matrix.prefix }}" in text
    assert "const PREFIX = process.env.LIVE_PREFIX;" in text
    assert not re.search(r"const PREFIX = '", text), (
        "festes Praefix teilte ein Issue fuer beide Ziele"
    )
