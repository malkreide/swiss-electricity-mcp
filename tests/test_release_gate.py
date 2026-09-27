"""Tests fuer das Release-Gate: scripts/check_release_artifacts.py und seinen
Platz in .github/workflows/publish.yml.

Warum es das Gate gibt: 0.2.5 lag sieben Wochen lang kaputt auf PyPI, waehrend
jede Pruefung gruen war — alle prueften `main`, keine das Artefakt. Das Gate
schliesst nicht diese ganze Luecke (es prueft Metadaten, nicht das Verhalten),
aber den Teil, der nach dem Upload nicht mehr zu reparieren ist.

Zwei Haelften:

  - Das Skript, als Unterprozess gegen synthetische Wheels. Es haelt seinen
    Befund in Modul-Globalen; ein Import wuerde Funde zwischen Tests
    verschleppen.
  - Der Workflow, als Text gelesen wie in den anderen Workflow-Tests (kein
    PyYAML im dev-Extra). Ein Gate, das nicht aufgerufen wird, oder erst nach
    dem Upload, prueft nichts — und bleibt dabei gruen.

Dazu ein Test, der das Gate gegen die echten Quelldateien des Repos faehrt:
so faellt ein zu langer description-Text oder ein verschwundener Marker schon
im PR auf und nicht erst beim Tag.

Nur Standardbibliothek, kein Netz.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_release_artifacts.py"
PUBLISH = ROOT / ".github" / "workflows" / "publish.yml"

NAME = "io.github.malkreide/swiss-electricity-mcp"
MARKER = f"<!-- mcp-name: {NAME} -->"
VERSION = "1.2.3"


def _wheel(dist: Path, body: str, version: str = VERSION) -> Path:
    dist.mkdir(parents=True, exist_ok=True)
    wheel = dist / f"swiss_electricity_mcp-{version}-py3-none-any.whl"
    meta = (
        "Metadata-Version: 2.4\n"
        "Name: swiss-electricity-mcp\n"
        f"Version: {version}\n"
        "Description-Content-Type: text/markdown\n"
        "\n"
        f"{body}\n"
    )
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.writestr(f"swiss_electricity_mcp-{version}.dist-info/METADATA", meta)
    return wheel


def _repo(
    root: Path,
    *,
    readme: str = f"# Server\n\n{MARKER}\n",
    version: str = VERSION,
    sj_version: str = VERSION,
    name: str = NAME,
    description: str = "Swiss electricity tariffs",
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "swiss-electricity-mcp"\nversion = "{version}"\nreadme = "README.md"\n',
        encoding="utf-8",
    )
    (root / "README.md").write_text(readme, encoding="utf-8")
    (root / "server.json").write_text(
        json.dumps({"name": name, "description": description, "version": sj_version}),
        encoding="utf-8",
    )
    return root


def _gate(dist: Path, repo: Path, tag: str | None = f"v{VERSION}"):
    cmd = [sys.executable, str(SCRIPT), "--dist", str(dist), "--repo", str(repo)]
    if tag is not None:
        cmd += ["--tag", tag]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")


# --- Skript ------------------------------------------------------------------


def test_sauberer_stand_passiert(tmp_path):
    _wheel(tmp_path / "dist", f"# Server\n\n{MARKER}\n")
    r = _gate(tmp_path / "dist", _repo(tmp_path / "repo"))
    assert r.returncode == 0, r.stdout
    assert "0 Blocker" in r.stdout
    assert "✓ A4" in r.stdout


def test_ohne_wheel_stoppt(tmp_path):
    (tmp_path / "dist").mkdir()
    r = _gate(tmp_path / "dist", _repo(tmp_path / "repo"))
    assert r.returncode == 1
    assert "Kein Wheel" in r.stdout


def test_marker_fehlt_im_wheel(tmp_path):
    _wheel(tmp_path / "dist", "# Server ohne Marker\n")
    r = _gate(tmp_path / "dist", _repo(tmp_path / "repo"))
    assert r.returncode == 1
    assert "✗ A1: kein" in r.stdout


def test_zwei_marker_im_wheel(tmp_path):
    _wheel(tmp_path / "dist", f"{MARKER}\n\n{MARKER}\n")
    r = _gate(tmp_path / "dist", _repo(tmp_path / "repo"))
    assert r.returncode == 1
    assert "✗ A1: 2 Marker" in r.stdout


def test_marker_im_wheel_aber_nicht_in_der_readme_quelle(tmp_path):
    _wheel(tmp_path / "dist", f"# Server\n\n{MARKER}\n")
    r = _gate(tmp_path / "dist", _repo(tmp_path / "repo", readme="# Server\n"))
    assert r.returncode == 1
    assert "nicht in README.md" in r.stdout


def test_marker_weicht_vom_registry_namen_ab(tmp_path):
    _wheel(tmp_path / "dist", f"# Server\n\n{MARKER}\n")
    repo = _repo(tmp_path / "repo", name="io.github.malkreide/anderer-mcp")
    r = _gate(tmp_path / "dist", repo)
    assert r.returncode == 1
    assert "≠ server.json name" in r.stdout


@pytest.mark.parametrize(("laenge", "code"), [(100, 0), (101, 1)])
def test_description_grenze_bei_100(tmp_path, laenge, code):
    _wheel(tmp_path / "dist", f"# Server\n\n{MARKER}\n")
    repo = _repo(tmp_path / "repo", description="x" * laenge)
    r = _gate(tmp_path / "dist", repo)
    assert r.returncode == code, r.stdout
    assert (f"{laenge} Zeichen (max. 100)" in r.stdout) == (code == 1)


def test_server_json_version_weicht_von_pyproject_ab(tmp_path):
    _wheel(tmp_path / "dist", f"# Server\n\n{MARKER}\n")
    r = _gate(tmp_path / "dist", _repo(tmp_path / "repo", sj_version="1.2.2"))
    assert r.returncode == 1
    assert "✗ Version: server.json 1.2.2 ≠ pyproject 1.2.3" in r.stdout


def test_tag_weicht_von_gebauter_version_ab(tmp_path):
    _wheel(tmp_path / "dist", f"# Server\n\n{MARKER}\n")
    r = _gate(tmp_path / "dist", _repo(tmp_path / "repo"), tag="v1.2.2")
    assert r.returncode == 1
    assert "✗ A4: Tag v1.2.2 ≠ gebaute Version 1.2.3" in r.stdout


def test_ohne_tag_wird_a4_uebersprungen(tmp_path):
    """Dokumentiert die Luecke, die der Workflow mit `:?` schliesst."""
    _wheel(tmp_path / "dist", f"# Server\n\n{MARKER}\n")
    r = _gate(tmp_path / "dist", _repo(tmp_path / "repo"), tag=None)
    assert r.returncode == 0
    assert "A4" not in r.stdout


def test_echte_quelldateien_bestehen_das_gate(tmp_path):
    """Das Repo selbst, mit einem Wheel, dessen README die echte ist.

    So wie hatchling baut: die als `readme` deklarierte Datei wird zum Body der
    METADATA. Faellt hier etwas, faellt es beim naechsten Release auch.
    """
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    body = (ROOT / project["readme"]).read_text(encoding="utf-8")
    _wheel(tmp_path / "dist", body, version=project["version"])
    r = _gate(tmp_path / "dist", ROOT, tag=f"v{project['version']}")
    assert r.returncode == 0, r.stdout


# --- Workflow ----------------------------------------------------------------


def _job(text: str, name: str) -> str:
    m = re.search(rf"^  {name}:\n(.*?)(?=^  \S|\Z)", text, re.M | re.S)
    assert m, f"Job {name!r} fehlt in publish.yml"
    return m.group(1)


def _steps(job: str) -> list[str]:
    return re.split(r"^      - ", job, flags=re.M)[1:]


def _code(step: str) -> str:
    return "\n".join(line for line in step.splitlines() if not line.lstrip().startswith("#"))


def _gate_step(job: str) -> tuple[int, str]:
    treffer = [
        (i, s) for i, s in enumerate(_steps(job)) if "check_release_artifacts.py" in _code(s)
    ]
    assert len(treffer) == 1, "Release-Gate muss genau einmal im build-Job stehen"
    return treffer[0]


def test_gate_steht_zwischen_build_und_upload():
    steps = _steps(_job(PUBLISH.read_text(encoding="utf-8"), "build"))
    i_build = next(i for i, s in enumerate(steps) if "python -m build" in _code(s))
    i_upload = next(i for i, s in enumerate(steps) if "actions/upload-artifact" in _code(s))
    i_gate, _ = _gate_step(_job(PUBLISH.read_text(encoding="utf-8"), "build"))
    assert i_build < i_gate < i_upload


def test_gate_bekommt_den_tag_und_stoppt_ohne():
    _, step = _gate_step(_job(PUBLISH.read_text(encoding="utf-8"), "build"))
    code = _code(step)
    assert "TAG: ${{ github.event.release.tag_name }}" in code
    run = code.split("run:", 1)[1]
    assert '--tag "${TAG:?' in run
    assert "${{" not in run, "Ausdruecke gehoeren in env, nicht in die Shell-Zeile"
    assert "continue-on-error" not in code


def test_gate_prueft_dist_und_repo():
    _, step = _gate_step(_job(PUBLISH.read_text(encoding="utf-8"), "build"))
    run = _code(step).split("run:", 1)[1]
    assert "--dist dist" in run
    assert "--repo ." in run


def test_upload_haengt_am_build_job():
    text = PUBLISH.read_text(encoding="utf-8")
    assert re.search(r"^    needs: build$", _job(text, "publish"), re.M)
    assert re.search(r"^    needs: publish$", _job(text, "publish-mcp"), re.M)
