#!/usr/bin/env python3
"""Actual Maxima producer through common leased review/approval, without SymPy.

Uses the installed checker wheels and native-authoring distribution. The caller
provides the same runtime-v3 package that will be copied into the HTML output.
"""
import argparse
import importlib.abc
import json
import os
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]


class NoSymPy(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname=='sympy' or fullname.startswith('sympy.'):
            raise AssertionError('Native preparation tried to import '+fullname)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkers',type=Path,required=True)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--xml',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    folder=args.checkers.resolve()
    descriptor=json.loads((folder/'checkers.json').read_text())
    sys.path[:0]=[str(folder/descriptor['wheel']),str(folder/descriptor['parts']['stack']['wheel']),
        str(folder/'native-authoring'),str(ROOT/'_extensions/ctm-stack')]
    sys.meta_path.insert(0,NoSymPy())
    from ctm_variants.stack_component import parse_source,request
    from ctm_stack_native import NativeBackend
    checks=[]
    with tempfile.TemporaryDirectory(prefix='ctm-maxima-producer-') as directory:
        project=Path(directory)
        tree=ET.parse(args.xml)
        question=tree.getroot().find('question')
        note=question.find('questionnote')
        if note is None:note=ET.SubElement(question,'questionnote')
        text=note.find('text')
        if text is None:text=ET.SubElement(note,'text')
        text.text='a={@a@}; b={@b@}'
        tree.write(project/'question.xml',encoding='unicode')
        source='\n'.join(['#| label: native-review','#| file: question.xml',
            '#| question: '+question.findtext('name/text'),'#| cas: maxima','#| variants: 2'])
        (project/'page.qmd').write_text('```{.stack-question}\n'+source+'\n```\n')
        options,body=parse_source(source)
        payload=dict(version=1,source=source,options=options,question=body,label='native-review',
            projectRoot=str(project),file='page.qmd',manifest='_variants/native-review.yml')

        def resolve(**changes):
            return request(dict(payload,**changes),backend=NativeBackend(runtime_root=args.runtime,
                checker_folder=folder,cache=project/'cache'))

        try:resolve()
        except ValueError as error:
            assert 'at least one current approved' in str(error),str(error)
        else:raise AssertionError('Required approval was bypassed')
        checks.append('required approval blocks publication')
        generated=resolve(action='generate',renderMode='review',baseHash=None)
        assert len(generated['records'])==2
        assert all(r['tests']['passed'] for r in generated['records'])
        assert all(p['tape']['backend']=='maxima' for p in generated['manifest']['proposals'])
        checks.append('two native candidates and XML tests retained with Maxima replay tapes')
        decisions=[{'id':r['id'],'hash':r['hash'],'status':'approved'} for r in generated['records']]
        approved=resolve(action='decide-many',baseHash=generated['baseHash'],decisions=decisions)
        assert [r['n'] for r in approved['payload']['variants']]==[1,2]
        assert all(not r['proposal'] for r in approved['payload']['variants'])
        checks.append('approved candidates receive stable shared numbering')
        manifest=project/payload['manifest'];stored=manifest.read_bytes()
        xml=project/'question.xml'
        xml.write_text(xml.read_text().replace('Expand and collect like terms:','Please expand and collect like terms:'))
        refreshed=resolve()
        assert [r['hash'] for r in refreshed['payload']['variants']]==[r['hash'] for r in approved['payload']['variants']]
        assert 'Please expand' in refreshed['payload']['variants'][0]['display']['question_html']
        assert manifest.read_bytes()==stored
        checks.append('prose refresh preserves approval, numbering and immutable manifest')
        try:resolve(action='generate',renderMode='review',baseHash=None)
        except ValueError as error:assert 'lease changed' in str(error),str(error)
        else:raise AssertionError('Stale history lease accepted')
        checks.append('stale manifest lease rejected')
        # This real mathematical edit changes the prompt and teacher values but
        # keeps the authored question tests internally valid.
        xml.write_text(xml.read_text().replace('rand(4)+2','rand(4)+12'))
        try:resolve()
        except ValueError as error:assert 'at least one current approved' in str(error),str(error)
        else:raise AssertionError('Mathematical edit reused old approval')
        checks.append('mathematical edit requires fresh approval')
        assert not any(name=='sympy' or name.startswith('sympy.') for name in sys.modules)
        checks.append('SymPy import blocked throughout native authoring')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'schema':1,'passed':True,'checks':checks},indent=2)+'\n')
    print(json.dumps({'passed':True,'checks':checks},indent=2))


if __name__=='__main__':main()
