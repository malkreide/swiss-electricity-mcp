"""Entrypoint for swiss-electricity-mcp.

Transport selected via SWISS_ELECTRICITY_TRANSPORT env var:
- stdio (default): for Claude Desktop and local IDE clients
- streamable-http: for cloud / remote deployments (Render, Railway, etc.)

The HTTP host defaults to 127.0.0.1 (loopback only). Bind to all interfaces
explicitly via SWISS_ELECTRICITY_HOST=0.0.0.0 inside a container only — never
as the implicit default (NeighborJack / SEC-016).

For browser-based clients, allowed CORS origins are configured via
SWISS_ELECTRICITY_CORS_ORIGINS (comma-separated). The default is empty
(same-origin only) — never a wildcard (SDK-004).

All configuration is read through the Settings object in config.py (ARCH-004).
"""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware

from .config import get_settings
from .server import mcp


def build_transport_security(host: str, port: int):
    """Host/Origin allow-list for the HTTP transport (SEC-005, inbound half).

    Under mcp 2.x this is a per-app kwarg, and *not* passing it is not neutral:
    the SDK derives a default from the app's `host` argument and auto-enables
    `127.0.0.1:*` whenever that looks like loopback. Since `host` itself
    defaults to `127.0.0.1`, a server binding `SWISS_ELECTRICITY_HOST=0.0.0.0`
    answered every request under a real hostname with HTTP 421.

    Returns `None` when no allow-list can be derived — a non-loopback bind with
    no `SWISS_ELECTRICITY_ALLOWED_HOSTS`. A guessed list would reproduce exactly
    that 421, so the caller warns instead and the SDK's behaviour for a
    non-loopback bind is left unchanged.
    """
    from mcp.server.transport_security import TransportSecuritySettings

    settings = get_settings()
    loopback = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
    if settings.allowed_hosts:
        # Loopback stays reachable for container health checks and debugging.
        hosts = set(settings.allowed_hosts) | loopback
    elif host in ("127.0.0.1", "localhost", "::1"):
        hosts = loopback | {f"{host}:{port}"}
    else:
        return None

    # Configured CORS origins must also pass the transport check, or the server
    # rejects exactly the browser clients CORS permits — a failure that only
    # surfaces in a browser. "*" cannot be expressed here (origins are compared
    # literally), so it is not copied across.
    origins = {o for o in settings.cors_origins if o != "*"}
    origins |= {f"http://{h}" for h in hosts}
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=sorted(hosts),
        allowed_origins=sorted(origins),
    )


# Die Header, nach denen Spec 2026-07-28 eine Streamable-HTTP-Anfrage routet —
# in der Schreibweise des SDK (`mcp.shared.inbound`). Ein Browser darf einen
# nicht safelisteten Header gar nicht erst senden, wenn der Server ihn nicht in
# `Access-Control-Allow-Headers` nennt: ohne sie stirbt jede Cross-Origin-
# Anfrage am Preflight, vor dem ersten MCP-Byte. stdio- und Python-Clients
# kennen keinen Preflight und merken davon nichts — deshalb fiel es nicht auf.
#
# `Mcp-Param-*` fehlt bewusst: CORS kennt keinen Praefix-Wildcard, und kein
# Tool-Schema dieses Servers traegt eine `x-mcp-header`-Annotation.
CORS_ROUTING_HEADERS = ["Mcp-Method", "Mcp-Name", "Mcp-Protocol-Version"]


def build_http_app(
    origins: list[str] | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> Starlette:
    """Build the Streamable-HTTP app with CORS that exposes Mcp-Session-Id.

    `expose_headers` must include `Mcp-Session-Id` so browser clients can read
    the session id from the response; `allow_headers` must include it so they
    can send it back on follow-up requests (SDK-004).

    `host` must be the address uvicorn actually binds — see
    :func:`build_transport_security` for why leaving it at the default breaks a
    container deployment.
    """
    import logging

    if origins is None:
        origins = get_settings().cors_origins
    security = build_transport_security(host, port)
    if security is None:
        logging.getLogger("swiss_electricity_mcp").warning(
            "DNS rebinding protection is OFF: the bind %s is not loopback and "
            "SWISS_ELECTRICITY_ALLOWED_HOSTS is empty. Set it to the hostnames "
            "this server is reachable under so Host and Origin are validated.",
            host,
        )
    app = mcp.streamable_http_app(transport_security=security, host=host)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,  # explicit list, never "*"
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Mcp-Session-Id", "Content-Type", *CORS_ROUTING_HEADERS],
        expose_headers=["Mcp-Session-Id"],
        allow_credentials=bool(origins),
    )
    return app


def main() -> None:
    settings = get_settings()
    if settings.transport.lower() in {"http", "streamable-http", "sse"}:
        import uvicorn

        # The bind goes to uvicorn *and* into the app. Under mcp 2.x it is no
        # longer redundant there: the SDK derives its Host allow-list from the
        # app's `host` argument, so omitting it made a 0.0.0.0 deployment reject
        # every real request with HTTP 421.
        uvicorn.run(
            build_http_app(host=settings.host, port=settings.port),
            host=settings.host,
            port=settings.port,
        )
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
