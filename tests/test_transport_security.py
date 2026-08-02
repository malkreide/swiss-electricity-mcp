"""Inbound Host/Origin check for the HTTP transport (SEC-005, inbound half).

The trigger was not a missing guard but an over-strict one aimed at the wrong
address. mcp 2.x auto-enables an allow-list of ``127.0.0.1:*`` when the app's
``host`` argument looks like loopback, and ``streamable_http_app()`` defaults
that argument to ``127.0.0.1``. This server documents
``SWISS_ELECTRICITY_HOST=0.0.0.0`` for containers, so every request under a real
hostname was answered with HTTP 421 while ``/healthz`` stayed 200 and hid it.

These tests pin both halves: a real bind is reachable again, and an allow-list,
once configured, is port-exact.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from swiss_electricity_mcp.__main__ import build_http_app, build_transport_security
from swiss_electricity_mcp.config import get_settings

_INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"},
    },
}
_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """`get_settings` is lru_cached, so env changes need the cache dropped."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_loopback_bind_is_protected():
    sec = build_transport_security("127.0.0.1", 8000)
    assert sec is not None
    assert sec.enable_dns_rebinding_protection is True
    assert "127.0.0.1:8000" in sec.allowed_hosts


def test_wildcard_bind_without_allowlist_stays_off():
    """The actual fix.

    On 0.0.0.0 the reachable name is unknown here, and the SDK's loopback
    default is precisely a guess — it reproduces the 421. So protection stays
    off and the caller warns.
    """
    assert build_transport_security("0.0.0.0", 8000) is None


def test_wildcard_bind_with_allowlist_is_protected(monkeypatch):
    monkeypatch.setenv("SWISS_ELECTRICITY_ALLOWED_HOSTS", "power.example.ch")
    get_settings.cache_clear()
    sec = build_transport_security("0.0.0.0", 8000)
    assert sec is not None
    assert "power.example.ch" in sec.allowed_hosts
    # Loopback stays in, or container health checks break.
    assert "127.0.0.1:8000" in sec.allowed_hosts


def test_cors_origins_pass_the_transport_check(monkeypatch):
    """Otherwise the transport rejects exactly the browser clients CORS allows."""
    monkeypatch.setenv("SWISS_ELECTRICITY_CORS_ORIGINS", "https://claude.ai")
    get_settings.cache_clear()
    sec = build_transport_security("127.0.0.1", 8000)
    assert "https://claude.ai" in sec.allowed_origins


def test_wildcard_cors_is_not_copied(monkeypatch):
    monkeypatch.setenv("SWISS_ELECTRICITY_CORS_ORIGINS", "*")
    get_settings.cache_clear()
    sec = build_transport_security("127.0.0.1", 8000)
    assert "*" not in sec.allowed_origins


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_all_loopback_forms_count_as_local(host):
    assert build_transport_security(host, 8000) is not None


def _post(app, host_header: str) -> int:
    with TestClient(app) as client:
        return client.post(
            "/mcp", headers={"Host": host_header, **_HEADERS}, json=_INIT
        ).status_code


def test_a_public_bind_is_reachable_again():
    """The regression itself, through the real ASGI stack.

    Without the `host` kwarg this is a 421 — the state this commit repairs.
    """
    assert _post(build_http_app([], host="0.0.0.0", port=8000), "power.example.ch") == 200


def test_configured_host_is_served(monkeypatch):
    monkeypatch.setenv("SWISS_ELECTRICITY_ALLOWED_HOSTS", "power.example.ch")
    get_settings.cache_clear()
    assert _post(build_http_app([], host="0.0.0.0", port=8000), "power.example.ch") == 200


def test_foreign_host_is_rejected(monkeypatch):
    monkeypatch.setenv("SWISS_ELECTRICITY_ALLOWED_HOSTS", "power.example.ch")
    get_settings.cache_clear()
    assert _post(build_http_app([], host="0.0.0.0", port=8000), "evil.example.com") == 421


def test_right_host_wrong_port_is_rejected(monkeypatch):
    """The load-bearing case.

    ``evil.example.com`` alone proves little: a fallback loopback policy would
    reject it too. Only "right hostname, wrong port" separates a port-exact
    allow-list from one that permits anything — and it fails the moment
    ``transport_security`` stops being passed.
    """
    monkeypatch.setenv("SWISS_ELECTRICITY_ALLOWED_HOSTS", "power.example.ch:8000")
    get_settings.cache_clear()
    assert _post(build_http_app([], host="0.0.0.0", port=8000), "power.example.ch:9999") == 421


def test_allowed_hosts_is_read_as_csv(monkeypatch):
    monkeypatch.setenv("SWISS_ELECTRICITY_ALLOWED_HOSTS", "a.example.ch, b.example.ch")
    get_settings.cache_clear()
    assert get_settings().allowed_hosts == ["a.example.ch", "b.example.ch"]


def test_cors_origins_is_read_as_csv(monkeypatch):
    """Pre-existing bug, exposed by adding a second list-typed setting.

    The module docstring documents ``SWISS_ELECTRICITY_CORS_ORIGINS`` as
    comma-separated, but pydantic-settings JSON-decodes complex-typed fields
    from the environment *before* a ``mode="before"`` validator runs. Without
    ``NoDecode`` this raised ``SettingsError``, so the documented form never
    worked and ``_split_csv`` was unreachable for env input.
    """
    monkeypatch.setenv("SWISS_ELECTRICITY_CORS_ORIGINS", "https://a.test, https://b.test")
    get_settings.cache_clear()
    assert get_settings().cors_origins == ["https://a.test", "https://b.test"]
