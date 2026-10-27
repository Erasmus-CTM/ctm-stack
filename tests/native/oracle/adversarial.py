#!/usr/bin/env python3
"""Prepare a deterministic upstream audit; PHP remains a test oracle only.

Run with the project test environment (pytest is used by the independent
reference module). Emits input for adversarial.php and native-audit.mjs.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import random
import sys

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('prt_reference', HERE.parent/'test_prt_compiler.py')
reference = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = reference
spec.loader.exec_module(reference)
prt = reference.prt


def corpus():
    rng = random.Random(20261027)
    graphs, cases = [], []
    for graph in range(120):
        count = rng.randrange(2, 7)
        nodes, encoded = [], []
        for index in range(count):
            targets = [str(n) for n in range(index+1, count)]+[None]
            following = str(index+1) if index+1 < count else None
            alternative = rng.choice(targets)
            branches = [prt.Branch(rng.choice(['=', '+', '-', '*']),
                rng.choice([0, .1, .2, .333, .5, .618, .999, 1, 1.2, -.2]),
                target, str(index)+side, None)
                for target, side in [(following, 'T'), (alternative, 'F')]]
            nodes.append(prt.Decision(str(index), prt.NativeTest('AlgEquiv', str(index),
                '1', '', '', False, True, False), *branches, False))
            encoded.append({side: {'mode': branch.mode, 'score': branch.score,
                'next': branch.next_node, 'note': branch.note}
                for side, branch in zip(('true', 'false'), branches)})
        tree = prt.ResponseTree('audit', tuple(nodes), (), (), None, True,
            rng.choice([0, .1, .333, .618, 1.2]))
        graphs.append({'id': graph, 'nodes': encoded, 'penalty': tree.penalty})
        for bits in range(1 << count):
            verdicts = [bool(bits & (1 << n)) for n in range(count)]
            cases.append({'id': f'{graph}/{bits}', 'graph': graph,
                'verdicts': verdicts, 'expected': reference.expected(tree, verdicts)})
    return {'texts': {
        'marker-literal': 'A sufficiently long static prefix {@x@} literal //CT2S0//',
        'marker-control': 'A sufficiently long static prefix {@x@} literal KEEP',
        'math-close': r'\({@x@}\) outside {@x@}',
        'dollar-close': '$ {@x@} $ outside {@x@}',
        'unicode': 'æøå 😀 {@x@} æøå 😀',
    }, 'paint': [
        {'id': 'html-environment-control', 'format': 1,
         'source': r'\begin{equation}{@1@}\end{equation} outside {@2@}', 'expected': [True, False]},
        {'id': 'markdown-unescaped-control', 'format': 4,
         'source': r'\\begin{equation}{@1@}\\end{equation} outside {@2@}', 'expected': [True, False]},
        {'id': 'markdown-escaped-open-brace', 'format': 4,
         'source': r'\\begin\{equation}{@1@}\\end\{equation} outside {@2@}', 'expected': [True, False]},
        {'id': 'markdown-escaped-both-braces', 'format': 4,
         'source': r'\\begin\{equation\}{@1@}\\end\{equation\} outside {@2@}', 'expected': [True, False]},
    ], 'graphs': graphs, 'cases': cases}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(corpus(), indent=2)+'\n')
