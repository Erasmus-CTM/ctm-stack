"""Exercise the actual Quarto filter, CLI and copied browser assets."""
from __future__ import annotations

from functools import cache
import html
import os
from pathlib import Path
import re
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]


@cache
def render_site() -> Path:
    quarto = os.environ.get("QUARTO", "quarto")
    env = os.environ.copy()
    extension = ROOT / "_extensions/stack-sympy"
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(extension), env.get("PYTHONPATH", "")]))
    result = subprocess.run([quarto, "render"], cwd=ROOT, env=env,
                            text=True, capture_output=True, timeout=180)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    return ROOT / "_site"


def test_project_renders_cards_and_deployable_assets():
    site = render_site()
    index = (site / "index.html").read_text()
    examples = (site / "examples.html").read_text()
    guide = (site / "docs/authoring.html").read_text()
    assert 'class="stack-sympy-data"' in index or 'class="stack-sympy-data"' in examples
    assert index.count('class="stack-sympy-data"') == 1
    assert examples.count('class="stack-sympy-data"') >= 5
    assert guide.count('class="stack-sympy-data"') == 1
    assert "stack-diagnostic" not in index + examples + guide
    assert 'class="stack-check"' in index or 'stack-check' in index
    assert 'class="stack-validate"' in index or 'stack-validate' in index
    assert 'class="stack-tests"' in index or 'stack-tests' in index
    script = re.search(r'<script[^>]+src="([^"]*stack-sympy\.js)"', index)
    assert script, "Quarto did not install the page's JavaScript dependency"
    path = script.group(1).split("?", 1)[0]
    asset = site / path
    assert asset.is_file(), path
    for sibling in ("worker.js", "runtime-sources.js", "vendor/pyodide-runtime.js"):
        assert (asset.parent / sibling).is_file(), sibling
    assert "STACK_SYMPY_SOURCES" in (asset.parent / "runtime-sources.js").read_text()


def test_rendered_questions_show_authored_block_and_original_xml():
    site = render_site()
    panel = re.compile(r'<details class="stack-source"><summary>(Show source|Show STACK source)' r'</summary><pre><code class="language-(markdown|xml)">(.*?)</code></pre></details>', re.S)
    block = re.compile(r'^```\{\.stack-question\}\n(.*?)\n```$', re.M | re.S)
    for page in ("index", "examples", "docs/authoring"):
        qmd = ROOT / f"{page}.qmd"
        output = (site / f"{page}.html").read_text()
        rendered = panel.findall(output)
        count = output.count('class="stack-sympy"')
        assert len(rendered) == count * 2
        authored = block.findall(qmd.read_text())
        for i in range(count):
            first, second = rendered[i * 2:i * 2 + 2]
            assert first[:2] == ("Show source", "markdown")
            assert second[:2] == ("Show STACK source", "xml")
            assert html.unescape(first[2]) == "```{.stack-question}\n" + authored[i] + "\n```"
            path = re.search(r"^#\| file: (.+)$", authored[i], re.M).group(1)
            assert html.unescape(second[2]) == (qmd.parent / path).read_text()
            assert "<quiz>" not in second[2], "XML should be escaped as code"


def test_unsupported_question_stops_quarto_build():
    # An independent project avoids mutating the built site's website cache.
    with tempfile.TemporaryDirectory(dir=ROOT, prefix="invalid_stack_") as temporary:
        project = Path(temporary)
        (project / "_extensions").symlink_to(ROOT / "_extensions", target_is_directory=True)
        (project / "_quarto.yml").write_text("project:\n  type: default\nfilters:\n  - stack-sympy\n")
        (project / "test.qmd").write_text("```{.stack-question}\n#| file: missing.xml\n"
                                           "#| question: Missing\n```\n")
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT / "_extensions/stack-sympy"), env.get("PYTHONPATH", "")]))
        result = subprocess.run([os.environ.get("QUARTO", "quarto"), "render"],
                                cwd=project, env=env, text=True, capture_output=True, timeout=60)
        assert result.returncode != 0, "unsupported XML silently rendered"
        assert "could not render missing.xml / Missing" in result.stdout + result.stderr, (
            result.stdout + "\n" + result.stderr)
