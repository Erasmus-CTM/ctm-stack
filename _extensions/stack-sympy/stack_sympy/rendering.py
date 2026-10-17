"""Render a safe, deliberately limited subset of STACK CASText."""

from __future__ import annotations

import html
import json
from html.parser import HTMLParser
import re
import secrets

import sympy as sp

from .expressions import evaluate, form_latex, parse
from .importer import UnsupportedQuestion


_MARKER = re.compile(r"\{@(.*?)@\}|\[\[([^\]]+)\]\]", re.S)
_TAGS = {"p", "div", "span", "br", "hr", "strong", "b", "em", "i", "u", "ul", "ol", "li", "sub", "sup", "blockquote", "code", "pre", "a", "table", "thead", "tbody", "tr", "th", "td", "h1", "h2", "h3", "h4", "h5", "h6"}
_VOID = {"br", "hr"}


class _Sanitizer(HTMLParser):
    def __init__(self, question, location):
        super().__init__(convert_charrefs=False)
        self.question, self.location = question, location
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag not in _TAGS:
            raise UnsupportedQuestion(self.question, self.location, f"unsupported HTML tag <{tag}>")
        safe = []
        for key, value in attrs:
            if key in {"class", "title"} and value is not None:
                safe.append(f' {key}="{html.escape(value, quote=True)}"')
            elif key == "href" and tag == "a" and value is not None and (value.startswith("#") or value.startswith("https://")):
                safe.append(f' href="{html.escape(value, quote=True)}" rel="noopener noreferrer"')
            else:
                raise UnsupportedQuestion(self.question, self.location, f"unsupported HTML attribute {key!r} on <{tag}>")
        self.parts.append(f"<{tag}{''.join(safe)}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag not in _TAGS:
            raise UnsupportedQuestion(self.question, self.location, f"unsupported closing tag </{tag}>")
        if tag not in _VOID:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        self.parts.append(html.escape(data, quote=False))

    def handle_entityref(self, name):
        self.parts.append(f"&{name};" if name in html.entities.html5 else f"&amp;{html.escape(name)};")

    def handle_charref(self, name):
        self.parts.append(f"&#{name};")

    def handle_comment(self, data):
        raise UnsupportedQuestion(self.question, self.location, "HTML comments are unsupported")


def render_castext(source: str, env: dict, question: str, location: str, *, inputs=(), feedback=None,
                   assumptions=None, form_expression=None) -> str:
    """Substitute CASText tokens, then allowlist sanitize the HTML.

    Literal source text never enters an HTML attribute through a token.
    Escaped placeholders are held as private sentinels until after sanitizing.
    """
    # Nested list syntax inside a CAS expression is not a CASText directive.
    outside_expressions = re.sub(r"\{@.*?@\}", "", source, flags=re.S)
    if re.search(r"\[\[(?!input:|validation:|feedback:)", outside_expressions):
        raise UnsupportedQuestion(question, location, "unsupported CASText block")
    placeholders = {}
    nonce = secrets.token_hex(12)
    while nonce in source:
        nonce = secrets.token_hex(12)
    def substitute(match):
        prefix = source[:match.start()]
        if prefix.rfind("<") > prefix.rfind(">"):
            raise UnsupportedQuestion(question, location, "CASText tokens inside HTML tags are unsupported")
        expr, directive = match.groups()
        if expr is not None:
            try:
                # STACK CASText also prints scalar equations, e.g. {@p=ta@}.
                # Keep equation parsing local to display; student/author CAS
                # expressions still have the stricter scalar grammar.
                sides = [part.strip() for part in expr.split("=")]
                if len(sides) not in (1, 2) or any(not side for side in sides):
                    raise ValueError("Only a scalar equality is supported")
                trees = [parse(side) for side in sides]
                def random_call(node):
                    return (node.kind == "call" and node.value in {"rand", "rand_with_step"}) or any(random_call(c) for c in node.children)
                if any(random_call(tree) for tree in trees):
                    raise UnsupportedQuestion(question, location, "random CASText expressions must be assigned in question variables")
                if form_expression is not None:
                    rendered_sides = [form_latex(parse(form_expression(side))) for side in sides]
                else:
                    rendered_sides = [sp.latex(evaluate(tree, env=env, assumptions=assumptions)) for tree in trees]
                latex = " = ".join(rendered_sides)
            except UnsupportedQuestion:
                raise
            except Exception as exc:
                raise UnsupportedQuestion(question, location, f"invalid CASText expression {expr!r}: {exc}") from exc
            # STACK CASText can appear inside an existing TeX delimiter.
            # Nested \( ... \) would make MathJax render literal markup.
            math_delimiters = list(re.finditer(r"\\(?:\(|\)|\[|\])", prefix))
            in_math = bool(math_delimiters and math_delimiters[-1].group() in {r"\(", r"\["})
            # The braces in {@expr@} are TeX grouping when already inside
            # math, e.g. \frac{@a+b@}{@c@} or ^{@power@}.
            rendered = "{" + html.escape(latex) + "}" if in_math else r"\(" + html.escape(latex) + r"\)"
        else:
            kind, sep, name = directive.partition(":")
            if not sep or (kind in {"input", "validation"} and name not in inputs) or (kind == "feedback" and name not in (feedback or ())):
                raise UnsupportedQuestion(question, location, f"unknown CASText token [[{directive}]]")
            safe_name = html.escape(name, quote=True)
            if kind == "input":
                inp = inputs.get(name, {}) if isinstance(inputs, dict) else {}
                size = inp.get("boxsize", 15)
                if inp.get("type") == "matrix":
                    value = evaluate(inp["teacher"], env=env, assumptions=assumptions)
                    shape = getattr(value, "shape", None)
                    if shape is None or len(shape) != 2 or min(shape) < 1 or max(shape) > 16 or shape[0] * shape[1] > 64:
                        raise UnsupportedQuestion(question, location, "matrix teacher requires positive shape bounded by 16 axes and 64 entries")
                    config = inp.get("matrix") or {
                        key: {"auto": False, "initial": int(n), "min": int(n), "max": int(n)}
                        for key, n in zip(("rows", "cols"), shape)}
                    spec = html.escape(json.dumps({"name": name, **config}), quote=True)
                    rendered = f'<span class="stack-answer stack-matrix" data-name="{safe_name}" data-matrix-spec="{spec}" role="group" aria-label="Answer {safe_name}"></span>'
                else:
                    rendered = f'<input class="stack-answer" data-name="{safe_name}" aria-label="Answer {safe_name}" size="{min(max(size, 1), 60)}" autocomplete="off">'
            elif kind == "validation":
                rendered = f'<span class="stack-validation" data-name="{safe_name}" aria-live="polite"></span>'
            else:
                rendered = f'<span class="stack-feedback" data-name="{safe_name}"></span>'
        token = f"STACKTOKEN{nonce}{len(placeholders)}END"
        placeholders[token] = rendered
        return token
    text = _MARKER.sub(substitute, source or "")
    if "{@" in text or "[[" in text:
        raise UnsupportedQuestion(question, location, "unclosed or unsupported CASText token")
    sanitizer = _Sanitizer(question, location)
    sanitizer.feed(text)
    sanitizer.close()
    output = "".join(sanitizer.parts)
    for token, value in placeholders.items():
        output = output.replace(token, value)
    return output
