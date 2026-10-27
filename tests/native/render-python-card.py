#!/usr/bin/env python3
"""Build real native/Python and ordinary native cards for browser acceptance."""
import argparse
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('libs','checkers','runtime','sources','output'):parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args();project=args.output.resolve()
    if project.exists():raise ValueError('Choose a fresh standalone test project')
    for source,name in [(ROOT/'_extensions/ctm-stack','ctm-stack'),(args.libs,'ctm-libs'),(args.checkers,'ctm-checkers')]:
        shutil.copytree(source,project/'_extensions'/name)
    for file in ['python-checker.xml','polynomial-expansion.xml']:shutil.copyfile(args.sources/file,project/file)
    tree=ET.parse(project/'python-checker.xml');q=tree.getroot().find('question')
    note=ET.SubElement(q,'questionnote');ET.SubElement(note,'text').text='d={@d@}'
    tree.write(project/'python-checker.xml',encoding='unicode')
    matrix=runpy.run_path(str(Path(__file__).with_name('python-fixtures.py')))['matrices'](project)[0]
    specification=runpy.run_path(str(Path(__file__).with_name('python-integration.py')))
    def card(label,file,title,checker=None,tests=None,count=1,cas='maxima'):
        lines=['```{.stack-question}','#| label: '+label,'#| file: '+file,'#| question: '+title,
            '#| cas: '+cas,'#| variants: '+str(count),'#| review: true']
        for key,value in [('checker',checker),('tests',tests)]:
            if value:lines+=['#| '+key+': |',*['#|   '+line for line in value.splitlines()]]
        return '\n'.join([*lines,'```'])
    cards=[card('plain-native','polynomial-expansion.xml','Expand a product (form-sensitive)'),
        card('native-python','python-checker.xml',q.findtext('name/text'),specification['CHECKER'],specification['AUTHORED'],2),
        card('native-basis',matrix.name,'Native nullspace basis'),
        card('sympy-control','polynomial-expansion.xml','Expand a product (form-sensitive)',cas='sympy')]
    (project/'_quarto.yml').write_text('project:\n  type: default\nformat: html\nfilters:\n  - ctm-stack\nstack:\n  stop-after: 1\n')
    (project/'index.qmd').write_text('---\ntitle: Native PythonChecker acceptance\n---\n\n'+'\n\n'.join(cards)+'\n')
    environment={**os.environ,'CTM_COMPONENT_DEV':'1','CTM_VARIANTS':'review',
        'CTM_STACK_NATIVE_PACKAGE':str(args.runtime.resolve()),'CTM_STACK_PYTHON':os.sys.executable}
    subprocess.run([os.environ.get('QUARTO','quarto'),'render','index.qmd'],cwd=project,env=environment,check=True,timeout=600)
    html=(project/'index.html').read_text()
    assert all('data-stack-id="'+label+'"' in html for label in ['plain-native','native-python','native-basis','sympy-control'])


if __name__=='__main__':main()
