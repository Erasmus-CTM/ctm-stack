"""Project-owned regression contracts, independent of the legacy STACK inventory."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import sympy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / '_extensions/stack-sympy'))
from native_compliance.maxima_runner import INPUT_PREPARATION, STACK_SHA, run_native
from native_compliance.python_runner import classify_case
from run_compliance_python import isolated_case

FIXTURE = ROOT / 'tests/port_regressions/fixtures.json'
OUTPUT = ROOT / 'test-results/compliance/port-regressions.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


from native_compliance.port_contract import load_fixture, matches, python_status, assemble


def run(fixture, stack_source, maxima, output, browser):
    cases = load_fixture(fixture)
    from run_compliance_pyodide import validate_bundle
    bundle_hash = validate_bundle()
    observations = []
    for case in cases:
        observed = isolated_case(case, timeout=10)
        observed['scope'] = classify_case(case)['kind']
        observations.append(observed)
    python = {'schema_version':1,'engine':'python','passed':all(not python_status(c,o).startswith('unexpected') for c,o in zip(cases,observations)),
              'metadata':{'fixture_sha256':digest(fixture),'sympy_version':sympy.__version__},'observations':observations}
    output.parent.mkdir(parents=True,exist_ok=True)
    python_path = output.with_name('port-python.json')
    python_path.write_text(json.dumps(python,indent=2)+'\n')
    native = parity = None
    errors = {}
    try:
        converted, id_map = [], {}
        for case in cases:
            if case['native_scope']:
                native_id = hashlib.sha256(case['id'].encode()).hexdigest()+'-1'
                converted.append({**case,'id':native_id})
                id_map[native_id] = case['id']
        native = run_native(converted,stack_source,maxima,jobs=4,timeout=60)
        for row in native['observations']:
            row['case_id'] = id_map[row['case_id']]
    except Exception as exc:
        errors['native'] = f'{type(exc).__name__}: {exc}'
    if browser:
        try:
            from run_compliance_pyodide import run as run_parity
            parity = run_parity(fixtures=fixture,python_report=python_path,init_timeout_ms=180000,case_timeout_ms=30000)
        except Exception as exc:
            errors['parity'] = f'{type(exc).__name__}: {exc}'
    else:
        errors['parity'] = 'Browser parity intentionally not run locally; CI requires it'
    report = assemble(cases,observations,native,parity,errors)
    report['provenance'] = {'fixture_sha256':digest(fixture),'source_bundle_sha256':bundle_hash,
                            'stack_sha':STACK_SHA,'input_preparation':INPUT_PREPARATION,
                            'sympy_version':sympy.__version__,'python_version':sys.version.split()[0]}
    report['runners'] = {'native':(native or {}).get('metadata'),
                         'parity':{k:v for k,v in (parity or {}).items() if k not in {'cases'}}}
    output.write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,default=FIXTURE)
    parser.add_argument('--stack-source',type=Path,required=True)
    parser.add_argument('--maxima',default='maxima')
    parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--without-browser',action='store_true',help='Local diagnostic only; overall report remains incomplete')
    args = parser.parse_args()
    report = run(args.fixture,args.stack_source,args.maxima,args.output,not args.without_browser)
    print('Port regressions:',report['summary'],'errors:',report['errors'])
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
