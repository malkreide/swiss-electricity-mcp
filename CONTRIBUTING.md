# 🤝 Contributing to swiss-electricity-mcp

🌍 **Read this in your language:** [🇩🇪 Deutsch](CONTRIBUTING.de.md)

Part of the [Swiss Public Data MCP Portfolio](https://github.com/malkreide/swiss-public-data-mcp).
This portfolio follows shared conventions so that all servers compose cleanly into
multi-source AI agent workflows.

## Portfolio conventions

- **No-Auth-First**: Phase 1 servers use only unauthenticated public endpoints.
- **Live-probe before code**: every new endpoint is validated against the real
  upstream before being added to the client.
- **Envelope discipline**: every Pydantic response inherits from `ResponseEnvelope`
  with `source` + `provenance` + `retrieved_at` — accidental omission is impossible.
- **Retry-with-backoff**: 3 retries, 2/4/8 seconds, 5xx + 429 retried.
- **Dual transport**: stdio for Claude Desktop, Streamable HTTP for cloud.
- **Bilingual docs**: English `README.md` primary, German `README.de.md` mirror
  in Swiss spelling (no eszett).
- **CI**: ruff + pytest (excluding `@pytest.mark.live`) on push.
- **Release**: tagged release on GitHub triggers PyPI publish via OIDC.

## Setup

```bash
git clone https://github.com/malkreide/swiss-electricity-mcp.git
cd swiss-electricity-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Test

```bash
# Unit tests (mocked, fast)
PYTHONPATH=src pytest tests/ -m "not live" -v

# Live tests (hits real upstreams — only when needed)
PYTHONPATH=src pytest tests/ -m live -v
```

## Lint

Install the hooks once. They pin the same ruff version as CI, so a local run
and a CI run cannot disagree:

```bash
pre-commit install
```

To run the CI gates by hand instead, install the pinned version explicitly —
`pip install -e ".[dev]"` resolves `ruff>=0.4.0` to whatever is newest:

```bash
pip install ruff==0.16.1
ruff check src/ tests/ scripts/
ruff format --check src/ tests/ scripts/
```

## Adding a tool

1. Live-probe the endpoint (`curl`, check response shape, status, latency).
2. Add a Pydantic response model in `models.py` (inherit `ResponseEnvelope`).
3. Add the client method in `api_client.py` (use `_fetch_with_retry`).
4. Register the `@mcp.tool` in `server.py` with German docstring + English
   tool description.
5. Add a mocked happy-path test and at least one live test in
   `tests/test_server.py`.
6. Update `CHANGELOG.md`.

## Releasing

1. Bump `version` in `pyproject.toml` and `__init__.py`.
2. Update `CHANGELOG.md` with a new section.
3. Commit, push, create a GitHub Release with tag `v0.X.Y`.
4. GitHub Actions publishes to PyPI automatically.

## Code style

- Use Swiss German spelling conventions in user-facing strings (no eszett).
- Field descriptions in models: German first (since it's the source language
  of most datasets), English in tool descriptions for LLM clarity.

## The live suite: when it runs, and who sees a red result

**Cadence:** every Monday at 05:23 UTC, plus on demand via *Actions → Live-Tests → Run
workflow*. See [`.github/workflows/live-tests.yml`](.github/workflows/live-tests.yml).

**Who sees it:** A red run opens an issue labelled `upstream` and the stable title “Live-Tests gegen energiedashboard.admin.ch rot (<Datum>)”. A second red run recognises the open issue by its title prefix and appends to that same thread rather than opening a second one. Once the suite is green again, the issue closes itself.

**Three answers, not two.** `scripts/classify_live_run.py` reads the JUnit XML rather than
the exit code and separates `clear` (ran, green), `finding` (ran, something
fell) and `unknown` (did not run — install failed, nothing collected,
everything skipped). An `unknown` never closes an issue: closing would claim a
comparison that never happened.

**A red live run does not necessarily mean *our* bug.** It means the contract
with the source has changed, or the source is down. Both belong seen; only the
first belongs fixed. Please read the run before disabling the job — that is how
this check dies, and it is the only one in the repository that can contradict a
wrong assumption about energiedashboard.admin.ch. Every other test asserts against a fixture, and
the fixture was written from the same assumption as the code.
