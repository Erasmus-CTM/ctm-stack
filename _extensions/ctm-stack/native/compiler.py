"""Native question build frontend: structural XML + Node compiler + runtime-v3.

No SymPy expression evaluation, browser or authored grading fallback runs here.
The caller supplies installed checker wheels and staged, verified owned assets.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile
import importlib.util
import sys
import ast

HERE = Path(__file__).resolve().parent
STACK = json.loads((HERE/'stack-pin.json').read_text())['revision']


def sha(body):
    return hashlib.sha256(body).hexdigest()


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True)


def model(source, question_name, *, checker=None, checker_value=1, tests=None):
    # This importer is structural; its package root is deliberately lazy.
    from ctm_checkers.stack.importer import import_xml, UnsupportedQuestion
    from xml.etree import ElementTree as ET
    raw = Path(source).read_bytes()
    if len(raw)>8*1024*1024:
        raise ValueError('Native question XML exceeds 8 MiB')
    tree = ET.fromstring(raw)
    selected = [q for q in tree.findall('question') if q.get('type')=='stack' and q.findtext('name/text')==question_name]
    if len(selected)!=1:
        raise ValueError('STACK XML must contain exactly one selected question')
    question = import_xml('<quiz>'+ET.tostring(selected[0],encoding='unicode')+'</quiz>',
                          checker=checker,checker_value=checker_value,tests=tests)[0]
    if tests is not None:
        if not isinstance(tests,list) or not tests or len(tests)>100:raise ValueError('Native tests require 1–100 declarative cases')
        names=[item['name'] for item in question['inputs']]
        prepared=[]
        for case in tests:
            values=case.get('answers') if isinstance(case,dict) else None
            if isinstance(values,list):
                if len(values)!=len(names):raise ValueError('Native test answer count differs from inputs')
                values=dict(zip(names,values))
            if not isinstance(values,dict) or set(values)!=set(names):raise ValueError('Native tests require answers keyed by every input')
            row={}
            for key,value in values.items():
                if value is None or isinstance(value,bool):raise ValueError('Native test answers require expressions or raw text')
                text=str(value)
                if text.strip().startswith('raw('):
                    parsed=ast.parse(text,mode='eval').body
                    if not(isinstance(parsed,ast.Call) and isinstance(parsed.func,ast.Name) and parsed.func.id=='raw'
                        and len(parsed.args)==1 and not parsed.keywords and isinstance(parsed.args[0],ast.Constant)
                        and isinstance(parsed.args[0].value,str)):raise ValueError('raw() requires one literal string')
                    row[key]={'raw':parsed.args[0].value}
                else:row[key]={'expression':text}
            prepared.append(row)
        question['native_test_inputs']=prepared
    if len(question['inputs'])>32 or len(question['prts'])>32 or sum(len(p['nodes']) for p in question['prts'])>256:
        raise UnsupportedQuestion(question_name,'native plan','Question exceeds native structural bounds')
    texts = [question.get(k,'') for k in ['questiontext','generalfeedback','specificfeedback','questionnote']]
    texts += [n[b]['feedback'] for p in question['prts'] for n in p['nodes'] for b in ['true','false']]
    for text in texts:
        blocks = re.findall(r'\[\[\s*/?\s*([A-Za-z][\w-]*)(?=[:\s/\]])',text)
        unsupported = set(blocks)-{'input','validation','feedback','if','elif','else','foreach','comment'}
        if unsupported:
            raise UnsupportedQuestion(question_name,'CASText','Unsupported native block(s): '+', '.join(sorted(unsupported)))
    return question, sha(raw)


def checker_part(folder):
    folder = Path(folder).resolve()
    descriptor = json.loads((folder/'checkers.json').read_text())
    part = descriptor['parts']['stack']; wheel = (folder/part['wheel']).resolve()
    if not wheel.is_relative_to(folder) or sha(wheel.read_bytes())!=part['sha256']:
        raise ValueError('STACK wheel differs from its canonical descriptor')
    return wheel, part['sha256']


def compile_model(question):
    """Parse with upstream JS grammar actions; emit the PRTs in Python."""
    result=subprocess.run([os.environ.get('CTM_STACK_NODE','node'),'--max-old-space-size=256',
        str(HERE/'compile-question.mjs'),'--compile-ir'],input=json.dumps({'question':question}),
        capture_output=True,text=True,timeout=30)
    if result.returncode:
        raise ValueError(result.stderr[-8000:] or 'Native author parsing failed')
    if len(result.stdout)>16*1024*1024:
        raise ValueError('Native compiler IR exceeds 16 MiB')
    filename=HERE/'prt_compiler.py'
    module_name='_ctm_owned_prt_'+sha(filename.read_bytes())[:16]
    if module_name not in sys.modules:
        spec=importlib.util.spec_from_file_location(module_name,filename)
        module=importlib.util.module_from_spec(spec);sys.modules[module_name]=module;spec.loader.exec_module(module)
    return sys.modules[module_name].compile_ir(question,json.loads(result.stdout))


def prepare_question(source, question_name, seeds, *, runtime_root, checker_folder, cache=None,
                     checker=None, checker_value=1, tests=None):
    question, source_hash = model(source,question_name,checker=checker,checker_value=checker_value,tests=tests)
    compiled=compile_model(question)
    wheel, checker_hash = checker_part(checker_folder)
    folder=Path(checker_folder).resolve()
    descriptor=json.loads((folder/'checkers.json').read_text())
    base=(folder/descriptor['wheel']).resolve()
    if not base.is_relative_to(folder) or sha(base.read_bytes())!=descriptor['sha256']:
        raise ValueError('Checker wheel differs from its canonical descriptor')
    with tempfile.TemporaryDirectory(prefix='ctm-admission-',dir=os.environ.get('CTM_STACK_BUILD_TMP')) as tmp:
        with zipfile.ZipFile(wheel) as bundle:
            for filename in ['admission.js','admission-data.json']:
                Path(tmp,filename).write_bytes(bundle.read('ctm_checkers/stack/'+filename))
        request = dict(schema=1,question=question,compiled=compiled,sourceSha256=source_hash,seeds=list(seeds),runtimeRoot=str(Path(runtime_root).resolve()),
                       admissionRoot=tmp,checkerWheelSha256=checker_hash,cache=str(cache) if cache else None,
                       python={'executable':sys.executable,'paths':[str(base),str(wheel)],
                               'baseWheelSha256':descriptor['sha256'],'version':list(sys.version_info[:3])})
        try:
            result = subprocess.run([os.environ.get('CTM_STACK_NODE','node'),str(HERE/'compile-question.mjs')],
                input=json.dumps(request),capture_output=True,text=True,timeout=240)
        except FileNotFoundError as error:
            raise ValueError('Native author builds require Node 22 or 24 (CTM_STACK_NODE)') from error
        if result.returncode:
            raise ValueError(result.stderr[-8000:] or 'Native Maxima preparation failed')
        if len(result.stdout)>16*1024*1024:
            raise ValueError('Native preparation output exceeds 16 MiB')
        prepared = json.loads(result.stdout)
    return prepared
