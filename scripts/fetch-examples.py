#!/usr/bin/env python3
"""Copy the STACK example questions of ctm-checkers into questions/ (pre-render).

The STACK question XML has its one home in ctm-checkers (`examples/stack/`,
consolidation step 2). This site shows it from the ctm-checkers commit it
builds against: CI checks that commit out as `_ctm-checkers-source/`
(.github/actions/ctm-dependencies); elsewhere set CTM_CHECKERS_SOURCE to a
ctm-checkers checkout. `questions/` is git-ignored and replaced on every run,
without `probes/` and `supplement/` (inputs of ctm-checkers' golden tables only).
`questions/SOURCE.json` names the commit it came from.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'questions'
SKIP = {'probes', 'supplement'}


def source() -> Path:
    configured = os.environ.get('CTM_CHECKERS_SOURCE')
    folder = Path(configured) if configured else ROOT / '_ctm-checkers-source'
    if not (folder / 'examples/stack').is_dir():
        pin = json.loads((ROOT / '.github/pins.json').read_text())['ctm-checkers']['commit']
        sys.exit('stack-sympy shows the STACK examples of ctm-checkers, which were not found in '
                 f'{folder}. Check out Erasmus-CTM/ctm-checkers at {pin} (.github/pins.json) '
                 'there, or set CTM_CHECKERS_SOURCE to a ctm-checkers checkout.')
    return folder


def commit(folder: Path) -> str | None:
    result = subprocess.run(['git', '-C', str(folder), 'rev-parse', 'HEAD'],
                            capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def main() -> None:
    folder = source()
    shutil.rmtree(TARGET, ignore_errors=True)
    shutil.copytree(folder / 'examples/stack', TARGET,
                    ignore=lambda directory, names: SKIP & set(names)
                    if Path(directory) == folder / 'examples/stack' else ())
    (TARGET / 'SOURCE.json').write_text(json.dumps(
        {'repository': 'Erasmus-CTM/ctm-checkers', 'path': 'examples/stack',
         'commit': commit(folder)}, indent=1) + '\n')


if __name__ == '__main__':
    main()
