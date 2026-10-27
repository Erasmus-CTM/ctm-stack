#!/usr/bin/env python3
"""Native preparation and XML tests across distinct authored question families."""
import argparse
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkers',type=Path,required=True)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--sources',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();folder=args.checkers.resolve()
    descriptor=json.loads((folder/'checkers.json').read_text())
    sys.path[:0]=[str(folder/descriptor['wheel']),str(folder/descriptor['parts']['stack']['wheel']),
        str(folder/'native-authoring'),str(ROOT/'_extensions/ctm-stack')]
    from ctm_stack_native import NativeBackend
    report={'schema':1,'passed':False,'questions':[]}
    for name in ['rational-equivalence','numerical-measurement','bounded-matrices',
                 'boolean-equivalence','nested-collections','hyperbolic-equivalence']:
        source=args.sources/(name+'.xml')
        title=ET.parse(source).findtext('question/name/text')
        try:
            with NativeBackend(runtime_root=args.runtime,checker_folder=folder) as backend:
                question=backend.load_question(source,title,{})
                record=backend.seed_record(question,1)
                assert question['qtests'] and record['tests']['passed']
                report['questions'].append({'file':source.name,'question':title,'seed':1,
                    'xmlTests':len(question['qtests']),'teacherScore':record['tests']['teacher']['score'],'passed':True})
        except Exception as error:
            report['questions'].append({'file':source.name,'passed':False,'error':str(error)[:8000]})
        print(json.dumps(report['questions'][-1]),flush=True)
    report['passed']=all(row['passed'] for row in report['questions'])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    if not report['passed']:raise SystemExit('Native question family acceptance failed')


if __name__=='__main__':main()
