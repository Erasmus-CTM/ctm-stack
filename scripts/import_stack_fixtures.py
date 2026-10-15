"""Import the pinned STACK answer-test fixture literal without evaluating PHP.

Only the static ``protected static $rawdata`` initializer is read. Unknown
expressions fail closed, so source changes cannot quietly remove test rows.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT.parent / "stack-upstream"
SOURCE_PATH = "tests/fixtures/answertestfixtures.class.php"
COMMIT = "10d323311b7f39fb7b092dd10ce75f7d8632f525"
REPOSITORY = "maths/moodle-qtype_stack"
OUTPUT = ROOT / "tests/native_compliance/fixtures.json"
MAX_SOURCE_BYTES = 2_000_000
MAX_ARRAY_DEPTH = 16
INITIALIZER = re.compile(r"\bprotected\s+static\s+\$rawdata\s*=", re.ASCII)
NUMBER = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")


class FixtureSyntaxError(ValueError):
    """Unsupported or malformed PHP literal at a precise source location."""


class LiteralParser:
    """Small, bounded parser: arrays, scalar literals, and string joins only."""

    def __init__(self, source: str, position: int):
        self.source = source
        self.position = position
        self.depth = 0

    def error(self, reason: str) -> FixtureSyntaxError:
        line = self.source.count("\n", 0, self.position) + 1
        return FixtureSyntaxError(f"line {line}: {reason} near {self.source[self.position:self.position+30]!r}")

    def skip(self) -> None:
        s = self.source
        while self.position < len(s):
            if s[self.position].isspace():
                self.position += 1
            elif s.startswith("//", self.position) or s.startswith("#", self.position):
                end = s.find("\n", self.position)
                self.position = len(s) if end < 0 else end
            elif s.startswith("/*", self.position):
                end = s.find("*/", self.position + 2)
                if end < 0:
                    raise self.error("unterminated block comment")
                self.position = end + 2
            else:
                break

    def take(self, char: str) -> bool:
        self.skip()
        if self.source.startswith(char, self.position):
            self.position += len(char)
            return True
        return False

    def require(self, char: str) -> None:
        if not self.take(char):
            raise self.error(f"expected {char!r}")

    def string(self) -> str:
        s = self.source
        quote = s[self.position]
        self.position += 1
        result = []
        double = {"n": "\n", "r": "\r", "t": "\t", "v": "\v", "e": "\x1b", "f": "\f", "\\": "\\", "$": "$", '"': '"'}
        while self.position < len(s):
            char = s[self.position]
            self.position += 1
            if char == quote:
                return "".join(result)
            if char != "\\":
                if quote == '"' and char == "$":
                    raise self.error("interpolated double-quoted strings are unsupported")
                result.append(char)
                continue
            if self.position >= len(s):
                raise self.error("unterminated escape")
            escaped = s[self.position]
            self.position += 1
            if quote == "'":
                result.append(escaped if escaped in ("'", "\\") else "\\" + escaped)
            elif escaped in double:
                result.append(double[escaped])
            elif escaped in "01234567":
                digits = escaped
                for _ in range(2):
                    if self.position < len(s) and s[self.position] in "01234567":
                        digits += s[self.position]
                        self.position += 1
                result.append(chr(int(digits, 8) % 256))
            elif escaped == "x":
                match = re.match(r"[0-9a-fA-F]{1,2}", s[self.position:])
                if match:
                    result.append(chr(int(match.group(), 16)))
                    self.position += len(match.group())
                else:
                    result.append("\\x")
            elif escaped == "u" and s.startswith("{", self.position):
                match = re.match(r"\{([0-9a-fA-F]+)\}", s[self.position:])
                if not match or int(match.group(1), 16) > 0x10FFFF:
                    raise self.error("invalid Unicode escape")
                result.append(chr(int(match.group(1), 16)))
                self.position += len(match.group())
            else:
                result.append("\\" + escaped)
        raise self.error("unterminated string")

    def atom(self):
        self.skip()
        s = self.source
        if self.position >= len(s):
            raise self.error("unexpected end of initializer")
        char = s[self.position]
        if char == "[":
            return self.array()
        if char in "'\"":
            return self.string()
        if char == "-":
            self.position += 1
            value = self.atom()
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise self.error("unary minus requires a numeric literal")
            return -value
        match = NUMBER.match(s, self.position)
        if match:
            self.position = match.end()
            value = match.group()
            return float(value) if any(c in value for c in ".eE") else int(value)
        for literal, value in (("true", True), ("false", False), ("null", None)):
            if s.startswith(literal, self.position) and (
                self.position + len(literal) == len(s)
                or not (s[self.position + len(literal)].isalnum() or s[self.position + len(literal)] == "_")
            ):
                self.position += len(literal)
                return value
        raise self.error("unsupported PHP expression")

    def value(self):
        result = self.atom()
        while self.take("."):
            next_value = self.atom()
            if not isinstance(result, str) or not isinstance(next_value, str):
                raise self.error("only string-literal concatenation is supported")
            result += next_value
        return result

    def array(self):
        self.depth += 1
        if self.depth > MAX_ARRAY_DEPTH:
            raise self.error("array nesting exceeds supported limit")
        self.require("[")
        values = []
        if self.take("]"):
            self.depth -= 1
            return values
        while True:
            values.append(self.value())
            if self.take("]"):
                self.depth -= 1
                return values
            self.require(",")
            if self.take("]"):
                self.depth -= 1
                return values


def parse_static_rawdata(source: str) -> list[tuple[int, list]]:
    if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise FixtureSyntaxError("fixture source exceeds supported size")
    matches = list(INITIALIZER.finditer(source))
    if len(matches) != 1:
        raise FixtureSyntaxError(f"expected one static $rawdata initializer, found {len(matches)}")
    parser = LiteralParser(source, matches[0].end())
    parser.require("[")
    rows = []
    if not parser.take("]"):
        while True:
            parser.skip()
            line = source.count("\n", 0, parser.position) + 1
            row = parser.value()
            if not isinstance(row, list):
                raise parser.error("fixture row must be an array")
            rows.append((line, row))
            if parser.take("]"):
                break
            parser.require(",")
            if parser.take("]"):
                break
    parser.require(";")
    return rows


def make_document(source: str, sha256: str) -> dict:
    occurrences = defaultdict(int)
    cases = []
    for ordinal, (line, row) in enumerate(parse_static_rawdata(source), 1):
        if len(row) < 7 or any(not isinstance(row[i], str) for i in (0, 1, 2, 3, 5, 6)):
            raise FixtureSyntaxError(f"line {line}: row must have six string fields and a numeric score")
        if isinstance(row[4], bool) or not isinstance(row[4], (int, float)) or not math.isfinite(row[4]):
            raise FixtureSyntaxError(f"line {line}: score must be numeric")
        digest = hashlib.sha256(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
        occurrences[digest] += 1
        cases.append({
            "id": f"{digest}-{occurrences[digest]}", "ordinal": ordinal, "source_line": line,
            "test": row[0], "options": row[1], "student": row[2], "teacher": row[3],
            "expected_score": row[4], "answer_note": row[5], "notes": row[6],
            "extra_fields": row[7:],
        })
    return {
        "schema_version": 1,
        "upstream": {
            "repository": REPOSITORY, "commit": COMMIT, "path": SOURCE_PATH,
            "sha256": sha256,
            "source_url": f"https://github.com/{REPOSITORY}/blob/{COMMIT}/{SOURCE_PATH}",
        },
        "inventory": {
            "total_rows": len(cases),
            "by_test": dict(sorted(Counter(case["test"] for case in cases).items())),
            "scope": "Static protected $rawdata only; get_raw_test_data() also appends equivfixtures.class.php at runtime, which is outside this inventory.",
        },
        "cases": cases,
    }


def build(source_path: Path) -> dict:
    source_bytes = source_path.read_bytes()
    return make_document(source_bytes.decode("utf-8"), hashlib.sha256(source_bytes).hexdigest())


def verify_revision(upstream: Path) -> None:
    try:
        revision = subprocess.check_output(
            ["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True, stderr=subprocess.PIPE
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError(f"cannot verify pinned upstream git revision: {exc}") from exc
    if revision != COMMIT:
        raise ValueError(f"upstream revision {revision} differs from pinned {COMMIT}")


def main(argv=None) -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--upstream", type=Path, default=UPSTREAM, help="local checkout at the pinned revision")
    cli.add_argument("--output", type=Path, default=OUTPUT)
    cli.add_argument("--check", action="store_true", help="verify output matches exact pinned local source")
    args = cli.parse_args(argv)
    try:
        verify_revision(args.upstream)
        document = build(args.upstream / SOURCE_PATH)
        expected = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        if args.check:
            if not args.output.exists() or args.output.read_text(encoding="utf-8") != expected:
                raise ValueError(f"{args.output} differs from pinned upstream; regenerate fixture inventory")
            print(f"Verified {len(document['cases'])} static fixture rows and source SHA-256")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(expected, encoding="utf-8")
            print(f"Imported {len(document['cases'])} static fixture rows to {args.output}")
        return 0
    except (FixtureSyntaxError, ValueError, OSError, UnicodeError) as exc:
        print(f"fixture import failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
