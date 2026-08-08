"""Zugriff auf die aufgezeichneten Fixtures.

Ein fehlender Name ist hier ein Fehler und keine leere Struktur. Ein Loader,
der bei einem Tippfehler `{}` zurueckgibt, erzeugt einen Test, der nichts mehr
prueft und trotzdem Erfolg meldet — die teuerste Sorte gruen.

Herkunft, Datum und Auswahlregel stehen in `fixtures/PROVENANCE.md`.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"


@cache
def payload(name: str) -> Any:
    path = FIXTURES / name
    if not path.exists():
        available = sorted(p.name for p in FIXTURES.glob("*.json"))
        raise FileNotFoundError(
            f"Fixture {name!r} gibt es nicht. Vorhanden: {available}. "
            "Neu aufzeichnen mit `python scripts/record_fixtures.py`."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def bindings(name: str) -> list[dict[str, Any]]:
    """Die SPARQL-Bindings einer aufgezeichneten LINDAS-Antwort."""
    return payload(name)["results"]["bindings"]
