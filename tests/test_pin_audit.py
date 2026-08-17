#!/usr/bin/env python3
"""Tests fuer scripts/pin_audit.py.

Das Werkzeug misst andere Repos. Faellt seine Erkennung oder sein Urteil still
falsch aus, meldet es «alles in Ordnung» ueber Server, die es nie richtig
angesehen hat — und das ist schlimmer als kein Werkzeug, weil danach niemand
mehr nachsieht.

Beide Fehler unten sind nicht ausgedacht: Sie sind mir bei der ersten Erhebung
genau so unterlaufen.

  - Die Erkennung suchte in `scripts/` nur nach dem Aufruf aus einem Workflow
    und nur in `tests/` nach Inhalten. `meteoswiss-mcp/scripts/check_ruff_pin.py`
    fiel dadurch durch jedes Netz — sie liest die pre-commit-Datei, wird aber
    nicht aus einem Workflow gestartet, sondern IST ein pre-commit-Hook.
  - Das Urteil pruefte `if kontrolle == 0`. Fehlt die Kontrollvariante, ist der
    Wert `None`, der Vergleich falsch, und der Fall fiel in den Korrekt-Zweig.
    Ein Repo ganz ohne `rev` stand daraufhin als «ordnet richtig zu» da.

Nur Standardbibliothek, kein Netz, keine fremden Repos.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pin_audit as pa  # noqa: E402


class ErkennungTest(unittest.TestCase):
    """Welche Dateien gelten als Waechter?"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def lege_an(self, rel: str, inhalt: str) -> None:
        pfad = self.root / rel
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_text(inhalt, encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", rel], check=True)

    def test_skript_das_die_datei_liest_zaehlt_mit(self):
        """Der Fall meteoswiss: ein Waechter, den kein Workflow startet.

        Die erste Fassung fand Skripte nur ueber ihren Aufruf in einem Workflow.
        Dieses Skript wird als pre-commit-Hook gestartet und war damit unsichtbar
        — obwohl es genau die Datei liest, um die es geht.
        """
        self.lege_an("scripts/check_ruff_pin.py", 'P = ROOT / ".pre-commit-config.yaml"\n')
        self.assertEqual(pa.waechter_dateien(self.root), ["scripts/check_ruff_pin.py"])

    def test_test_das_die_datei_liest_zaehlt_mit(self):
        self.lege_an("tests/test_werkzeug.py", 'assert "rev:" not in text\n')
        self.assertEqual(pa.waechter_dateien(self.root), ["tests/test_werkzeug.py"])

    def test_laufzeitcode_zaehlt_nicht(self):
        """`src/` ist kein Gate — dort steht der Server, nicht seine Bewachung."""
        self.lege_an("src/paket/server.py", "# siehe .pre-commit-config.yaml\n")
        self.assertEqual(pa.waechter_dateien(self.root), [])

    def test_datei_ohne_bezug_zaehlt_nicht(self):
        self.lege_an("scripts/record_fixtures.py", "import httpx\n")
        self.assertEqual(pa.waechter_dateien(self.root), [])

    def test_unversionierte_datei_zaehlt_nicht(self):
        """Ein Streuner aus einem Arbeitsverzeichnis ist kein Waechter des Repos."""
        pfad = self.root / "scripts" / "kladde.py"
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_text('open(".pre-commit-config.yaml")\n', encoding="utf-8")
        self.assertEqual(pa.waechter_dateien(self.root), [])


class UrteilTest(unittest.TestCase):
    """Aus den Exit-Codes das Urteil — die Stelle, an der ich mich vertan habe."""

    def test_fehlende_kontrolle_ist_nicht_bestanden(self):
        """Der eigentliche Fehler.

        Ohne Kontrollvariante ist ueber die Zuordnung nichts bekannt. `None == 0`
        ist falsch, der Fall fiel deshalb durch bis in den Korrekt-Zweig — und
        ein Repo ohne jede `rev` galt als «ordnet richtig zu».
        """
        rc = {"unveraendert": 0, "sauber": 0, "fremder_hook": 0}
        self.assertEqual(pa.klassifiziere(rc), pa.OHNE_REV)

    def test_gruene_kontrolle_heisst_blind(self):
        rc = {"unveraendert": 0, "sauber": 0, "kontrolle": 0, "fremder_hook": 0}
        self.assertEqual(pa.klassifiziere(rc), pa.BLIND)

    def test_rote_kontrolle_und_gruener_fremder_hook_ist_korrekt(self):
        rc = {"unveraendert": 0, "sauber": 0, "kontrolle": 1, "fremder_hook": 0}
        self.assertEqual(pa.klassifiziere(rc), pa.KORREKT)

    def test_rote_kontrolle_und_roter_fremder_hook_ist_fehlalarm(self):
        rc = {"unveraendert": 0, "sauber": 0, "kontrolle": 1, "fremder_hook": 1}
        self.assertEqual(pa.klassifiziere(rc), pa.FEHLALARM)

    def test_schon_vorher_rot_ist_nicht_messbar(self):
        """Ein Waechter, der unveraendert rot ist, sagt ueber den Hook nichts.

        Genau dieser Fall trat auf, als ein aelteres `ruff` im PATH die gepinnte
        Version beschattete: sechs Waechter waren rot, und ohne diesen Zweig
        haette die Auswertung sie als Fehlalarm gezaehlt.
        """
        rc = {"unveraendert": 1, "sauber": 1, "kontrolle": 1, "fremder_hook": 1}
        self.assertEqual(pa.klassifiziere(rc), pa.VORBEDINGUNG)


class VariantenTest(unittest.TestCase):
    """Was dem Repo vorgelegt wird."""

    SAUBER = "repos:\n" + pa.RUFF_BLOCK.format(pin="0.16.1")

    def namen(self, original: str | None) -> list[str]:
        return [n for n, _ in pa.varianten("0.16.1", original, self.SAUBER)]

    def test_ohne_passende_rev_entfaellt_die_kontrolle(self):
        """`repo: local` bringt keine rev mit — dann gibt es nichts zu verstellen."""
        lokal = "repos:\n  - repo: local\n    hooks:\n      - id: ruff\n"
        self.assertNotIn("kontrolle", self.namen(lokal))

    def test_mit_rev_gibt_es_eine_kontrolle(self):
        self.assertIn("kontrolle", self.namen(self.SAUBER))

    def test_die_echte_datei_bleibt_erhalten(self):
        """Der fremde Hook wird davorgesetzt, nicht die Datei ersetzt.

        Sonst pruefte der Fall eine selbstgebaute Konfiguration statt der, die im
        Repo wirklich steht — und ein Fehler in der echten Datei bliebe unsichtbar.
        """
        eigen = self.SAUBER.replace("ruff-check", "ruff-check-eigen")
        _, inhalt = next(
            x for x in pa.varianten("0.16.1", eigen, self.SAUBER) if x[0] == "fremder_hook"
        )
        self.assertIn("ruff-check-eigen", inhalt)
        self.assertIn("end-of-file-fixer", inhalt)
        self.assertLess(inhalt.index("end-of-file-fixer"), inhalt.index("ruff-pre-commit"))

    def test_unveraendert_bildet_das_fehlen_der_datei_ab(self):
        """`None` heisst «Datei loeschen», nicht «leere Datei»."""
        varianten = dict(pa.varianten("0.16.1", None, self.SAUBER))
        self.assertIsNone(varianten["unveraendert"])


class SicherheitTest(unittest.TestCase):
    def test_dirty_repo_wird_uebersprungen(self):
        """Das Werkzeug verstellt fremde Dateien — ohne git kein Zurueck.

        Auf einem Arbeitsverzeichnis mit ungesicherten Aenderungen liesse sich
        nach einem Abbruch nicht mehr unterscheiden, was vorher da war.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "kladde.txt").write_text("offen\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "kladde.txt"], check=True)
            ergebnis = pa.messe(root, sys.executable, "pytest")
        self.assertIn("nicht sauber", ergebnis["fehler"])


if __name__ == "__main__":
    unittest.main()
