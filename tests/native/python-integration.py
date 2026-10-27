#!/usr/bin/env python3
"""Real native preparation, Python leaves, block checkers and assigned identities."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET
import runpy

ROOT=Path(__file__).resolve().parents[2]
CHECKER='''counter=0
def check(response, symbols):
    global counter
    counter+=1
    assert counter==1, 'checker namespace was reused'
    assert response['variant']['id'].startswith('seed=')
    if response['variant'].get('hash') is not None:
        assert len(response['variant']['hash'])==16
    ans=response['answers']['ans']
    if ans==0:
        return {'valid':False,'feedback':'Use a nonzero answer.'}
    if ans==666:
        raise ValueError('controlled checker error')
    if ans==999:
        while True: pass
    ratio=ans/response['variables']['d']
    return {'score':1 if ratio.is_integer and ratio.is_positive else 0,'feedback':'<plain Python feedback> QMCHAR'}
'''
AUTHORED='''- name: teacher
  answers: {ans: d}
  expect: correct
- name: invalid
  answers: {ans: 'raw("load(x)")'}
  expect: invalid
- name: wrong
  answers: {ans: d+1}
  expect: wrong
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkers',required=True,type=Path)
    parser.add_argument('--runtime',required=True,type=Path)
    parser.add_argument('--sources',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();folder=args.checkers.resolve()
    descriptor=json.loads((folder/'checkers.json').read_text())
    sys.path[:0]=[str(folder/descriptor['wheel']),str(folder/descriptor['parts']['stack']['wheel']),
        str(folder/'native-authoring'),str(ROOT/'_extensions/ctm-stack')]
    from ctm_stack_native import NativeBackend
    from ctm_variants.stack_component import parse_source,request
    report={'schema':1,'passed':False,'cases':[]}
    with tempfile.TemporaryDirectory(prefix='native-python-proof-') as directory:
        matrices=runpy.run_path(str(Path(__file__).with_name('python-fixtures.py')))['matrices'](directory)
        sources=[(args.sources/'python-checker.xml',{'checker':CHECKER,'tests':AUTHORED}),
                 (args.sources/'determinant-one.xml',{}),*[(path,{}) for path in matrices]]
        for source,options in sources:
            file=source.name;title=ET.parse(source).findtext('question/name/text')
            with NativeBackend(runtime_root=args.runtime,checker_folder=folder) as backend:
                question=backend.load_question(source,title,options)
                record=backend.seed_record(question,1)
                assert record['tests']['passed'] and record['tests']['teacher']['score']==1
                if options.get('checker'):
                    assert '&lt;plain Python feedback&gt; QMCHAR' in record['tests']['teacher']['prts']['prt1']['feedback']
                identity={'n':7,'id':record['id'],'hash':record['hash']}
                assigned=backend.seed_record(question,1,identity=identity)
                assert assigned['hash']==record['hash']
                assert all(assigned['data']['plan'][key]==value for key,value in identity.items())
                report['cases'].append({'file':file,'passed':True,'tests':len(record['tests']['qtests']['results']),
                    'assignedIdentity':identity,'teacher':record['tests']['teacher']})
        # Checker-only cards have no native PRT functions. Their partial mark
        # is numeric, unlike the Boolean predicate used by an XML Python node.
        tree=ET.parse(args.sources/'python-checker.xml');q=tree.getroot().find('question')
        for node in [*q.findall('prt'),*q.findall('qtest')]:q.remove(node)
        q.find('questiontext/text').text='Answer {@d@}: [[input:ans]] [[validation:ans]] [[feedback:checker]]'
        source=Path(directory)/'block.xml';tree.write(source,encoding='unicode')
        block='''def check(response, symbols):
    ans=response['answers']['ans']; d=response['variables']['d']
    if ans==0: return {'valid':False,'feedback':'Nonzero required'}
    return {'score':1 if ans==d else .5 if ans==d+1 else 0,'show_score':False}
'''
        tests='''- name: teacher
  answers: {ans: d}
  expect: correct
- name: partial
  answers: {ans: d+1}
  expect: partial
  score: 0.5
- name: wrong
  answers: {ans: -d}
  expect: wrong
- name: invalid
  answers: {ans: 0}
  expect: invalid
'''
        with NativeBackend(runtime_root=args.runtime,checker_folder=folder) as backend:
            question=backend.load_question(source,q.findtext('name/text'),{'checker':block,'checker-value':'2','tests':tests})
            record=backend.seed_record(question,1)
            assert record['tests']['passed'] and len(record['tests']['qtests']['results'])==4
            report['cases'].append({'file':'checker-only','passed':True,'tests':4})
        # Exercise the actual shared lease/approval path, including the final
        # numbered identity. A checker that only passes unnumbered proposals
        # must not be approved or leave a manifest behind.
        source=Path(directory)/'review.xml'
        tree=ET.parse(args.sources/'python-checker.xml');tree.write(source,encoding='unicode')
        title=tree.findtext('question/name/text')
        code=CHECKER+"\noriginal=check\ndef check(response,symbols):\n    assert response['variant']['n'] is None, 'numbered checker must fail'\n    return original(response,symbols)\n"
        authored='\n'.join(['#| label: native-python-review','#| file: review.xml','#| question: '+title,
            '#| cas: maxima','#| variants: 1','#| checker: |',*['#|   '+line for line in code.splitlines()]])
        project=Path(directory);(project/'page.qmd').write_text('```{.stack-question}\n'+authored+'\n```\n')
        options,body=parse_source(authored)
        payload=dict(version=1,source=authored,options=options,question=body,label='native-python-review',
            projectRoot=str(project),file='page.qmd',manifest='_variants/native-python-review.yml')
        def resolve(**changes):
            return request(dict(payload,**changes),backend=NativeBackend(runtime_root=args.runtime,checker_folder=folder))
        generated=resolve(action='generate',renderMode='review',baseHash=None)
        stored=(project/payload['manifest']).read_bytes()
        try:
            resolve(action='decide-many',baseHash=generated['baseHash'],decisions=[
                {'id':r['id'],'hash':r['hash'],'status':'approved'} for r in generated['records']])
        except ValueError as error:
            assert 'numbered checker must fail' in str(error),str(error)
        else:raise AssertionError('A checker that fails its assigned identity was approved')
        assert (project/payload['manifest']).read_bytes()==stored
        report['approvalIdentityFailure']={'passed':True,'manifestUnchanged':True}
    report['passed']=True
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':True,'cases':[{k:v for k,v in case.items() if k!='teacher'} for case in report['cases']]},indent=2))


if __name__=='__main__':main()
