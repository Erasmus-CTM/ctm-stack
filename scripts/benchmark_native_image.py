"""Compare cold/image observations, diagnostics and wall times without waivers."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
from native_compliance.maxima_runner import run_native, run_standalone_probe, _unavailable

def isolation_cases():
    def case(name, student, teacher):
        return {'id': hashlib.sha256(name.encode()).hexdigest()+'-1', 'test': 'AlgEquiv',
                'student': student, 'teacher': teacher, 'options': ''}
    return [case('mutate assumption', 'block([],assume(stack_image_probe_z>0),stack_image_probe_z)', 'stack_image_probe_z'),
            case('observe clean assumption', 'abs(stack_image_probe_z)', 'stack_image_probe_z')]

def compare(cases, source, image, full=False):
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
    equal = (reports['cold']['observations'] == reports['image']['observations'] and
             reports['cold']['summary'] == reports['image']['summary'] and
             reports['cold']['metadata']['native_scope_sha256'] == reports['image']['metadata']['native_scope_sha256'] and
             reports['cold']['metadata']['loader_probe'] == reports['image']['metadata']['loader_probe'] and
             probes['cold'] == probes['image'] and isolation['cold'] == isolation['image'] and
             [row.get('correct') for row in isolation['image']] == [True, False])
    return {'passed': equal, 'full': full, 'cases': len(selected),
            'runnable_cases': sum(_unavailable(c) is None for c in selected), 'wall_seconds': times,
            'speedup': times['cold'] / times['image'], 'reports': reports, 'standalone_probes': probes,
            'isolation_probes': isolation}

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
    print({k:v for k,v in report.items() if k not in {'reports', 'standalone_probes', 'isolation_probes'}})
    raise SystemExit(0 if report['passed'] else 1)
