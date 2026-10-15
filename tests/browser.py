"""Full browser integration through Quarto HTML, Worker, Pyodide and SymPy."""
from __future__ import annotations

from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright

from test_render import render_site


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

        card.locator(".stack-answer").first.fill("x+x")
        card.locator(".stack-validate").click()
        card.locator('.stack-validation[data-state="valid"]').wait_for(timeout=120000)
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
            answer.fill("0")
        multi.locator(".stack-validate").click()
        multi.locator('.stack-result[data-state="valid"]').wait_for(timeout=120000)
        assert multi.locator(".stack-check").is_enabled()
        multi.locator(".stack-check").click()
        multi.locator(".stack-result .stack-verdict").wait_for(timeout=120000)
        assert multi.locator(".stack-result").get_attribute("data-state") == "retry"
        assert not errors, errors
        browser.close()
