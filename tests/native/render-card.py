#!/usr/bin/env python3
"""Build a controlled mixed-backend page using installed CTM dependencies."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--libs',type=Path,required=True)
    parser.add_argument('--checkers',type=Path,required=True)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--xml',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();project=args.output.resolve()
    if project.exists():raise ValueError('Choose a fresh card project')
    for source,name in [(ROOT/'_extensions/ctm-stack','ctm-stack'),(args.libs,'ctm-libs'),(args.checkers,'ctm-checkers')]:
        shutil.copytree(source,project/'_extensions'/name)
    tree=ET.parse(args.xml);question=tree.getroot().find('question')
    note=question.find('questionnote')
    if note is None:note=ET.SubElement(question,'questionnote')
    text=note.find('text')
    if text is None:text=ET.SubElement(note,'text')
    text.text='a={@a@}; b={@b@}'
    tree.write(project/'expansion.xml',encoding='unicode')
    (project/'_quarto.yml').write_text('project:\n  type: default\nformat: html\nfilters:\n  - ctm-stack\nstack:\n  cas: maxima\n')
    def card(label,backend):
        # Native uses the project default, testing both settings paths.
        return '\n'.join(['```{.stack-question}','#| label: '+label,'#| file: expansion.xml',
            '#| question: '+question.findtext('name/text'),*(['#| cas: '+backend] if backend else []),
            '#| variants: 2','#| review: true','```'])
    (project/'index.qmd').write_text('---\ntitle: Native card integration\n---\n\n'+card('native-proof',None)+'\n\n'+card('sympy-control','sympy')+'\n')
    environment={**os.environ,'CTM_COMPONENT_DEV':'1','CTM_VARIANTS':'review',
        'CTM_STACK_NATIVE_PACKAGE':str(args.runtime.resolve()),'CTM_STACK_PYTHON':os.environ.get('CTM_STACK_PYTHON',os.sys.executable)}
    subprocess.run([os.environ.get('QUARTO','quarto'),'render','index.qmd'],cwd=project,env=environment,check=True,timeout=600)


if __name__=='__main__':main()
