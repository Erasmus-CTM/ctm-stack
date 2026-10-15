"""Full browser integration through Quarto HTML, Worker, Pyodide and SymPy."""
from __future__ import annotations

from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright

from test_render import render_site


CORPUS = Path(__file__).resolve().parents[1] / "questions/corpus"


@contextmanager
def serve(directory: Path):
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(directory)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_browser_worker_grades_and_runs_authored_tests():
    site = render_site()
    with serve(site) as url, sync_playwright() as pw:
        browser_options = {"headless": True}
        if os.environ.get("STACK_SYMPY_CHROMIUM"):
            browser_options["executable_path"] = os.environ["STACK_SYMPY_CHROMIUM"]
        browser = pw.chromium.launch(**browser_options)
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url + "/index.html", wait_until="domcontentloaded")
        card = page.locator(".stack-sympy:not(.stack-diagnostic)").first
        assert card.count() == 1
        assert card.locator(".stack-answer").count() > 0
        card.locator(".stack-prompt mjx-container").first.wait_for(timeout=60000)

        # Exact tests from the imported XML must execute in the browser's
        # bundled Python engine, rather than a JavaScript imitation.
        card.locator(".stack-tests").click()
        card.locator(".stack-result .stack-verdict").wait_for(timeout=180000)
        assert "All authored tests passed" in card.locator(".stack-result").inner_text()

        card.locator(".stack-answer").first.fill("!!!")
        assert card.locator(".stack-check").is_disabled()
        card.locator(".stack-validate").click()
        card.locator(".stack-result .stack-verdict").wait_for(timeout=120000)
        assert card.locator(".stack-result").get_attribute("data-state") == "invalid"
        assert card.locator(".stack-check").is_disabled()

        # The demo opts into STACK's implied-multiplication input setting.
        # Validation must display the same polynomial without artificial
        # parentheses from the parser's left-associated addition tree.
        card.locator(".stack-answer").first.fill("x**2+8x+15")
        card.locator(".stack-validate").click()
        card.locator('.stack-validation[data-state="valid"]').wait_for(timeout=120000)
        preview = card.locator('.stack-validation').first
        preview.locator('mjx-container').first.wait_for(timeout=60000)
        assert preview.get_attribute('data-latex') == r'x^{2} + 8x + 15'
        card.locator(".stack-check").click()
        card.locator(".stack-result .stack-verdict").wait_for(timeout=120000)
        assert card.locator(".stack-result").get_attribute("data-state") == "correct"

        card.locator(".stack-answer").first.fill("x+x")
        card.locator(".stack-validate").click()
        card.locator('.stack-validation[data-state="valid"]').wait_for(timeout=120000)
        card.locator('.stack-validation mjx-container').first.wait_for(timeout=60000)
        assert card.locator('.stack-validation').first.get_attribute('data-latex') == 'x + x'
        assert card.locator(".stack-check").is_enabled()
        assert card.locator(".stack-result").get_attribute("data-state") == "valid"
        assert "score" not in card.locator(".stack-result").inner_text().lower()
        card.locator(".stack-check").click()
        card.locator(".stack-answer").first.fill("x+x+1")
        assert card.locator(".stack-check").is_disabled()
        page.wait_for_timeout(1000)  # old Worker result must not repaint the edited response
        assert card.locator(".stack-result").inner_text() == ""

        # A variant switch clears stale answers/results and updates CASText.
        selector = card.locator(".stack-variant")
        if selector.count():
            selector.select_option(index=1)
            assert card.locator(".stack-answer").first.input_value() == ""
            assert card.locator(".stack-result").inner_text() == ""
            card.locator(".stack-prompt mjx-container").first.wait_for(timeout=60000)

        page.goto(url + "/examples.html", wait_until="domcontentloaded")
        cards = page.locator(".stack-sympy:not(.stack-diagnostic)")
        assert cards.count() >= 3, "equivalent, numerical and upstream examples should render"
        for index in range(cards.count()):
            example = cards.nth(index)
            assert example.locator(".stack-answer").count() > 0
            example.locator(".stack-tests").click()
            example.locator(".stack-result .stack-verdict").wait_for(timeout=180000)
            assert "All authored tests passed" in example.locator(".stack-result").inner_text(), index
        multi = None
        # Find the authored multi-input numerical case without depending on
        # the visual order of the examples.
        for index in range(cards.count()):
            if cards.nth(index).locator(".stack-answer").count() >= 3:
                multi = cards.nth(index)
                break
        assert multi is not None, "numerical multi-input example was not rendered"
        for answer in multi.locator(".stack-answer").all():
            answer.fill("0.00")
        multi.locator(".stack-validate").click()
        multi.locator('.stack-result[data-state="valid"]').wait_for(timeout=120000)
        assert multi.locator(".stack-check").is_enabled()
        multi.locator(".stack-check").click()
        multi.locator(".stack-result .stack-verdict").wait_for(timeout=120000)
        assert multi.locator(".stack-result").get_attribute("data-state") == "retry"
        (site.parent / "test-results").mkdir(exist_ok=True)
        page.screenshot(path=str(site.parent / "test-results/example.png"), full_page=True)
        assert not errors, errors
        browser.close()


def _prime_power_answer(number: int) -> str:
    """Build a written prime product independently of the CAS's factor form."""
    assert number > 1
    factors = []
    divisor = 2
    while divisor * divisor <= number:
        exponent = 0
        while number % divisor == 0:
            number //= divisor
            exponent += 1
        if exponent:
            factors.append(f"{divisor}^{exponent}" if exponent > 1 else str(divisor))
        divisor += 1
    if number > 1:
        factors.append(str(number))
    assert len(factors) > 1, "the displayed integer should have multiple prime factors"
    return "*".join(factors)


def _check_corpus_answer(card, answer: str, expected_state: str) -> None:
    response = card.locator('.stack-answer[data-name="ans"]')
    assert response.count() == 1
    response.fill(answer)
    card.locator(".stack-validate").click()
    card.locator('.stack-result[data-state="valid"] .stack-verdict').wait_for(timeout=120000)
    assert card.locator(".stack-check").is_enabled(), answer
    card.locator(".stack-check").click()
    card.locator(f'.stack-result[data-state="{expected_state}"] .stack-verdict').wait_for(timeout=120000)


def test_browser_corpus_native_author_tests_and_form_sensitive_answers():
    """Exercise the actual published cards with the bundled Worker/Pyodide CAS."""
    baseline = json.loads((CORPUS / "baseline.json").read_text())
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    reports = {item["id"]: item for item in baseline["questions"]}
    expected = {
        item["question_name"]: (item, reports[item["id"]])
        for item in manifest["questions"] if reports[item["id"]]["status"] == "qtests_pass"
    }
    assert {"AlgMap-2.1", "AlgMap-10.1", "AlgMap-13.1"} <= expected.keys()

    site = render_site()
    with serve(site) as url, sync_playwright() as pw:
        browser_options = {"headless": True}
        if os.environ.get("STACK_SYMPY_CHROMIUM"):
            browser_options["executable_path"] = os.environ["STACK_SYMPY_CHROMIUM"]
        browser = pw.chromium.launch(**browser_options)
        try:
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(url + "/corpus.html", wait_until="domcontentloaded")
            cards = page.locator(".stack-sympy:not(.stack-diagnostic)")
            assert cards.count() == len(expected)
            by_name = {}
            for index in range(cards.count()):
                card = cards.nth(index)
                payload = json.loads(card.locator("script.stack-sympy-data").text_content())
                name = payload["question"]["name"]
                assert name in expected and name not in by_name, name
                entry, report = expected[name]
                assert payload["variants"][0]["seed"] == report["seeds"][0], name
                assert card.locator(".stack-answer").count() == entry["input_count"], name
                by_name[name] = (card, payload["variants"][0]["env"])

                prompt = card.locator(".stack-prompt")
                prompt.locator("mjx-container").first.wait_for(timeout=60000)
                assert prompt.locator("mjx-merror").count() == 0, name

                card.locator(".stack-tests").click()
                card.locator(".stack-result .stack-verdict").wait_for(timeout=180000)
                assert card.locator(".stack-result").get_attribute("data-state") == "correct", name
                assert "All authored tests passed" in card.locator(".stack-result").inner_text(), name
                cases = card.locator(".stack-test-list li").all_inner_texts()
                assert len(cases) == entry["qtest_count"], name
                assert all(case.startswith("Pass · ") for case in cases), (name, cases)

            assert set(by_name) == set(expected)

            factor_card, env = by_name["AlgMap-10.1"]
            k, coefficient, variable = int(env["k1"]), int(env["cf1"]), env["v"]
            assert variable in {"x", "y", "z", "t"}
            common = math.gcd(k, coefficient)
            assert common > 1
            _check_corpus_answer(factor_card,
                                 f"{common}*({k // common}-{coefficient // common}*{variable})",
                                 "correct")
            _check_corpus_answer(factor_card, f"{k}-{coefficient}*{variable}", "retry")

            quadratic_card, env = by_name["AlgMap-13.1"]
            variable = env["v"]
            assert variable in {"x", "y", "z", "t"}
            response = quadratic_card.locator('.stack-answer[data-name="ans"]')
            response.fill(f"{variable}/({variable}-1)")
            quadratic_card.locator(".stack-validate").click()
            quadratic_card.locator('.stack-result[data-state="valid"] .stack-verdict').wait_for(timeout=120000)
            quadratic_card.locator(".stack-check").click()
            error_result = quadratic_card.locator('.stack-result[data-state="error"]')
            error_result.locator("p").wait_for(timeout=120000)
            error_text = error_result.inner_text()
            assert "FacForm supports only numeric denominators" in error_text
            assert all(fragment not in error_text for fragment in ("Traceback", 'File "', "PythonError"))

            # A corrected response recovers on the same card and Worker.
            first_coefficient, first_constant = int(env["cf1"]), int(env["a"])
            second_coefficient, second_constant = int(env["cf2"]), int(env["b"])
            factors = []
            for coefficient, constant in ((first_coefficient, first_constant),
                                          (second_coefficient, second_constant)):
                common = math.gcd(coefficient, constant)
                factors.append(f"{common}*({coefficient // common}*{variable}{constant // common:+d})")
            response.fill("*".join(factors))
            assert quadratic_card.locator(".stack-result").inner_text() == ""
            assert quadratic_card.locator(".stack-check").is_disabled()
            _check_corpus_answer(quadratic_card, response.input_value(), "correct")

            primes_card, env = by_name["AlgMap-2.1"]
            number = int(env["n"])
            _check_corpus_answer(primes_card, _prime_power_answer(number), "correct")
            _check_corpus_answer(primes_card, str(number), "retry")
            assert "not fully factored" in primes_card.locator(".stack-result .stack-prt-feedback").inner_text()
            assert not errors, errors
        finally:
            browser.close()
