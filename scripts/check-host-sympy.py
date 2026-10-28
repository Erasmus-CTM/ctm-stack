#!/usr/bin/env python3
"""Check that the build host's SymPy pin is the SymPy of ctm-libs' Pyodide.

Native PythonCheckers grade authored tests at build time in host CPython and
in the learner's browser in ctm-libs' shared Pyodide. The compiled question
records the host SymPy (pythonIdentity.browserSympyVersion) and the browser
refuses to grade when its Pyodide SymPy differs (`python-checker-identity`).
ctm-libs owns the Pyodide pin and records the SymPy it bundles in
runtime/pyodide-sympy.json (its scripts/sync-pyodide-sympy.py); this repository
does not choose a SymPy version, it follows that record. No network or browser.

  python scripts/check-host-sympy.py --libs PATH

PATH: a ctm-libs checkout (CI: the commit of .github/pins.json or a review ref)
or an installed _extensions/ctm-libs; default $CTM_LIBS_EXTENSION, then
_ctm-libs-source, then _extensions/ctm-libs. The pin of requirements.txt and
the install commands of README.md and docs/authoring.qmd must equal its
`sympy` exactly.
"""
import argparse
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORD = Path('runtime/pyodide-sympy.json')
# Where the host SymPy is pinned or written out for authors: (file, pattern,
# the text it must capture). Requirement files capture the whole specifier.
SPEC = r'^\s*sympy\b\s*([^#\n]*?)\s*(?:#.*)?$'
PINS = [
    ('requirements.txt', SPEC, '=={}'),
    ('requirements-dev.txt', SPEC, '=={}'),
    ('README.md', r"pip install 'sympy([^']*)'", '=={}'),
    ('docs/authoring.qmd', r"pip install 'sympy([^']*)'", '=={}'),
    ('docs/authoring.qmd', r'SymPy (\d+(?:\.\d+)+), Quarto', '{}'),
    ('docs/native-authoring.qmd', r'`sympy(==[^`]*)`', '=={}'),
    ('docs/native-authoring.qmd', r'bundles SymPy (\d+(?:\.\d+)+)', '{}'),
]


def record_path(libs):
    candidates = [libs] if libs else [os.environ.get('CTM_LIBS_EXTENSION'), ROOT / '_ctm-libs-source', ROOT / '_extensions/ctm-libs']
    for base in filter(None, candidates):
        base = Path(base)
        for path in (base / RECORD, base / '_extensions/ctm-libs' / RECORD):
            if path.is_file():
                return path
    if libs:
        raise SystemExit(f'{libs} has no {RECORD} or _extensions/ctm-libs/{RECORD}: this ctm-libs predates the record '
                         '(scripts/sync-pyodide-sympy.py); pin a ctm-libs commit that has it in .github/pins.json')
    raise SystemExit('No ctm-libs found: pass --libs with a ctm-libs checkout or installed extension')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--libs', help='a ctm-libs checkout or installed _extensions/ctm-libs')
    args = parser.parse_args()
    source = record_path(args.libs)
    record = json.loads(source.read_text())
    pyodide, sympy = record.get('pyodide'), record.get('sympy')
    if not (isinstance(pyodide, str) and isinstance(sympy, str)):
        raise SystemExit(f'{source} records no Pyodide and SymPy versions')
    found, problems = [], []
    for name, pattern, expected in PINS:
        path = ROOT / name
        if not path.exists():
            continue
        specs = re.findall(pattern, path.read_text(), re.M | re.I)
        if name == 'requirements.txt' and len(specs) != 1:
            problems.append(f'requirements.txt must pin SymPy once, as sympy=={sympy} (found {len(specs)} SymPy lines)')
        for spec in specs:
            found.append(name)
            if spec != expected.format(sympy):
                problems.append(f'{name} has sympy{spec}' if expected.startswith('==') else f'{name} names SymPy {spec}')
    if problems:
        raise SystemExit(
            'Host SymPy differs from the SymPy of ctm-libs\' Pyodide\n  '
            + '\n  '.join(problems)
            + f'\nctm-libs\' Pyodide {pyodide} bundles SymPy {sympy} ({source}).\n'
            f'Set sympy=={sympy} there. Native PythonChecker questions built with another host SymPy record it and '
            'fail in the browser with python-checker-identity. To move SymPy, move the Pyodide pin in ctm-libs '
            '(scripts/sync-pyodide-sympy.py) and repin ctm-libs here with the new version.')
    print(f'Host SymPy {sympy} = SymPy of ctm-libs\' Pyodide {pyodide} ({source}); checked: {", ".join(dict.fromkeys(found))}')


if __name__ == '__main__':
    main()
