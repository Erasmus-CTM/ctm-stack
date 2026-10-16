"""Port discoveries have explicit expectations and never alter legacy counts."""
import hashlib
import json
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from native_compliance.port_contract import load_fixture, matches, python_status, assemble
from native_compliance.python_runner import evaluate_case
from native_compliance.report import port_regressions

CASES = load_fixture(ROOT/'tests/port_regressions/fixtures.json')


@pytest.mark.parametrize('case',CASES,ids=lambda case:case['id'])
def test_project_regression_contract(case):
    assert python_status(case,evaluate_case(case)) in {'pass','boundary_pass','known_defect'}


def test_boundary_agreement_is_not_mathematical_coverage():
    case = next(c for c in CASES if c['expected']['kind']=='unsupported')
    observed = evaluate_case(case)
    report = assemble([case],[observed],parity={'cases':[{'id':case['id'],'match':True}]})
    assert report['summary']['python']=={'boundary_pass':1}
    assert report['summary']['native']=={'outside_port_scope':1}
    assert report['passed']
    assert not matches({'kind':'timeout'}, {'kind':'unsupported'})


def test_stale_exception_and_changed_observation_fail():
    case = next(c for c in CASES if 'known_defect' in c)
    assert python_status(case,case['expected'])=='unexpected_stale_exception'
    assert python_status(case,{'kind':'result','valid':True,'correct':False,'cas_valid':False})=='unexpected'


def test_missing_runner_is_incomplete_and_wrong_provenance_is_unavailable(tmp_path):
    case = CASES[0]
    report = assemble([case],[evaluate_case(case)])
    assert not report['passed']
    assert report['summary']['native']=={'unavailable':1}
    assert report['summary']['parity']=={'unavailable':1}
    path=tmp_path/'old.json'
    path.write_text(json.dumps({**report,'suite':'project_port_regressions','provenance':{}}))
    assert not port_regressions(path)['available']


def test_legacy_inventory_untouched_and_port_cases_have_origin():
    assert len(json.loads((ROOT/'tests/native_compliance/fixtures.json').read_text())['cases'])==2303
    assert len(CASES)>=40
    assert all(c['origin']['kind']=='project_regression' and c['reason'] for c in CASES)


def test_branch_convention_difference_is_case_pinned_and_cannot_silently_change():
    case = next(c for c in CASES if 'native_expected' in c)
    python = evaluate_case(case)
    native = {'observations':[{'case_id':case['id'],'status':'ok',**case['native_expected']}]}
    parity = {'cases':[{'id':case['id'],'match':True}]}
    report = assemble([case],[python],native,parity)
    assert report['passed'] and report['cases'][0]['native_status']=='branch_convention_difference'
    native['observations'][0]['correct'] = False
    assert not assemble([case],[python],native,parity)['passed']
