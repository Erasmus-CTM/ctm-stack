"""Portable, dependency-free contracts for project-owned regression results."""
from collections import Counter
import json
import re

def load_fixture(path):
    data = json.loads(path.read_text())
    if data.get('schema_version') != 1 or data.get('suite') != 'project_port_regressions':
        raise ValueError('Expected a project-owned v1 regression fixture')
    ids = set()
    for case in data['cases']:
        if not re.fullmatch(r'port-[a-z0-9-]+', case['id']) or case['id'] in ids:
            raise ValueError('Regression IDs must be unique and stable')
        ids.add(case['id'])
        if not case.get('reason') or not isinstance(case.get('origin'), dict):
            raise ValueError('Each regression requires a reason and origin')
        validate_expected(case['expected'])
        if 'known_defect' in case:
            validate_expected(case['known_defect']['observation'])
            if not case['known_defect'].get('reason'):
                raise ValueError('A known defect requires a case-specific reason')
        if 'native_expected' in case:
            if (set(case['native_expected']) != {'cas_valid','correct'}
                    or any(type(v) is not bool for v in case['native_expected'].values())
                    or not case.get('native_difference_reason')):
                raise ValueError('Native branch differences require explicit booleans and a traced reason')
            if case['native_expected'] == {k:case['expected'].get(k) for k in ('cas_valid','correct')}:
                raise ValueError('Native branch difference must differ from the port expectation')
        if case['native_scope'] and case['expected']['kind'] != 'result':
            raise ValueError('Native contracts require result expectations')
    if not ids:
        raise ValueError('Regression fixture cannot be empty')
    return data['cases']


def validate_expected(expected):
    if not isinstance(expected, dict) or expected.get('kind') not in {
            'result', 'unsupported', 'invalid_student', 'invalid_teacher', 'invalid_option'}:
        raise ValueError('Expected semantic result or explicit contract boundary')
    if expected['kind'] == 'result' and any(type(expected.get(k)) is not bool for k in ('valid','correct','cas_valid')):
        raise ValueError('Result contracts pin syntax validity, CAS applicability, and correctness')
    if set(expected) - {'kind','valid','correct','cas_valid'}:
        raise ValueError('Unknown expectation fields')


def matches(observed, expected):
    if not observed or observed.get('kind') in {'unexpected_exception','timeout'}:
        return False
    return all(observed.get(k, observed.get('valid') if k == 'cas_valid' else None) == v
               for k,v in expected.items())


def python_status(case, observed):
    known = case.get('known_defect')
    if known:
        if matches(observed, case['expected']):
            return 'unexpected_stale_exception'
        return 'known_defect' if matches(observed, known['observation']) else 'unexpected'
    if matches(observed, case['expected']):
        return 'boundary_pass' if case['expected']['kind'] != 'result' else 'pass'
    return 'unexpected'


def assemble(cases, python, native=None, parity=None, errors=None):
    pmap = {o['case_id']:o for o in python}
    nmap = {o['case_id']:o for o in (native or {}).get('observations',[])}
    bmap = {o['id']:o for o in (parity or {}).get('cases',[])}
    rows = []
    for case in cases:
        p,n,b = pmap.get(case['id']), nmap.get(case['id']), bmap.get(case['id'])
        status = python_status(case,p)
        native_status = 'outside_port_scope' if not case['native_scope'] else 'unavailable'
        if case['native_scope'] and n:
            desired = {'cas_valid':case['expected']['cas_valid'], 'correct':case['expected']['correct']}
            expected_native = case.get('native_expected',desired)
            if n.get('status') != 'ok' or not all(n.get(k)==v for k,v in expected_native.items()):
                native_status = 'unexpected'
            else:
                native_status = 'branch_convention_difference' if 'native_expected' in case else 'match_desired'
        rows.append({**case, 'python':p, 'native':n, 'parity':b,
                     'python_status':status, 'native_status':native_status,
                     'parity_status':'unavailable' if b is None else 'match' if b['match'] else 'unexpected'})
    summary = {key:dict(Counter(row[key+'_status'] for row in rows)) for key in ('python','native','parity')}
    passed = (not errors and all(not row['python_status'].startswith('unexpected')
              and row['native_status'] in {'match_desired','branch_convention_difference','outside_port_scope'}
              and row['parity_status']=='match' for row in rows))
    return {'schema_version':1,'suite':'project_port_regressions','passed':bool(passed),
            'cases':rows,'summary':summary,'errors':errors or {}}


