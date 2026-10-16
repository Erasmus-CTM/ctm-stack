"""Exercise the actual Quarto filter, CLI and copied browser assets."""
from __future__ import annotations

from functools import cache
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
QUESTION = ROOT / "questions/polynomial-expansion.xml"


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


def test_corpus_page_tracks_manifest_baseline_and_only_passing_cards():
    from scripts.generate_corpus_page import generate, teaching_source

    manifest = json.loads((ROOT / "questions/corpus/manifest.json").read_text())
    baseline = json.loads((ROOT / "questions/corpus/baseline.json").read_text())
    entries = manifest["questions"]
    reports = {row["id"]: row for row in baseline["questions"]}
    authored = (ROOT / "corpus.qmd").read_text()
    assert authored == generate(), "regenerate with python scripts/generate_corpus_page.py"
    upstream_note = "A reduced answer with the wrong value can receive full credit."
    assert upstream_note in authored
    output = (render_site() / "corpus.html").read_text()
    assert upstream_note in output
    navbar = output
    assert re.search(r'href="(?:\./|/)?corpus\.html"', navbar)
    assert "Question corpus" in navbar
    assert len(entries) == len(reports) == 30
    passing = [entry for entry in entries if reports[entry["id"]]["status"] == "qtests_pass"]
    assert output.count('class="stack-sympy-data"') == len(passing)
    assert 'class="stack-sympy stack-diagnostic"' not in output
    assert output.count('<details class="stack-source">') == 2 * len(passing)
    assert '<details class="stack-source" open' not in output
    rendered_xml = re.findall(r'<code class="language-xml">(.*?)</code>', output, re.S)
    assert len(rendered_xml) == len(passing)
    for entry, source in zip(passing, rendered_xml):
        assert html.unescape(source) == (ROOT / teaching_source(entry)[0]).read_text()
    for entry in entries:
        assert f'id="{entry["id"]}"' in output
        assert f'questions/corpus/{entry["file"]}' in output
        assert html.escape(entry["source_url"], quote=True) in output
        assert (render_site() / "questions/corpus" / entry["file"]).is_file()
    assert "CC BY-SA 4.0" in output
    assert (render_site() / "questions/corpus/manifest.json").is_file()
    assert (render_site() / "questions/corpus/baseline.json").is_file()


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


def _fixture_render(source: str, *, shared: str | None = None,
                    filters: tuple[str, ...] = ("stack-sympy",),
                    files: dict[str, str] | None = None) -> tuple[subprocess.CompletedProcess, str]:
    with tempfile.TemporaryDirectory(dir=ROOT.parent, prefix="stack_feedback_render_") as temporary:
        project = Path(temporary)
        ext = project / "_extensions"
        ext.mkdir()
        shutil.copytree(ROOT / "_extensions/stack-sympy", ext / "stack-sympy")
        if shared:
            installed = ROOT / "_extensions/ai-feedback"
            assert installed.exists(), "install the shared AI Feedback extension before testing enabled cards"
            target = ext / "ai-feedback" if shared == "flat" else ext / "Erasmus-CTM/ai-feedback"
            target.parent.mkdir(exist_ok=True)
            shutil.copytree(installed, target)
        (project / "_quarto.yml").write_text(
            "project:\n  type: default\nfilters:\n" + "".join(f"  - {name}\n" for name in filters))
        (project / "test.qmd").write_text(source)
        for name, content in (files or {}).items():
            destination = project / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content)
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT / "_extensions/stack-sympy"), env.get("PYTHONPATH", "")]))
        result = subprocess.run([os.environ.get("QUARTO", "quarto"), "render"], cwd=project,
                                env=env, text=True, capture_output=True, timeout=90)
        output = (project / "test.html").read_text() if (project / "test.html").exists() else ""
        return result, output


def _card(feedback: str = "", extra: str = "") -> str:
    return ("```{.stack-question}\n"
            f"#| file: {QUESTION}\n"
            "#| question: Expand a product (form-sensitive)\n"
            f"{feedback}{extra}```\n")


def _feedback_cards(output: str) -> list[dict]:
    return [json.loads(html.unescape(encoded)) for encoded in
            re.findall(r'data-stack-feedback="([^"]+)"', output)]


def test_feedback_is_optional_and_missing_dependency_errors_only_when_enabled():
    result, output = _fixture_render("# Question\n\n" + _card())
    assert result.returncode == 0, result.stdout + result.stderr
    assert "data-stack-feedback" not in output
    assert "feedback-core.js" not in output
    result, _ = _fixture_render("# Question\n\n" + _card("#| feedback: true\n"))
    assert result.returncode != 0
    assert "Run: quarto add Erasmus-CTM/ai-feedback" in result.stdout + result.stderr


def test_shared_feedback_context_and_policy_are_emitted_once_per_page():
    source = ("---\nlang: de\n---\n"
              "# Exercise\n\nImplicit lesson context before the card.\n\n"
              "::: {.callout-note .ai-feedback-ignore}\nConfidential example answer in hidden callout.\n:::\n\n"
              + _card("#| feedback: true\n", "#| feedback-language: es\n")
              + "\n::: {#explanation .ai-context}\nUse $x^2$ in this explicit context.\n:::\n\n"
              + _card("#| feedback: true\n", "#| context: explanation\n#| label: policy-key\n")
              + "\n" + _card("#| feedback: true\n", "#| context: none\n"))
    for location, filters in (("flat", ("stack-sympy",)),
                              ("namespaced", ("stack-sympy", "ai-feedback")),
                              ("flat", ("ai-feedback", "stack-sympy"))):
        result, output = _fixture_render(source, shared=location, filters=filters)
        assert result.returncode == 0, result.stdout + result.stderr
        cards = _feedback_cards(output)
        assert len(cards) == 3
        assert output.count('feedback-core.js') == 1
        assert cards[0]["context"]["mode"] == "auto"
        assert "Implicit lesson context" in cards[0]["context"]["text"]
        assert "Confidential example answer" not in cards[0]["context"]["text"]
        assert cards[0]["language"] == "es"
        assert cards[0]["uiLanguage"] == "de"
        assert cards[1]["context"]["mode"] == "explicit"
        assert cards[1]["context"]["refs"] == "explanation"
        assert cards[1]["policySelection"]["exercise"] == "policy-key"
        assert cards[2]["context"]["mode"] == "none"
        assert "ai-feedback-ignore" in output
        assert "data-ai-feedback-context=&quot;" not in output
        assert "data-stack-feedback&quot;" not in output  # source panes are authored only


def test_named_policy_uses_shared_yaml_selection():
    source = ("---\nai-feedback:\n  page-policy-files: feedback/chapter.yml\n---\n"
              + _card("#| feedback: true\n", "#| label: expansion-practice\n#| feedback-policy: short-hints\n"))
    policy = ("ai-feedback:\n  integrations:\n    math-exercise:\n"
              "      max-words: 120\n  policies:\n    short-hints:\n"
              "      prompt: Ask for the next step.\n")
    result, output = _fixture_render(source, shared="flat", files={"feedback/chapter.yml": policy})
    assert result.returncode == 0, result.stdout + result.stderr
    assert _feedback_cards(output)[0]["policySelection"] == {
        "exercise": "expansion-practice", "name": "short-hints"}
    assert "short-hints" in output  # shared policy payload is emitted on the page
    result, _ = _fixture_render(source.replace("short-hints", "missing"), shared="flat",
                                files={"feedback/chapter.yml": policy})
    assert result.returncode != 0
    assert "unknown feedback-policy missing" in result.stdout + result.stderr
