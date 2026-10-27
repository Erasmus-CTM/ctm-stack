// SPDX-License-Identifier: AGPL-3.0-or-later
// Trusted author-build stdin only. Every computed value/test comes from v3.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import readline from 'node:readline';
import './feedback.js';
import questionEngine from './question-engine.js';
import {loadPackage,sha256} from './node-runtime.mjs';
import {NodeMaximaSession} from './node-session.mjs';
import {adapterHash} from './build-runner.mjs';
import {compileIR} from './author-compiler.mjs';
import {pythonChecker} from './python-checker.mjs';

function canonical(value) {
  if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
  if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
  return JSON.stringify(value);
}
function validSeed(seed) { if(!Number.isInteger(seed)||seed<1||seed>2147483647) throw new Error('Native seeds must be integers from 1 to 2147483647'); }

export class QuestionCompiler {
  static async open(request) {
    if (!request || request.schema!==1 || !/^[a-f0-9]{64}$/.test(request.checkerWheelSha256)
        || !/^[a-f0-9]{64}$/.test(request.sourceSha256)) throw new Error('Expected an installed STACK wheel hash and XML source hash');
    const installed=await loadPackage(request.runtimeRoot);
    const require=createRequire(import.meta.url);
    const admission=require(path.join(request.admissionRoot,'admission.js'))(
      JSON.parse(await fs.readFile(path.join(request.admissionRoot,'admission-data.json'))));
    const sources=await Promise.all(['question-engine.js','feedback.js','author-compiler.mjs','maxima-parser.cjs','castext-parser.cjs',
      'compiler-data.json','compiler-provenance.json','stack-pin.json','stack-pin.js','prt_compiler.py','python-checker.py','python-checker.mjs'].map(async name=>[name,sha256(await fs.readFile(new URL(name,import.meta.url)))]));
    const identity={schema:1,packageHash:installed.packageHash,transportHash:await adapterHash(),
      compilerHash:sha256(JSON.stringify(sources)),checkerWheelSha256:request.checkerWheelSha256,node:process.versions.node};
    const question={...request.question};delete question.native;
    const compiled=request.compiled;
    if(!compiled||compiled.schema!==1||!compiled.prts||Object.values(compiled.prts).some(p=>typeof p.def!=='string'))throw new Error('A prepared Python compiler plan is required');
    const usesPython=!!question.checker||!!question.authored_tests||Object.values(compiled.prts).some(p=>p.continuations);
    const checker=usesPython?pythonChecker(request.python||{}):undefined;
    if(usesPython){
      if(!/^[a-f0-9]{64}$/.test(request.python?.baseWheelSha256))throw new Error('Python continuation needs the installed base checker wheel identity');
      const actual=await checker.identity();
      if(JSON.stringify(actual.version)!==JSON.stringify(request.python.version)){await checker.close();throw new Error('Python checker interpreter identity differs');}
      // Host and browser must use the same SymPy version. The browser measures
      // its loaded package before accepting any request; a runtime upgrade
      // therefore needs a matching host rebuild and fresh approval.
      identity.python={baseWheelSha256:request.python.baseWheelSha256,...actual,browserSympyVersion:actual.sympyVersion};
    }
    const questionHash=sha256(canonical({question,compiled,sourceSha256:request.sourceSha256,
      packageHash:identity.packageHash,compilerHash:identity.compilerHash,checkerWheelSha256:identity.checkerWheelSha256,python:identity.python||null}));
    question.native={schema:1,stackRevision:admission.stackCommit,questionHash,compiled,
      checkerWheelSha256:identity.checkerWheelSha256,feedbackNames:compiled.feedbackNames,packageHash:identity.packageHash,
      python:usesPython,pythonGrading:!!question.checker||Object.values(compiled.prts).some(p=>p.continuations),
      pythonBaseWheelSha256:identity.python?.baseWheelSha256,pythonIdentity:identity.python};
    const self=new QuestionCompiler();
    Object.assign(self,{question,identity,checker,cache:request.cache});
    self.session=new NodeMaximaSession(request.runtimeRoot);
    self.engine=new questionEngine.Engine(expression=>self.session.evaluate(expression),admission,
      checker);
    return self;
  }
  async plan(seed){validSeed(seed);await this.session.start();return {seed,plan:await this.engine.prepare(this.question,seed)};}
  async seed(seed,assigned) {
    validSeed(seed);
    if(assigned!==undefined&&assigned!==null){
      if(Object.keys(assigned).sort().join(',')!=='hash,id,n'||assigned.id!=='seed='+seed||!/^[a-f0-9]{16}$/.test(assigned.hash)
        ||assigned.n!==null&&(!Number.isSafeInteger(assigned.n)||assigned.n<1))throw new Error('Invalid assigned native checker identity');
    }
    if(this.question.authored_tests&&!assigned)throw new Error('Authored tests require the current candidate id/hash');
    const {question,identity}=this;
    const key=sha256(canonical({identity,questionHash:question.native.questionHash,seed,assigned:assigned||null}));
    const filename=this.cache&&path.join(this.cache,key+'.json');
    if(filename) {
      try {
        const hit=JSON.parse(await fs.readFile(filename));
        if(hit.key===key && canonical(hit.identity)===canonical(identity) && hit.record?.seed===seed
            && hit.record.plan?.questionHash===question.native.questionHash
            && hit.resultHash===sha256(canonical(hit.record))) return {...hit.record,cacheHit:true};
      } catch(error) { if(error.code!=='ENOENT'&&!(error instanceof SyntaxError))throw error; }
    }
    await this.session.start();
    const plan=await this.engine.prepare(question,seed);
    if(assigned)Object.assign(plan,assigned);
    const tests=await this.engine.tests(question,plan);
    if(!tests.passed)throw new Error('seed='+seed+': XML question tests failed: '+JSON.stringify(tests));
    const names=new Set(question.prts.map(p=>p.name));
    const full=question.qtests.findIndex(t=>[...names].every(n=>t.expected[n]?.score===1));
    const teacherInputs=full<0?Object.fromEntries(Object.entries(plan.teachers).map(([k,v])=>[k,questionEngine.written(v.source)])):plan.testInputs[full];
    const teacher=await this.engine.grade(question,plan,teacherInputs);
    if(teacher.status!=='graded'||Math.abs(teacher.score-1)>1e-8||Object.values(teacher.prts).some(p=>p.score!==1))throw new Error('seed='+seed+': native teacher vector must score 1 on every PRT');
    const probes=[];
    for(const input of question.inputs)if(input.type==='algebraic')for(const answer of ['0','1']) {
      if(answer===teacherInputs[input.name])continue;
      const result=await this.engine.grade(question,plan,{...teacherInputs,[input.name]:answer});
      probes.push({input:input.name,answer,result,warning:result.score===1});
    }
    const record={seed,plan,teacherInputs,tests:{passed:true,qtests:tests,teacher,wrongProbes:probes,...(this.checker?{checkerProcess:this.checker.stats()}:{} )}};
    if(filename) {
      await fs.mkdir(this.cache,{recursive:true});
      const temp=filename+'.'+process.pid+'.tmp';
      try {await fs.writeFile(temp,JSON.stringify({key,identity,record,resultHash:sha256(canonical(record))})+'\n',{flag:'wx'});await fs.rename(temp,filename);}
      finally {await fs.rm(temp,{force:true});}
    }
    return {...record,cacheHit:false};
  }
  async close() {await this.checker?.close();await this.session.stop();}
}
export async function prepare(request) {
  if(!Array.isArray(request.seeds)||!request.seeds.length||request.seeds.length>100)throw new Error('Expected 1–100 native seeds');
  request.seeds.forEach(validSeed);
  const compiler=await QuestionCompiler.open(request);
  try {
    const records=[];for(const seed of request.seeds)records.push(await compiler.seed(seed));
    return {schema:1,identity:compiler.identity,question:compiler.question,records};
  } finally {await compiler.close();}
}
async function server() {
  let compiler,sequence=0;
  const lines=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
  try {
    for await(const line of lines) {
      if(line.length>16*1024*1024)throw new Error('Native compiler message exceeds 16 MiB');
      const message=JSON.parse(line);
      if(message.id!==++sequence)throw new Error('Native compiler request sequence differs');
      if(!compiler) {
        compiler=await QuestionCompiler.open(message.request);
        // Source-loaded runtime startup is separate from a seed's calculation
        // deadline. The component's init request has its own loading budget.
        await compiler.session.start();
        process.stdout.write(JSON.stringify({id:message.id,ok:true,identity:compiler.identity,question:compiler.question})+'\n');
      } else if(message.type==='prepare-seed') {
        process.stdout.write(JSON.stringify({id:message.id,ok:true,record:await compiler.plan(message.seed)})+'\n');
      } else if(message.type==='seed') {
        process.stdout.write(JSON.stringify({id:message.id,ok:true,record:await compiler.seed(message.seed,message.identity)})+'\n');
      } else throw new Error('Unexpected native compiler operation');
    }
  } finally {
    // A failed seed must close the stdin reader too. Otherwise Node keeps the
    // pipe alive after reporting the author error, and the parent can only
    // observe a misleading deadline rather than the actual test diagnostic.
    lines.close();process.stdin.pause();
    await compiler?.close();
  }
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  try {
    if(process.argv.includes('--server'))await server();
    else {
      let raw='';for await(const chunk of process.stdin){raw+=chunk;if(raw.length>16*1024*1024)throw new Error('Native preparation request exceeds 16 MiB');}
      const request=JSON.parse(raw);
      process.stdout.write(JSON.stringify(process.argv.includes('--compile-ir')?compileIR(request.question):await prepare(request))+'\n');
    }
  } catch(error){process.stderr.write('Native compiler: '+error.message+'\n');process.exitCode=1;}
}
