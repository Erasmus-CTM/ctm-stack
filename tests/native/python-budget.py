#!/usr/bin/env python3
"""Real 3-Python-node / 10-XML-test seed budget, including native preparation."""
import argparse,copy,json,runpy,sys,tempfile,time
from pathlib import Path
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser(description=__doc__)
for name in ('checkers','runtime','sources','output'):p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args();folder=a.checkers.resolve();d=json.loads((folder/'checkers.json').read_text())
sys.path[:0]=[str(folder/d['wheel']),str(folder/d['parts']['stack']['wheel']),str(folder/'native-authoring'),str(ROOT/'_extensions/ctm-stack')]
from ctm_stack_native import NativeBackend
checker=runpy.run_path(str(Path(__file__).with_name('python-integration.py')))['CHECKER']
with tempfile.TemporaryDirectory(prefix='native-python-budget-') as directory:
 tree=ET.parse(a.sources/'python-checker.xml');q=tree.getroot().find('question');prt=q.find('prt');template=prt.find('node')
 for item in list(prt.findall('node')):prt.remove(item)
 for i in range(3):
  node=copy.deepcopy(template);node.find('name').text=str(i);node.find('truenextnode').text=str(i+1) if i<2 else '-1'
  node.find('trueanswernote').text=f'node-{i}-T';prt.append(node)
 for test in list(q.findall('qtest')):q.remove(test)
 for i in range(10):
  test=ET.SubElement(q,'qtest');ET.SubElement(test,'testcase').text=str(i+1)
  value=ET.SubElement(test,'testinput');ET.SubElement(value,'name').text='ans';ET.SubElement(value,'value').text=f'{i+1}*d'
  expected=ET.SubElement(test,'expected')
  for key,value in {'name':'prt1','expectedscore':'1','expectedpenalty':'0','expectedanswernote':'()'}.items():ET.SubElement(expected,key).text=value
 source=Path(directory)/'budget.xml';tree.write(source,encoding='unicode')
 with NativeBackend(runtime_root=a.runtime,checker_folder=folder) as backend:
  before=time.perf_counter();question=backend.load_question(source,q.findtext('name/text'),{'checker':checker});loading=time.perf_counter()-before
  samples=[]
  for seed in (1,2):
   before=time.perf_counter();row=backend.seed_record(question,seed);elapsed=time.perf_counter()-before
   assert elapsed<30,elapsed
   cases=row['tests']['qtests']['results'];assert len(cases)==10 and all(len(c['actual']['prts']['prt1']['path'])==3 for c in cases)
   assert row['tests']['checkerProcess']['processes']==1
   samples.append({'seed':seed,'seconds':elapsed,'tests':len(cases),'nodes':3,'checker':row['tests']['checkerProcess']})
  report={'passed':True,'budgetSeconds':30,'loadingSeconds':loading,'samples':samples,'pythonIdentity':backend.identity['python']}
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
