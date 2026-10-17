"""Compare cold/image observations, diagnostics and wall times without waivers."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from native_compliance.maxima_runner import (run_native, run_standalone_probe, _unavailable,
                                            make_batch, _command, parse_output, NativeProtocolError)
from native_compliance import native_image

def image_digest(directory):
    return native_image.digest(Path(directory) / 'stack-gcl')


def verify_sample_order(cases, source, image):
    families = {}
    for case in cases:
        if _unavailable(case) is None:
            families.setdefault(case['test'], case)
    sample = list(families.values())
    fragile = next((c for c in cases if _unavailable(c) is None and 'matrix(' in c['student']+c['teacher']), None)
    if fragile and fragile not in sample:
        sample.append(fragile)
    serial = run_native(sample, source, image=image, jobs=1)['observations']
    reverse = run_native(list(reversed(sample)), source, image=image, jobs=4)['observations']
    return {'passed': {r['case_id']:r for r in serial} == {r['case_id']:r for r in reverse},
            'serial': serial, 'reversed_parallel': reverse}


def verify_state_isolation(source, image):
    """Trusted diagnostic batches, separate from the imported case inventory."""
    reports = {}
    for mode in ('cold', 'image'):
        reports[mode] = {}
        for state in ('dirty', 'clean'):
            with tempfile.TemporaryDirectory(prefix='stack-image-state-') as directory:
                home = Path(directory)
                batch = home / 'state.mac'
                text = make_batch(source.resolve(), [], home, 0, preloaded=mode == 'image')
                mutation = ('assume(stack_image_probe_z>0)$\ndeclare(stack_image_probe_n,integer)$\n'
                            'stack_image_probe_binding:73$\n') if state == 'dirty' else ''
                diagnostic = ('print(sconcat("STACKIMAGE-STATE|",stackjson_stringify(['
                              'string(facts(stack_image_probe_z)),string(featurep(stack_image_probe_n,integer)),'
                              'string(stack_image_probe_binding)])))$\n')
                text = text.replace('print("STACKNATIVE-END|0|0")$', mutation+diagnostic+'print("STACKNATIVE-END|0|0")$')
                batch.write_text(text)
                argv = native_image.command(image, batch) if mode == 'image' else ['maxima', '--very-quiet', f'--batch={batch}']
                output = _command(argv, 300, **({'env': native_image.environment(home)} if mode == 'image' else {}))
                parse_output(output, [], 0)
                records = [line.removeprefix('STACKIMAGE-STATE|') for line in output.splitlines() if line.startswith('STACKIMAGE-STATE|')]
                if len(records) != 1:
                    raise NativeProtocolError('Missing or duplicate native state-isolation diagnostic')
                reports[mode][state] = json.loads(records[0])
    clean = ['[]', 'false', 'stack_image_probe_binding']
    passed = (reports['cold'] == reports['image'] and reports['image']['clean'] == clean and
              reports['image']['dirty'][0] != '[]' and reports['image']['dirty'][1:] == ['true', '73'])
    return {'passed': passed, 'observations': reports}

def isolation_cases():
    def case(name, student, teacher):
        return {'id': hashlib.sha256(name.encode()).hexdigest()+'-1', 'test': 'AlgEquiv',
                'student': student, 'teacher': teacher, 'options': ''}
    return [case('mutate assumption', 'block([],assume(stack_image_probe_z>0),stack_image_probe_z)', 'stack_image_probe_z'),
            case('observe clean assumption', 'abs(stack_image_probe_z)', 'stack_image_probe_z')]

def compare(cases, source, image, full=False):
    digest_before = image_digest(image)
    selected = [c for c in cases if _unavailable(c) is None]
    if full:
        selected = cases
    else:
        # First/middle/last of each family, plus every matrix fixture.
        families = {}
        for row in selected:
            families.setdefault(row['test'], []).append(row)
        ids = {r['id'] for rows in families.values() for r in (rows[0], rows[len(rows)//2], rows[-1])}
        selected = [r for r in selected if r['id'] in ids or 'matrix(' in r['student'] + r['teacher']]
    reports, times = {}, {}
    for mode in ('cold', 'image'):
        started = time.monotonic()
        reports[mode] = run_native(selected, source, image=image if mode == 'image' else None)
        times[mode] = time.monotonic() - started
    probes = {mode: run_standalone_probe(source, image=image if mode == 'image' else None)['probe']
              for mode in ('cold', 'image')}
    isolation = {mode: run_native(isolation_cases(), source, jobs=1,
                                 image=image if mode == 'image' else None)['observations']
                 for mode in ('cold', 'image')}
    order = verify_sample_order(cases, source, image)
    state = verify_state_isolation(source, image)
    digest_after = image_digest(image)
    equal = (reports['cold']['observations'] == reports['image']['observations'] and
             reports['cold']['summary'] == reports['image']['summary'] and
             reports['cold']['metadata']['native_scope_sha256'] == reports['image']['metadata']['native_scope_sha256'] and
             reports['cold']['metadata']['loader_probe'] == reports['image']['metadata']['loader_probe'] and
             probes['cold'] == probes['image'] and isolation['cold'] == isolation['image'] and
             [row.get('correct') for row in isolation['image']] == [True, False] and
             order['passed'] and state['passed'] and digest_before == digest_after)
    return {'passed': equal, 'full': full, 'cases': len(selected),
            'runnable_cases': sum(_unavailable(c) is None for c in selected), 'wall_seconds': times,
            'speedup': times['cold'] / times['image'], 'reports': reports, 'standalone_probes': probes,
            'isolation_probes': isolation, 'state_isolation': state, 'order_parallelism': order,
            'image_sha256_before': digest_before, 'image_sha256_after': digest_after}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stack-source', type=Path, required=True)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--full', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('test-results/compliance/native-image-benchmark.json'))
    args = parser.parse_args()
    fixture_bytes = Path('tests/native_compliance/fixtures.json').read_bytes()
    fixture = json.loads(fixture_bytes)
    report = compare(fixture['cases'], args.stack_source, args.image, args.full)
    report['fixture_sha256'] = hashlib.sha256(fixture_bytes).hexdigest()
    report['code_sha'] = os.environ.get('GITHUB_SHA')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print({k:v for k,v in report.items() if k not in {'reports', 'standalone_probes', 'isolation_probes',
                                                   'state_isolation', 'order_parallelism'}})
    raise SystemExit(0 if report['passed'] else 1)
