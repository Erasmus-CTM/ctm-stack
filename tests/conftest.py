"""Controlled Quarto pages for behavioral tests, independent of site copy.

The tests import ctm_checkers (with its STACK engine) from the wheels of the
installed ctm-checkers, as the build's Python does (tests/ctm_parts.py)."""
import shutil

import pytest

import ctm_parts

ctm_parts.python_path()
from test_render import ROOT, render_site


@pytest.fixture(scope="session")
def browser_site(tmp_path_factory):
    project = tmp_path_factory.mktemp("browser-project")
    shutil.copytree(ROOT / "tests/fixtures/browser", project, dirs_exist_ok=True)
    shutil.copytree(ROOT / "_extensions/stack-sympy", project / "_extensions/stack-sympy")
    ctm_parts.install(project)
    shutil.copytree(ROOT / "questions", project / "questions")
    return render_site(project)
