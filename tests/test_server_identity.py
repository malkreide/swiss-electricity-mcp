"""Die Identitaet, die dieser Server ueber sich selbst aussagt.

Bis Spec `2025-11-25` stand `serverInfo` genau einmal pro Verbindung auf der
Leitung, in der Antwort auf `initialize`. Spec `2026-07-28` stempelt es in das
`_meta` JEDER Antwort — die Identitaet ist damit keine Handshake-Fussnote mehr,
sondern Teil des laufenden Verkehrs.

`MCPServer` fuellt nichts davon selbst aus. Ohne `version=` meldete dieser
Server `"version": ""` an jeden Aufrufer, auf beiden Aeren und beiden
Transporten, und das SDK setzt bewusst nicht seine eigene Version an die Stelle
(`Server.server_info`: «An unversioned server reports an empty version; the SDK
never substitutes its own»). Der Fehlbefund war deshalb nicht rot, sondern
leer — genau die Sorte, die niemandem auffaellt.

Gemessen an der Antwort, nicht am Konstruktor-Argument: ein Blick auf
`mcp.version` waere auch dann gruen, wenn das Feld auf dem Weg zur Drahtform
verlorenginge.

Ein Feld pro Test und beide Aeren getrennt. Ein Test, der `version`, `title`
und `websiteUrl` zusammen prueft, faellt bei allen drei Fehlern gleich — und
sagt dann beim Lesen des Protokolls nicht mehr, welcher es war.
"""

from __future__ import annotations

import json
import pathlib
import tomllib
from collections.abc import Awaitable, Callable

import httpx
import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer

from swiss_electricity_mcp import HOMEPAGE, __version__
from swiss_electricity_mcp.__main__ import build_http_app
from swiss_electricity_mcp.api_client import DEFAULT_USER_AGENT
from swiss_electricity_mcp.server import mcp

REPO = pathlib.Path(__file__).resolve().parents[1]

SERVER_INFO_META_KEY = "io.modelcontextprotocol/serverInfo"

_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "Host": "127.0.0.1:8000",
}


async def _modern_server_info() -> dict:
    """Der Stempel im `_meta` einer gewoehnlichen Antwort der modernen Aera.

    Bewusst `tools/list` und nicht `server/discover`: der lasttragende Punkt
    von Spec 2026-07-28 ist, dass die Identitaet auf JEDER Antwort steht, nicht
    nur auf der einen, die nach ihr fragt.
    """
    async with Client(mcp) as client:
        result = await client.list_tools()
    return (result.meta or {}).get(SERVER_INFO_META_KEY) or {}


async def _handshake_server_info() -> dict:
    """Das `serverInfo` aus einem echten `initialize` durch den ASGI-Stack."""
    app = build_http_app(None, "127.0.0.1", 8000)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1:8000"
        ) as client:
            response = await client.post(
                "/mcp",
                headers=_HEADERS,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "legacy-client", "version": "1"},
                    },
                },
            )
    body = response.text
    for line in body.splitlines():  # SSE-Rahmen abstreifen, falls vorhanden
        if line.startswith("data: "):
            body = line[len("data: ") :]
    return json.loads(body)["result"]["serverInfo"]


# Zwei Aeren, ein Server: eine Identitaet, die nur in einer der beiden stimmt,
# ist kein Fortschritt, sondern eine neue Drift-Stelle. Jede Zusicherung faehrt
# deshalb beide.
ERAS: dict[str, Callable[[], Awaitable[dict]]] = {
    "handshake/initialize": _handshake_server_info,
    "modern/_meta-stempel": _modern_server_info,
}

_ERA_IDS = sorted(ERAS)


async def test_die_moderne_aera_stempelt_ueberhaupt_eine_identitaet() -> None:
    """Die Voraussetzung der Feldtests unten: der Stempel ist da.

    Ohne diesen Fall waere ein fehlender `_meta`-Block von einem leeren Feld
    nicht zu unterscheiden — `_modern_server_info` gibt in beiden Faellen ein
    Dict ohne den Schluessel zurueck.
    """
    async with Client(mcp) as client:
        result = await client.list_tools()

    assert (result.meta or {}).get(SERVER_INFO_META_KEY), (
        f"tools/list trug keinen {SERVER_INFO_META_KEY}-Stempel — die moderne "
        "Aera antwortet hier nicht mehr nach Spec 2026-07-28"
    )


@pytest.mark.parametrize("era", _ERA_IDS)
async def test_jede_aera_meldet_die_version(era: str) -> None:
    """Der lasttragende Fall: ohne `MCPServer(version=...)` steht hier ein
    leerer String, auf jeder einzelnen Antwort der modernen Aera."""
    info = await ERAS[era]()

    assert info.get("version"), f"{era} meldet eine leere Version"
    assert info["version"] == __version__


@pytest.mark.parametrize("era", _ERA_IDS)
async def test_jede_aera_meldet_die_projektadresse(era: str) -> None:
    info = await ERAS[era]()

    assert info.get("websiteUrl") == HOMEPAGE, f"{era} meldet {info.get('websiteUrl')!r}"


@pytest.mark.parametrize("era", _ERA_IDS)
async def test_jede_aera_meldet_einen_titel(era: str) -> None:
    """Der Anzeigename aus `Implementation.title`. Nur auf Vorhandensein
    geprueft: welcher Text dort steht, ist eine Produktentscheidung und keine
    Eigenschaft, die ein Test festhalten sollte."""
    info = await ERAS[era]()

    assert info.get("title"), f"{era} meldet keinen Titel"


@pytest.mark.parametrize("era", _ERA_IDS)
async def test_jede_aera_meldet_den_namen(era: str) -> None:
    """Der Name, unter dem der Server in der Registry steht. Ohne ihn waeren
    die Tests oben auch gegen eine Identitaet gruen, die zu einem anderen
    Server gehoert."""
    info = await ERAS[era]()

    assert info.get("name") == "swiss-electricity-mcp"


async def test_ein_server_ohne_identitaet_meldet_eine_leere_version() -> None:
    """Negativkontrolle: gleiches SDK, gleicher Client, kein `version=`.

    Ohne sie lesen sich die Zusicherungen oben wie eine Eigenschaft des SDK.
    Sie sind es nicht — und faellt dieser Test eines Tages, weil das SDK doch
    einen Default einsetzt, pruefen die anderen nicht mehr, dass WIR die
    Identitaet setzen.
    """
    async with Client(MCPServer("kontrolle")) as client:
        result = await client.list_tools()

    stamped = (result.meta or {}).get(SERVER_INFO_META_KEY)
    assert stamped is not None
    assert stamped["version"] == ""
    assert "websiteUrl" not in stamped
    assert "title" not in stamped


def test_die_projektadresse_steht_nur_einmal() -> None:
    """`HOMEPAGE` gegen die Paketmetadaten, aus denen PyPI sie ausliest.

    Die Adresse geht an zwei Orte, die nichts voneinander wissen: den
    User-Agent gegenueber den Datenquellen und `serverInfo.websiteUrl`. Vor
    dieser Konstante war sie an beiden Stellen ein eigenes Literal — zwei
    Wahrheiten, die auseinanderlaufen koennen, ohne dass eine von beiden
    unplausibel aussieht.
    """
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert HOMEPAGE == pyproject["project"]["urls"]["Repository"]
    assert HOMEPAGE in DEFAULT_USER_AGENT


def test_die_version_kommt_aus_den_paketmetadaten() -> None:
    """Sagt, woran ein gemeldeter Wert haengt.

    In der CI ist das Paket installiert, `__version__` ist dann die Zahl aus
    `pyproject.toml`. In einem blossen Checkout ohne Install ist es der
    Quellcode-Marker. Beides ist richtig; ein drittes Ergebnis — etwa ein
    handgepflegtes Literal, das an `pyproject.toml` vorbeilaeuft — nicht.
    """
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert __version__ in (pyproject["project"]["version"], "0.0.0+source")
