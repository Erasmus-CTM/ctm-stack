#!/usr/bin/env python3
"""Reproduce the pinned upstream audit without modifying upstream sources.

Requires Python with pytest, Node, and either PHP (intl/mbstring) or an existing
PHP Docker image. Docker runs offline. PHP is used exclusively as a test oracle.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from adversarial import corpus

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PIN = json.loads((Path(__file__).resolve().parents[3]/'_extensions/ctm-stack/native/stack-pin.json').read_text())['revision']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stack-source', required=True, type=Path)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--docker-image', help='Existing image with PHP intl and mbstring; no image pull')
    args = parser.parse_args()
    source, runtime, output = (p.resolve() for p in (args.stack_source, args.runtime, args.output))
    revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != PIN:
        raise ValueError('Use the audited STACK pin '+PIN)
    subprocess.run(['git', '-C', str(source), 'diff', '--exit-code', PIN, '--',
        'stack', 'api/emulation', 'lang/en/qtype_stack.php'], check=True, stdout=subprocess.DEVNULL)
    output.mkdir(parents=True, exist_ok=True)
    input_data = corpus()
    input_file = output/'input.json'
    input_file.write_text(json.dumps(input_data, indent=2)+'\n')
    with tempfile.TemporaryDirectory(prefix='oracle-', dir=output) as scratch:
        work = Path(scratch)
        (work/'run').mkdir()
        config = (source/'api/config_sample.txt').read_text()
        # Follow upstream API bootstrap with local paths, no server/database.
        for name, value in {'dirroot': str(source/'api'), 'dataroot': str(work/'data')}.items():
            config = re.sub(r'\$CFG->'+name+r'\s*=.*?;',
                lambda match: '$CFG->'+name+' = '+json.dumps(value)+';', config)
        (work/'config.php').write_text(config)
        environment = os.environ.copy()
        if args.docker_image:
            for key in ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH'):
                environment.pop(key, None)
            command = ['docker', '--host=unix:///var/run/docker.sock', 'run', '--rm', '-i',
                '--pull=never', '--network', 'none']
            for folder, readonly in ((source, True), (REPO, True), (output, False)):
                command += ['--mount', 'type=bind,src='+str(folder)+',dst='+str(folder)+(',readonly' if readonly else '')]
            command += ['--workdir', str(work/'run'), args.docker_image, 'php']
        else:
            command = ['php']
        command += [str(HERE/'adversarial.php'), str(source)]

        def oracle(payload):
            return json.loads(subprocess.check_output(command, input=json.dumps(payload).encode(),
                cwd=work/'run', env=environment, timeout=120))

        compiled = oracle(input_data)
        compiled_file = output/'compiled.json'
        compiled_file.write_text(json.dumps(compiled, indent=2)+'\n')
        native_file = output/'native.json'
        subprocess.run(['node', str(HERE/'native-audit.mjs'), str(runtime), str(input_file),
            str(compiled_file), str(native_file)], check=True, timeout=1800)
        native = json.loads(native_file.read_text())
        restored = oracle({'replacements': native['replacements']})
        (output/'restored.json').write_text(json.dumps(restored, indent=2)+'\n')
    scores = compiled['scores']
    summary = {'schema': 1, 'date': '2026-10-27', 'stackRevision': revision,
        'php': compiled['php'], 'node': subprocess.check_output(['node', '--version'], text=True).strip(),
        'runtime': native['identity'], 'graphs': len(compiled['graphs']),
        'graphVerdicts': len(native['cases']), 'graphMismatches': sum(not r['matched'] for r in native['cases']),
        'scoreSamples': len(scores), 'changedScores': sum(abs(r['raw']-r['actual']) > 1e-12 for r in scores),
        'largestScoreChange': max(abs(r['raw']-r['actual']) for r in scores),
        'questionTestRoundingMismatches': sum(abs(r['testActual']-r['testExpected']) > 1e-5 for r in scores),
        'mathPaint': compiled['paint'], 'renderedCASText': restored['castext'], 'rawFiles': []}
    for name in ('input.json', 'compiled.json', 'native.json', 'restored.json'):
        file = output/name
        packed = gzip.compress(file.read_bytes(), mtime=0)
        (output/(name+'.gz')).write_bytes(packed)
        summary['rawFiles'].append({'file': name+'.gz', 'sha256': hashlib.sha256(packed).hexdigest()})
    (output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps({k: summary[k] for k in ('graphVerdicts', 'graphMismatches', 'changedScores',
        'questionTestRoundingMismatches')}, indent=2))
    if summary['graphMismatches']:
        raise SystemExit('Graph oracle disagrees with independent reference')


if __name__ == '__main__':
    main()
