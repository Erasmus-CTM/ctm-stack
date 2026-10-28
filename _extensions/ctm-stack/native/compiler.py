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


def pyodide_sympy(libs=None):
    """ctm-libs' record of its Pyodide's SymPy, {pyodide, sympy, path}, or None.

    The ctm-libs installed beside this component is the runtime the page loads;
    CTM_LIBS_EXTENSION (component development builds) comes after it. A ctm-libs
    that predates the record (runtime/pyodide-sympy.json) gives None.
    """
    extensions = next((path for path in HERE.parents if path.name == '_extensions'), None)
    candidates = [libs] if libs else [HERE.parent.parent/'ctm-libs']
    if not libs and extensions is not None:
        candidates += [extensions/'ctm-libs', *sorted(extensions.glob('*/ctm-libs'))]
    if not libs and os.environ.get('CTM_LIBS_EXTENSION'):
        candidates.append(Path(os.environ['CTM_LIBS_EXTENSION']))
    for folder in dict.fromkeys(Path(c) for c in candidates):
        path = folder/'runtime/pyodide-sympy.json'
        if path.is_file():
            record = json.loads(path.read_text())
            if not (isinstance(record.get('pyodide'), str) and isinstance(record.get('sympy'), str)):
                raise ValueError(f'{path} records no Pyodide and SymPy versions')
            return {'pyodide': record['pyodide'], 'sympy': record['sympy'], 'path': str(path)}
    return None


def check_host_sympy(python, executable, libs=None):
    """Stop a Python build whose host SymPy the learner's browser would refuse.

    `python` is the checker identity (its sympyVersion is the host's). The
    browser compares its Pyodide SymPy with the recorded one and fails closed
    (python-checker-identity); this reports the same mismatch at build time.
    """
    record = pyodide_sympy(libs)
    host = (python or {}).get('sympyVersion')
    if record is None or host is None or host == record['sympy']:
        return
    raise ValueError(
        f"Host SymPy {host} differs from SymPy {record['sympy']}, which ctm-libs' Pyodide {record['pyodide']} "
        f"runs in the browser ({record['path']}). Learners' browsers would refuse this PythonChecker question "
        f"(python-checker-identity). Install the pinned version in the build's Python: "
        f"\"{executable}\" -m pip install 'sympy=={record['sympy']}'")


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
    seeds=list(seeds)
    if not 1<=len(seeds)<=100:raise ValueError('Expected 1–100 native seeds')
    # Reuse the same two-phase candidate/identity flow as the installed producer.
    spec=importlib.util.spec_from_file_location('_ctm_native_prepare_backend',HERE.parent/'ctm_stack_native.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    options={'checker':checker,'checker-value':checker_value} if checker else {}
    with module.NativeBackend(runtime_root=runtime_root,checker_folder=checker_folder,cache=cache) as backend:
        question=backend.load_question(source,question_name,options,authored_tests=tests)
        records=[]
        for seed in seeds:
            backend.seed_record(question,seed)
            records.append(backend.records[(seed,json.dumps(None))])
        return {'schema':1,'identity':backend.identity,'question':backend.prepared_question,'records':records}
