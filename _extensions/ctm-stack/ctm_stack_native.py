"""Maxima backend for the shared STACK variant/review producer.

The installed component owns the Node compiler. Shared authoring owns leases,
approval decisions, numbering and publication; this module supplies maths.
"""
import copy
import html
import importlib.util
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import tempfile
import threading
import time

from ctm_variants.model import candidate, snapshot, classify, digest, VariantError

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('_ctm_owned_maxima_compiler',HERE/'native/compiler.py')
compiler=importlib.util.module_from_spec(spec);spec.loader.exec_module(compiler)


class NativeBackend:
    id='maxima'

    def __init__(self, *, runtime_root=None, checker_folder=None, cache=None):
        self.runtime_root=Path(runtime_root or os.environ.get('CTM_STACK_NATIVE_PACKAGE',HERE/'native/runtime-v3')).resolve()
        self.checker_folder=Path(checker_folder or os.environ.get('CTM_CHECKERS_FOLDER',HERE.parent/'ctm-checkers')).resolve()
        self.cache=cache
        self.child=None;self.sequence=0;self.records={}

    def __enter__(self):
        return self

    def __exit__(self,*args):
        self.close()

    def close(self):
        child=self.child;self.child=None
        if child is not None:
            try:
                child.stdin.close();child.wait(timeout=5)
            except (BrokenPipeError,subprocess.TimeoutExpired):
                child.kill();child.wait()
            finally:
                child.stdout.close()
        if hasattr(self,'temporary'):
            self.temporary.cleanup();del self.temporary
        if hasattr(self,'errors'):
            self.errors.close();del self.errors

    def load_question(self,source,question_name,options):
        if any(k in options for k in ['checker','checker-value','tests','python-checkers']):
            raise VariantError('Native Python/declarative continuation is a separate capability (M4d)')
        question,self.source_hash=compiler.model(source,question_name)
        self.source_question=question
        self._open(question)
        return question

    def _open(self,question):
        if self.child is not None:
            return
        if not (self.runtime_root/'package.json').is_file():
            raise VariantError('Stage the owned runtime-v3 package and set CTM_STACK_NATIVE_PACKAGE for native author builds')
        import zipfile
        wheel,wheel_hash=compiler.checker_part(self.checker_folder)
        self.temporary=tempfile.TemporaryDirectory(prefix='ctm-native-admission-')
        with zipfile.ZipFile(wheel) as bundle:
            for filename in ['admission.js','admission-data.json']:
                Path(self.temporary.name,filename).write_bytes(bundle.read('ctm_checkers/stack/'+filename))
        self.errors=tempfile.TemporaryFile()
        try:
            self.child=subprocess.Popen([os.environ.get('CTM_STACK_NODE','node'),str(HERE/'native/compile-question.mjs'),'--server'],
                # Stay in the component supervisor's process group so its
                # aggregate deadline also retires this Node/Wasm descendant.
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.errors)
        except FileNotFoundError as error:
            self.close();raise VariantError('Native author builds require Node 22 or 24 (CTM_STACK_NODE)') from error
        self.messages=queue.Queue(maxsize=1)
        child=self.child
        def read():
            while True:
                line=child.stdout.readline(16*1024*1024+1)
                self.messages.put(line)
                if not line or len(line)>16*1024*1024:
                    return
        self.reader=threading.Thread(target=read,daemon=True);self.reader.start()
        compiled=compiler.compile_model(question)
        reply=self._call({'request':dict(schema=1,question=question,compiled=compiled,sourceSha256=self.source_hash,
            runtimeRoot=str(self.runtime_root),admissionRoot=self.temporary.name,checkerWheelSha256=wheel_hash,
            cache=str(self.cache) if self.cache else None)},timeout=180)
        self.prepared_question=reply['question'];self.identity=reply['identity']

    def _call(self,message,timeout):
        self.sequence+=1;message=dict(message,id=self.sequence)
        try:
            self.child.stdin.write((json.dumps(message)+'\n').encode());self.child.stdin.flush()
            raw=self.messages.get(timeout=timeout)
        except (BrokenPipeError,queue.Empty) as error:
            self.close();raise VariantError('Native compiler stopped or exceeded its supervised deadline') from error
        if not raw:
            self.errors.seek(0);diagnostic=self.errors.read(8000).decode(errors='replace')
            raise VariantError(diagnostic or 'Native compiler exited without a response')
        if len(raw)>16*1024*1024:
            raise VariantError('Native compiler output exceeds 16 MiB')
        reply=json.loads(raw)
        if reply.get('id')!=self.sequence:
            raise VariantError('Malformed or stale native compiler response')
        if reply.get('ok') is not True:
            raise VariantError(str(reply.get('error',{}).get('message','Native compilation failed')))
        return reply

    def seed_record(self,question,seed,timeout=30,*,identity=None):
        if identity is not None:
            raise VariantError('Native Python checker identity continuation is a separate capability (M4d)')
        if question!=self.source_question:
            raise VariantError('Native compiler question changed during resolution')
        if type(seed) is not int or not 1<=seed<=2147483647:
            raise VariantError('Native seed must be an integer from 1 to 2147483647')
        if seed not in self.records:
            self.records[seed]=self._call({'type':'seed','seed':seed},timeout)['record']
        row=self.records[seed];plan=row['plan']
        grading={k:copy.deepcopy(v) for k,v in question.items() if k not in {
            'name','variables','questiontext','generalfeedback','specificfeedback','questionnote','deployedseeds','inputs','prts','qtests'}}
        grading.update(component='ctm-stack',backend='maxima',stackRevision=self.prepared_question['native']['stackRevision'],
            runtimeHash=self.identity['packageHash'],compilerHash=self.identity['compilerHash'],admissionWheelHash=self.identity['checkerWheelSha256'])
        grading['inputs']=[]
        for inp in question['inputs']:
            item={k:copy.deepcopy(v) for k,v in inp.items() if k not in {'boxsize','syntaxhint','showvalidation'}}
            item['teacher']=plan['teachers'][inp['name']]['source'];grading['inputs'].append(item)
        grading['prts']=[]
        for prt in question['prts']:
            item={k:copy.deepcopy(v) for k,v in prt.items() if k not in {'nodes','feedbackvariables'}};item['nodes']=[]
            for node in prt['nodes']:
                resolved=copy.deepcopy(node);resolved.update(plan['approval']['grading'][prt['name']][node['name']])
                for branch in ['true','false']:
                    resolved[branch].pop('feedback',None)
                item['nodes'].append(resolved)
            grading['prts'].append(item)
        note=html.unescape(re.sub('<[^>]*>','',plan.get('questionnote_html',''))).strip()
        teacher={k:v['source'] for k,v in plan['teachers'].items()}
        return candidate('seed='+str(seed),snapshot(plan['approval']['math'],teacher,grading,plan['env']),note=note,
            data={'backend':'maxima','plan':copy.deepcopy(plan),'teacherInputs':row['teacherInputs']},tests=copy.deepcopy(row['tests']))

    def propose(self,question,count=25,*,start=1,retained=(),attempt_limit=5000,elapsed_limit=120,resolve_seed=None):
        deadline=time.monotonic()+elapsed_limit;records=[];skipped=[]
        notes={r['note'] for r in retained};known={r['id'] for r in retained}
        resolve_seed=resolve_seed or self.seed_record
        random=self.prepared_question['native']['compiled']['variables']['random']
        seed=start-1
        if notes and ('{@' not in question['questionnote'] and '{#' not in question['questionnote'] and '[[' not in question['questionnote']):
            return {'records':[],'skipped':[],'nextSeed':start}
        for seed in range(start,start+attempt_limit):
            if time.monotonic()>deadline:
                raise VariantError('Native STACK variant generation exceeded its aggregate budget')
            if 'seed='+str(seed) in known:
                continue
            row=resolve_seed(question,seed)
            if row['note'] in notes:
                skipped.append({'id':row['id'],'reason':'repeated question note'})
            else:
                records.append(row);notes.add(row['note'])
            if len(records)==count or not random or not any(token in question['questionnote'] for token in ['{@','{#','[[']):
                break
        return {'records':records,'skipped':skipped,'nextSeed':seed+1}

    def card_data(self,question,records,entries,*,identifier,review=False,identity_verifier=None):
        rows=classify(entries,records)['entries'];by_id={r['candidate']['id']:r for r in rows if r['candidate'] is not None}
        variants=[]
        for record in records:
            row=by_id.get(record['id']);approved=row is not None and row['state'] in ('current','moved') and row['entry']['status']=='approved'
            variants.append({'n':row['entry']['n'] if approved else None,'id':record['id'],'hash':record['hash'],
                'proposal':not approved,'reviewKey':digest([record['id'],record['hash']]),
                'display':{k:v for k,v in record['data']['plan'].items() if k.endswith('_html')},'plan':record['data']['plan']})
        return {'version':2,'id':identifier,'common':{'inputs':question['inputs'],'qtests':question['qtests'],'checker':None},
            'backend':{'id':'maxima','planSchema':1,'stackRevision':self.prepared_question['native']['stackRevision'],
                'runtimeHash':self.identity['packageHash'],'question':self.prepared_question},'variants':variants,'review':review}

    def runtime_resources(self):
        spec=json.loads((self.runtime_root/'package.json').read_text())
        notices=[]
        for name in ('LICENSES','BUILD-NOTICES.md','SITE-NOTICES-context.md'):
            source=self.runtime_root/name
            if source.is_file():notices.append(name)
            elif source.is_dir():
                notices.extend(p.relative_to(self.runtime_root).as_posix() for p in sorted(source.rglob('*')) if p.is_file())
        return {'root':str(self.runtime_root),'packageHash':self.identity['packageHash'],
            'files':['package.json']+['runtime/'+r['path'] for r in spec['runtimeAssets']]+['stack/'+r['path'] for r in spec['stackFiles']]+notices}
