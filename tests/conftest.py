"""Controlled Quarto pages for behavioral tests, independent of site copy."""
import shutil

import pytest

from test_render import ROOT, render_site


@pytest.fixture(scope="session")
def browser_site(tmp_path_factory):
    project = tmp_path_factory.mktemp("browser-project")
    shutil.copytree(ROOT / "tests/fixtures/browser", project, dirs_exist_ok=True)
    for name in ("stack-sympy", "ai-feedback"):
        shutil.copytree(ROOT / "_extensions" / name, project / "_extensions" / name)
    shutil.copytree(ROOT / "questions", project / "questions")
    return render_site(project)
