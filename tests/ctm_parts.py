"""CTM Assessment's parts that ctm-stack builds against, for the tests.

ctm-libs (the bootstrap's target: the Python runtime, AI feedback) and
ctm-checkers (the STACK engine: wheels for native Python, page scripts for the
browser): where they are installed, how a test project gets them (as
`quarto add` installs them), and the environment of a component development
build (CTM_COMPONENT_DEV=1: ctm-libs without the CTM Assessment package).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = ROOT / "_extensions"


def _locate(name: str, entry: str, variable: str) -> Path:
    # The variable (an _extensions/<name> folder), else the installation in
    # this repository: `quarto add` of a checkout installs it under
    # _extensions/<name>, `quarto add Erasmus-CTM/<name>` under an owner folder.
    if os.environ.get(variable):
        return Path(os.environ[variable])
    candidates = [EXTENSIONS / name]
    if EXTENSIONS.is_dir():
        candidates += [owner / name for owner in sorted(EXTENSIONS.iterdir()) if owner.is_dir()]
    for folder in candidates:
        if (folder / entry).is_file():
            return folder
    raise RuntimeError(f"Install {name} first (quarto add of an Erasmus-CTM/{name} checkout at the "
                       f"commit of .github/pins.json), or set {variable} to its _extensions/{name} folder.")


CTM_LIBS = _locate("ctm-libs", "lua/ctm.lua", "CTM_LIBS_EXTENSION")
CTM_CHECKERS = _locate("ctm-checkers", "checkers.json", "CTM_CHECKERS_EXTENSION")
MANIFEST = json.loads((CTM_CHECKERS / "checkers.json").read_text())
# The wheels of ctm-checkers with its STACK engine (ctm.checkers.environment(env, "stack")).
WHEELS = [str(CTM_CHECKERS / MANIFEST["wheel"]), str(CTM_CHECKERS / MANIFEST["parts"]["stack"]["wheel"])]


def python_path() -> None:
    """Imports ctm_checkers (with ctm_checkers.stack) in this process from the wheels."""
    for wheel in reversed(WHEELS):
        if wheel not in sys.path:
            sys.path.insert(0, wheel)


def render_env() -> dict[str, str]:
    """A component development build: ctm-libs and ctm-checkers without the package."""
    return {**os.environ, "CTM_COMPONENT_DEV": "1", "CTM_VARIANTS": "review"}


def install(project: Path, owner: str = "", *, checkers: bool = True) -> None:
    """Copies ctm-libs (and ctm-checkers) into a test project, as `quarto add` does."""
    shutil.copytree(CTM_LIBS, project / "_extensions" / owner / "ctm-libs")
    if checkers:
        shutil.copytree(CTM_CHECKERS, project / "_extensions" / owner / "ctm-checkers")


def engine_data(payload):
    """Extract backend plans for the independent native oracle in browser tests."""
    assert payload["version"] == 2
    assert {"common", "backend", "variants"} <= payload.keys()
    assert all({"n", "id", "hash", "display", "plan"} <= item.keys() for item in payload["variants"])
    return dict(payload, question=payload["backend"]["question"],
                variants=[dict(item["plan"], **item["display"]) for item in payload["variants"]])
