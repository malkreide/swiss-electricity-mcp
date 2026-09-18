"""swiss-electricity-mcp — MCP server for Swiss electricity data.

Part of the Swiss Public Data MCP Portfolio.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _distribution_version

# Die eine Stelle, an der die Projektadresse steht. Sie geht an zwei Orte, die
# unterschiedlich aussehen und dasselbe meinen: in den User-Agent gegenueber den
# Datenquellen und — seit Spec 2026-07-28 — in `serverInfo.websiteUrl`, das der
# Server in das `_meta` JEDER Antwort stempelt. Zwei Literale waeren zwei
# Wahrheiten; auseinandergelaufen faellt es an keiner Stelle auf, weil beide
# fuer sich plausibel bleiben.
HOMEPAGE = "https://github.com/malkreide/swiss-electricity-mcp"

try:
    # Read the version from the installed distribution metadata, which is built
    # from pyproject.toml. Hand-maintaining the literal here let the numbers
    # drift apart: pyproject said 0.2.3, this said 0.2.0. A value nobody
    # has to remember to bump cannot go stale.
    __version__ = _distribution_version("swiss-electricity-mcp")
except PackageNotFoundError:
    # Running from the source tree without an install (e.g. a bare checkout).
    # Deliberately not a plausible-looking number: an obviously non-release
    # marker is better than a wrong version in the User-Agent.
    __version__ = "0.0.0+source"
