"""Static STACK fixture import: no PHP interpreter or runtime dependencies."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/import_stack_fixtures.py"
spec = importlib.util.spec_from_file_location("import_stack_fixtures", SCRIPT)
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


def source(body):
    return "<?php\nclass Tests {\n protected static $rawdata = [\n" + body + "\n ];\n}\n"


class FixtureImportTests(unittest.TestCase):
    def test_literals_comments_line_numbers_and_php_escapes(self):
        php = source("""// skipped row in comment: ['NotARow'];
 ['AlgEquiv', '', 'x\\\\y', "line\\n\\\"quote\\\"", -1, 'a\\'b', 'hello' . /* join */ ' world', 'extra'],
 # another comment
 ['NumAbsolute', '', '\\q', '2', 0.5, '', '',],
""")
        rows = fixtures.parse_static_rawdata(php)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], 5)
        self.assertEqual(rows[1][0], 7)
        self.assertEqual(rows[0][1][2], "x\\y")
        self.assertEqual(rows[0][1][3], 'line\n"quote"')
        self.assertEqual(rows[0][1][5], "a'b")
        self.assertEqual(rows[0][1][6], "hello world")
        self.assertEqual(rows[1][1][2], "\\q")
        document = fixtures.make_document(php, "a" * 64)
        self.assertEqual(document["inventory"]["by_test"], {"AlgEquiv": 1, "NumAbsolute": 1})
        self.assertEqual(document["cases"][0]["extra_fields"], ["extra"])

    def test_php_double_quoted_unicode_and_single_quoted_literal_escapes(self):
        body = r'''['AlgEquiv', '', "\u{03A9}\t\$x", '\n\u{03A9}', -3, '', ''],
['AlgEquiv', '', 'x', 'x', -2, '', ''],
['AlgEquiv', '', 'x', 'x', -1, '', ''],'''
        rows = fixtures.parse_static_rawdata(source(body))
        self.assertEqual(rows[0][1][2], "Ω\t$x")
        self.assertEqual(rows[0][1][3], r"\n\u{03A9}")
        self.assertEqual([row[4] for _, row in rows], [-3, -2, -1])

    def test_duplicate_occurrences_have_stable_content_ids(self):
        row = "['AlgEquiv', '', 'x', 'x', 1, '', '']"
        document = fixtures.make_document(source(f"{row},\n{row},"), "a" * 64)
        ids = [case["id"] for case in document["cases"]]
        self.assertEqual(ids[0].rsplit("-", 1)[0], ids[1].rsplit("-", 1)[0])
        self.assertTrue(ids[0].endswith("-1"))
        self.assertTrue(ids[1].endswith("-2"))

    def test_rejects_dynamic_or_malformed_php_instead_of_omitting_rows(self):
        prefix = "'AlgEquiv', '', 'x', 'x', 1, '', ''"
        invalid = (
            (f"[{prefix}], get_fixture(),", "unsupported PHP expression"),
            (f"[{prefix}], ['AlgEquiv', '', compute(), 'x', 1, '', ''],", "unsupported PHP expression"),
            (f"[{prefix}] ['AlgEquiv', '', 'x', 'x', 1, '', ''],", "expected ','"),
            (f"[{prefix}], ['AlgEquiv', '', 'x' . $variable, 'x', 1, '', ''],", "unsupported PHP expression"),
            (f"[{prefix}], ['AlgEquiv', '', \"$variable\", 'x', 1, '', ''],", "interpolated"),
            (f"[{prefix}], ['AlgEquiv', '', 'x', 'x', 1/2, '', ''],", "expected ','"),
        )
        for body, reason in invalid:
            with self.subTest(body=body), self.assertRaisesRegex(fixtures.FixtureSyntaxError, reason):
                fixtures.parse_static_rawdata(source(body))

    def test_rejects_invalid_shape_and_oversized_source(self):
        with self.assertRaisesRegex(fixtures.FixtureSyntaxError, "six string fields"):
            fixtures.make_document(source("['AlgEquiv', '', 'x', 'x', 1, ''],"), "a" * 64)
        with self.assertRaisesRegex(fixtures.FixtureSyntaxError, "score must be numeric"):
            fixtures.make_document(source("['AlgEquiv', '', 'x', 'x', true, '', ''],"), "a" * 64)
        with self.assertRaisesRegex(fixtures.FixtureSyntaxError, "exceeds supported size"):
            fixtures.parse_static_rawdata("x" * (fixtures.MAX_SOURCE_BYTES + 1))
        nested = "[" * 17 + "'x'" + "]" * 17
        with self.assertRaisesRegex(fixtures.FixtureSyntaxError, "nesting exceeds"):
            fixtures.parse_static_rawdata(source(nested + ","))

    def test_checked_in_inventory_matches_exact_pinned_source(self):
        if not (fixtures.UPSTREAM / ".git").exists():
            self.skipTest("pinned upstream checkout unavailable")
        fixtures.verify_revision(fixtures.UPSTREAM)
        expected = fixtures.build(fixtures.UPSTREAM / fixtures.SOURCE_PATH)
        checked_in = json.loads(fixtures.OUTPUT.read_text(encoding="utf-8"))
        self.assertEqual(checked_in, expected)
        self.assertEqual(expected["inventory"]["total_rows"], 2303)
        self.assertEqual(expected["cases"][0]["source_line"], 69)
        self.assertEqual(expected["upstream"]["source_url"],
                         f"https://github.com/{fixtures.REPOSITORY}/blob/{fixtures.COMMIT}/{fixtures.SOURCE_PATH}")
        with tempfile.TemporaryDirectory() as tmp:
            changed = Path(tmp) / "changed.php"
            changed.write_bytes((fixtures.UPSTREAM / fixtures.SOURCE_PATH).read_bytes() + b"// changed\n")
            self.assertNotEqual(fixtures.build(changed)["upstream"]["sha256"], expected["upstream"]["sha256"])
        with patch.object(fixtures.subprocess, "check_output", return_value="different-revision\n"):
            with self.assertRaisesRegex(ValueError, "differs from pinned"):
                fixtures.verify_revision(fixtures.UPSTREAM)
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "fixtures.json"
            copy.write_text(fixtures.OUTPUT.read_text(encoding="utf-8"), encoding="utf-8")
            cmd = [sys.executable, str(SCRIPT), "--upstream", str(fixtures.UPSTREAM), "--output", str(copy), "--check"]
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            copy.write_text("{}\n", encoding="utf-8")
            self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)


if __name__ == "__main__":
    unittest.main()
