// SPDX-License-Identifier: AGPL-3.0-or-later AND GPL-3.0-or-later
// Shared Node/browser execution of native compiled PRT and CASText programs.
// No SymPy preparation, independent response-tree walker or grading fallback.
(function (root) {
  'use strict';
  const STACK = typeof module==='object'&&module.exports?require('./stack-pin.js'):root.CTMStackRevision;
  const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const escape = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  function fault(message, kind = 'author') { return Object.assign(new Error(message), {kind, code: 'maxima-question'}); }
  function name(value) {
    if (typeof value !== 'string' || !/^[A-Za-z][A-Za-z0-9_]*$/.test(value) || value.startsWith('ctm_')) throw fault('Unsafe native variable name');
    return value;
  }
  // Maxima strings use literal control characters, not JSON's \n/\u escapes.
  function quote(value) {
    const parts = String(value).split(/([\x00-\x1f\x7f])/).filter(Boolean).map(s =>
      /^[\x00-\x1f\x7f]$/.test(s) ? 'ascii(' + s.charCodeAt(0) + ')' : JSON.stringify(s));
    return parts.length > 1 ? 'sconcat(' + parts.join(',') + ')' : parts[0] || '""';
  }
  const bool = x => x ? 'true' : 'false';
  const map = pairs => '["stack_map"' + pairs.map(([k, v]) => ',[' + quote(k) + ',' + v + ']').join('') + ']';
  const block = (locals, values) => 'block([' + [...new Set(locals)].join(',') + '],' + values.filter(Boolean).join(',') + ')';
  const exact=expression=>'block([fpprintprec:0],string('+expression+'))';
  const evaluate = source => 'eval_string(' + quote(source) + ')';
  const aliases = Object.assign(Object.create(null), {ln: 'log', cosec: 'csc', cosech: 'csch',
    arcsin:'asin', arccos:'acos', arctan:'atan', arcsec:'asec', arccot:'acot', arccsc:'acsc',
    arcsinh:'asinh', arccosh:'acosh', arctanh:'atanh', arcsech:'asech', arccoth:'acoth', arccsch:'acsch',
    arccosec:'acsc', arsinh:'asinh', arcosh:'acosh', artanh:'atanh', arsech:'asech', arcoth:'acoth', arcsch:'acsch'});
  const calls = new Set(('sqrt sin cos tan sec csc cot sinh cosh tanh sech csch coth exp log abs ' +
    'asin acos atan asec acsc acot asinh acosh atanh asech acsch acoth gcd mod matrix').split(' '));
  const constants = new Map([['pi','%pi'],['%pi','%pi'],['e','%e'],['%e','%e'],['i','%i'],['%i','%i']]);
  // Convert native display vocabulary, preserving quoted string contents.
  const written=text=>text.replace(/"(?:\\.|[^"\\])*"|%pi\b|%e\b|%i\b|\bnoun(?:and|or|not)\b/g,token=>token.startsWith('"')?token:token.replace(/^%/,'').replace(/^noun/,''));
  function learnerSource(tree) {
    let count = 0;
    function visit(n, depth) {
      if (!n || ++count > 700 || depth > 350 || !Array.isArray(n.children)) throw fault('Malformed admitted expression', 'runtime');
      const children = n.children.map(c => visit(c, depth + 1));
      if (n.kind === 'number' && /^(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$/.test(n.value)) return n.value;
      if (n.kind === 'name' && /^%?[A-Za-z_][A-Za-z_0-9]*$/.test(n.value)) return constants.get(n.value) || n.value;
      if (n.kind === 'boolean' && ['true','false'].includes(n.value)) return n.value;
      if (n.kind === 'unary' && ['+','-'].includes(n.value) && children.length === 1) return '(' + n.value + children[0] + ')';
      if (n.kind === 'binary' && ['+','-','*','/','^','**'].includes(n.value) && children.length === 2) return '(' + children[0] + (n.value === '**' ? '^' : n.value) + children[1] + ')';
      if (n.kind === 'equation' && children.length === 2) return '(' + children.join('=') + ')';
      if (n.kind === 'logical' && ['not','and','or','xor','xnor','implies'].includes(n.value)) {
        const op = ['not','and','or'].includes(n.value) ? 'noun' + n.value : n.value;
        if (n.value === 'not' && children.length === 1) return '(' + op + ' ' + children[0] + ')';
        if (children.length === 2) return '(' + children.join(' ' + op + ' ') + ')';
      }
      if (n.kind === 'list' || n.kind === 'set') return (n.kind === 'list' ? '[' : '{') + children.join(',') + (n.kind === 'list' ? ']' : '}');
      if (n.kind === 'call' && calls.has(aliases[n.value] || n.value)) return (aliases[n.value] || n.value) + '(' + children.join(',') + ')';
      // Syntax admission alone does not authorize helper calls or indexing.
      throw fault('This expression is outside the native learner-call subset', 'learner');
    }
    return visit(tree, 0);
  }
  function tidy(value, compiled) {
    for (const [key, text] of Object.entries(compiled.language.latexReplacements)) value = value.split(key).join(text);
    return value.replace(/\n /g, '').replace(/\n/g, '').replace(/ {4}/g, ' ').replace(/ {3}/g, ' ').replace(/ {2}/g, ' ');
  }
  function casttext(value, compiled, io = token => '[[' + token[1] + ':' + token[2] + ']]') {
    const unmask=s=>s.replace(/QMCHAR/g,'?');
    let nodes = 0;
    function render(v, depth, masked = false) {
      if (++nodes > 10000 || depth > 64) throw fault('Native CASText output exceeded its bound');
      if (typeof v === 'string') {
        for (const [key, text] of Object.entries(compiled.statics)) v = v.split(key).join(text);
        return masked?unmask(v):v;
      }
      if (!Array.isArray(v)) throw fault('Malformed native CASText output', 'runtime');
      if (v[0] === '%root') return v.slice(1).map(c => render(c, depth + 1, true)).join('');
      if (v[0] === 'ctm_python_feedback' && v.length === 2 && typeof v[1] === 'string') return escape(v[1]);
      if (v[0] === 'smlt' && v.length === 2) { const text=tidy(v[1], compiled); return masked?unmask(text):text; }
      if (v[0] === 'ioblock' && v.length === 3) { const text=io(v); return masked?unmask(text):text; }
      if (v[0] === '%strans' && v.length === 2) {
        if (!root.NativeFeedback) throw fault('Native feedback formatter is missing', 'runtime');
        const description = root.NativeFeedback.describe(v[1], compiled.language);
        if (!description.translated) throw fault('Unsupported native feedback: ' + description.reason);
        return masked?unmask(description.html):description.html;
      }
      throw fault('Unsupported compiled CASText output block: ' + v[0]);
    }
    return render(value, 0);
  }
  function inputHTML(token, question, teachers) {
    const channel = token[1], key = token[2], safe = escape(key);
    const input = question.inputs.find(i => i.name === key);
    if (channel === 'feedback' && (question.prts.some(p => p.name === key)||key==='checker'&&question.checker)) return '<span class="stack-feedback" data-name="' + safe + '"></span>';
    if (!input) throw fault('Unknown native CASText input: ' + key);
    if (channel === 'validation') return '<span class="stack-validation" data-name="' + safe + '" aria-live="polite"></span>';
    if (channel !== 'input') throw fault('Unsupported native CASText input channel: ' + channel);
    if (input.type === 'matrix') {
      const shape = teachers[key].shape;
      if (!Array.isArray(shape) || shape.length !== 2 || shape.some(n => !Number.isSafeInteger(n) || n < 1 || n > 16) || shape[0]*shape[1] > 64) throw fault('Native matrix teacher exceeds its shape bound');
      const spec = {name: key, ...(input.matrix || Object.fromEntries(['rows','cols'].map((axis, at) => [axis,{auto:false,initial:shape[at],min:shape[at],max:shape[at]}])))};
      return '<span class="stack-answer stack-matrix" data-name="' + safe + '" data-matrix-spec="' + escape(JSON.stringify(spec)) + '" role="group" aria-label="Answer ' + safe + '"></span>';
    }
    return '<input class="stack-answer" data-name="' + safe + '" aria-label="Answer ' + safe + '" size="' + Math.min(60, Math.max(1, input.boxsize)) + '" autocomplete="off">';
  }
  function typeOf(expression) {
    return 'if matrixp(' + expression + ') then "matrix" else if listp(' + expression + ') then "list" else if setp(' + expression + ') then "set" else if equationp(' + expression + ') then "equation" else "scalar"';
  }
  function testAnswerNote(expected,actual) {
    expected=expected.trim();
    if(!expected)return false;
    if(expected==='()')return true;
    if(!actual.length)return expected==='NULL';
    if(expected==='NULL')return false;
    const start=expected.startsWith('['),end=!expected.endsWith(')');
    if(expected.startsWith('[')||expected.startsWith('('))expected=expected.slice(1);
    if(expected.endsWith(']')||expected.endsWith(')'))expected=expected.slice(0,-1);
    const wanted=expected.split('|').map(n=>n.trim());
    if(start&&wanted[0]!==actual[0]||end&&wanted.at(-1)!==actual.at(-1))return false;
    let at=0;
    for(const note of wanted){while(at<actual.length&&actual[at].trim()!==note)at++;if(at===actual.length)return false;at++;}
    return true;
  }
  class Engine {
    constructor(evaluateProgram, admission, checker) { this.evaluateProgram = evaluateProgram; this.admission = admission; this.checker=checker; }
    check(question, variant) {
      if (!question || question.native?.schema !== 1 || question.native.stackRevision !== STACK || !/^[a-f0-9]{64}$/.test(question.native.questionHash)) throw fault('Malformed native question plan');
      if (variant && (variant.schema !== 1 || variant.questionHash !== question.native.questionHash || !Number.isInteger(variant.seed) || variant.seed < 1 || variant.seed > 2147483647)) throw fault('Stale native variant plan');
      if (!this.admission || this.admission.stackCommit !== STACK) throw fault('Shared admission does not match native STACK');
    }
    program(question, variant, expressions) {
      this.check(question, variant);
      const c = question.native.compiled;
      const locals = ['simp:' + bool(question.simplify), 'assume_pos:' + bool(question.assumepositive),
        'assume_real:' + bool(question.assumereal), '%ERR:["stack_map"]', '%NOTES:["stack_map"]', '%FEEDBACK:["stack_map"]',
        '%stmt:"ctm-question"', '_INPUT_STRING:["stack_map"]', ...question.inputs.map(i => name(i.name)),
        ...Object.keys(c.variables.references.write).map(name)];
      const functions=Object.values(c.prts).map(p => {
        const identifier=p.function||p.sig.split('(')[0];
        if(!/^[A-Za-z][A-Za-z0-9_]*$/.test(identifier))throw fault('Malformed compiled PRT function');
        return identifier;
      });
      const setup = functions.length?['local('+functions.join(',')+')']:[];
      if (variant) {
        // Recreate native values/structure from the owned seed. Printed env
        // text is evidence for the checker, never a native state checkpoint.
        setup.push('stack_randseed('+variant.seed+')',c.variables.statement);
      } else setup.push('stack_randseed(' + question.native.seed + ')', c.variables.statement);
      return block(locals, [...setup, ...Object.values(c.prts).map(p => p.def), ...expressions]);
    }
    async prepare(question, seed) {
      if (!Number.isInteger(seed) || seed < 1 || seed > 2147483647) throw fault('Invalid native seed');
      question = {...question, native: {...question.native, seed}};
      const c = question.native.compiled;
      const teacherSource=i=>c.inputTeachers?.[i.name]??i.teacher;
      const teachers = map(question.inputs.map(i => [i.name, map([['source',exact(teacherSource(i))], ['type',typeOf(teacherSource(i))],
        ['shape','if matrixp(' + teacherSource(i) + ') then matrix_size(' + teacherSource(i) + ') else []']]) ]));
      const expression = map([['env',map(Object.keys(c.variables.references.write).map(n => [n,exact(name(n))]))],
        ['teachers',teachers], ['texts',map(Object.entries(c.texts))],
        ['math',c.math], ['grading',c.grading],
        ['testInputs',block(['simp',...question.inputs.map(i => name(i.name))], [
          ...question.inputs.map(i => name(i.name) + ':' + teacherSource(i)), 'simp:false', c.testInputs])],
        ['authoredInputs',block(['simp',...question.inputs.map(i => name(i.name))],[
          ...question.inputs.map(i => name(i.name)+':'+teacherSource(i)),'simp:false',c.authoredInputs||'[]'])]]);
      const prepared = await this.evaluateProgram(this.program(question, null, [expression]));
      const variant = {schema:1, questionHash:question.native.questionHash, seed, env:prepared.env,
        teachers:prepared.teachers, testInputs:prepared.testInputs, authoredInputs:prepared.authoredInputs,
        approval:{math:prepared.math,grading:prepared.grading}};
      variant.testInputs=prepared.testInputs.map((row,index)=>Object.fromEntries(Object.entries(row).map(([key,value])=>
        [key,question.qtests[index].inputs[key]?.startsWith('RAW:')?value:written(value)])));
      variant.authoredInputs=prepared.authoredInputs.map((row,index)=>Object.fromEntries(Object.entries(row).map(([key,value])=>
        [key,Object.hasOwn(question.native_test_inputs[index][key],'raw')?value:written(value)])));
      for (const [field, value] of Object.entries(prepared.texts)) {
        const target = {questiontext:'question_html', generalfeedback:'generalfeedback_html',
          specificfeedback:'specificfeedback_html', questionnote:'questionnote_html'}[field];
        variant[target] = casttext(value, c, t => inputHTML(t, question, prepared.teachers));
      }
      return variant;
    }
    admit(question, variant, answers) {
      this.check(question, variant);
      const c = question.native.compiled, admitted = {}, inputs = {};
      const questionVariables = Object.keys(variant.env), authorNames = [...questionVariables, ...question.native.feedbackNames];
      for (const input of question.inputs) {
        const raw = String(answers[input.name] ?? '').trim();
        let feedback = '';
        if (!raw) feedback = 'Enter an answer';
        else {
          const result = this.admission.admitExpression(raw, {insertstars:input.insertstars,questionVariables,authorNames});
          if (result.status !== 'admitted') feedback = result.feedback;
          else {
            try {
              const source = learnerSource(result.tree);
              const visit = n => [n, ...n.children.flatMap(visit)];
              const nodes = visit(result.tree);
              if (nodes.some(n => ['name','call'].includes(n.kind) && input.forbidwords.some(w => w.toLowerCase() === n.value.toLowerCase()))) feedback = 'This expression contains a forbidden word';
              else if (input.forbidfloat && nodes.some(n => n.kind === 'number' && /[.eE]/.test(n.value))) feedback = 'Floats are not allowed';
              else admitted[input.name] = {source,raw,canonical:result.canonical};
            } catch (error) { if (error.kind !== 'learner') throw error; feedback = error.message; }
          }
        }
        if (feedback) inputs[input.name] = {valid:false,latex:'',feedback};
      }
      return {admitted,inputs};
    }
    async validate(question, variant, answers) {
      const {admitted, inputs} = this.admit(question, variant, answers);
      const rows = [];
      for (const input of question.inputs) {
        const entry = admitted[input.name]; if (!entry) continue;
        const validation = (input.checkanswertype ? 'stack_validate' : 'stack_validate_typeless') + '([ctm_s],'
          + bool(input.requirelowestterms) + ',ctm_t,0' + (input.checkanswertype ? '' : ',false') + ')';
        const filename = '"/ctm/tmp/native-validation.txt"';
        const checks = ['ctm_s:' + evaluate(entry.source), 'with_stdout(' + filename + ',' + validation + ')',
          'ctm_stream:openr(' + filename + ')', 'ctm_line:readline(ctm_stream)',
          'while not is(ctm_line=false) do (if slength(ctm_line)>0 then ctm_lines:endcons(ctm_line,ctm_lines),ctm_line:readline(ctm_stream))',
          'close(ctm_stream)'];
        if (input.type === 'numerical') checks.push('if not numberp(ev(ctm_s,simp)) then ctm_lines:endcons("Enter a numerical answer",ctm_lines)');
        if (input.type === 'matrix') checks.push('if not matrixp(ctm_s) then ctm_lines:endcons("Enter a matrix",ctm_lines)');
        checks.push('if length(%ERR)>1 then ctm_lines:endcons("Native STACK could not evaluate this expression",ctm_lines)',
          map([['valid','is(ctm_lines=[])'], ['latex','if ctm_lines=[] then tex1(ctm_s) else ""'],
            ['feedback','simplode(ctm_lines," ")']]));
        rows.push([input.name, block(['ctm_s','ctm_t','ctm_r','ctm_lines:[]','ctm_stream','ctm_line',
          '%ERR:["stack_map"]','%NOTES:["stack_map"]','%FEEDBACK:["stack_map"]'], [
          'simp:false', 'ctm_t:' + (question.native.compiled.inputTeachers?.[input.name]??input.teacher),
          'ctm_r:ctm_classified_errcatch(' + block([],checks) + ')',
          'if ctm_r[1]="ok" then ctm_r[2] else ' + map([['valid','false'],['latex','""'],
            ['feedback','if ctm_r[1]="internal" then "Internal native validation fault" else "Native STACK could not evaluate this expression"'],
            ['internal','is(ctm_r[1]="internal")']])])]);
      }
      if (rows.length) {
        const evaluated = await this.evaluateProgram(this.program(question, variant, [map(rows)]));
        for (const [key, value] of Object.entries(evaluated)) {
          if (value.internal) throw fault('Internal native validation fault', 'runtime');
          value.latex = tidy(value.latex, question.native.compiled);
          inputs[key] = value;
        }
      }
      const valid = question.inputs.every(i => inputs[i.name]?.valid === true);
      return {status:valid ? 'valid' : 'invalid', inputs, feedback:valid ? 'Review the parsed answers' : 'Correct invalid answers before grading'};
    }
    async grade(question, variant, answers) {
      const validation = await this.validate(question, variant, answers);
      if (validation.status !== 'valid') return {status:'invalid',score:0,inputs:validation.inputs,prts:{},feedback:'Check your answers before grading'};
      const {admitted} = this.admit(question, variant, answers);
      const c = question.native.compiled;
      const expressions = ['simp:false', ...Object.entries(admitted).map(([k,v]) => name(k) + ':' + evaluate(v.source)),
        '_INPUT_STRING:' + map(Object.entries(admitted).map(([k,v]) => [k,quote(v.raw)])),
        map(Object.entries(c.prts).map(([k,p]) => [k,p.sig]))];
      let results;
      const invalid=(result,key)=>{
        for(const detail of Object.values(validation.inputs))delete detail.assessment;
        if(key)Object.assign(validation.inputs[key],{valid:false,feedback:result.feedback||'Invalid answer'});
        const prts=key?{}:{checker:{score:0,penalty:0,feedback:escape(result.feedback||'Invalid answer'),notes:[],answerNotes:[],note:'',path:[]}};
        return {status:'invalid',score:0,inputs:validation.inputs,prts,feedback:result.feedback||'Invalid answer'};
      };
      if(Object.values(c.prts).some(p=>p.continuations)){
        results={};
        const setup=expressions.slice(0,-1);
        for(const [name,p] of Object.entries(c.prts)){
          let raw=await this.evaluateProgram(this.program(question,variant,[...setup,p.sig]));
          let calls=0;
          while(Array.isArray(raw)&&raw[0]==='CTM_PYTHON'){
            const descriptor=p.continuations?.[raw[1]];
            if(!descriptor||typeof raw[2]!=='string'||typeof raw[3]!=='string'||++calls>Object.keys(p.continuations).length)throw fault('Malformed PythonChecker continuation','runtime');
            const response=await this.python(question,variant,admitted,{sans:descriptor.sans,tans:raw[3],options:descriptor.options});
            const node=question.prts.find(tree=>tree.name===name).nodes.find(n=>n.name===raw[1]);
            if(!response.valid)return invalid(node.quiet?{...response,feedback:'Invalid answer'}:response,descriptor.sans);
            if(!node.quiet)for(const [key,value] of Object.entries(response.assessment||{}))validation.inputs[key].assessment=value;
            const feedback=node.quiet?'':response.feedback||'';
            const call=p.function+'('+[...p.callArguments,quote(raw[2]),'['+bool(response.status==='correct')+','+quote(feedback)+']'].join(',')+')';
            raw=await this.evaluateProgram(this.program(question,variant,[...setup,call]));
          }
          results[name]=raw;
        }
      }else results = await this.evaluateProgram(this.program(question, variant, expressions));
      const prts = {}; let score = 0;
      const weighted=[...question.prts];
      if(question.checker)weighted.push({name:'checker',value:question.checker_value||1});
      const total = weighted.reduce((sum,p) => sum + p.value, 0);
      for (const prt of question.prts) {
        const raw = results[prt.name];
        if(Array.isArray(raw)&&raw[0]==='CTM_PRT_ERROR')throw fault('Native response tree failed: '+raw[2],raw[1]==='internal'?'runtime':'author');
        if (!Array.isArray(raw) || raw.length !== 5 || typeof raw[1] !== 'number') throw fault('Native PRT did not return its result: ' + prt.name);
        const [path, fraction, penalty, feedback, notes] = raw;
        const answerNotes=path.flatMap((test,index)=>[test[2],notes[index]].filter(n=>typeof n==='string'&&n.trim()).map(n=>n.trim()));
        prts[prt.name] = {score:fraction, penalty:fraction === 1 ? 0 : penalty,
          feedback:casttext(feedback,c), notes, answerNotes, note:notes.join(' | '), path};
        score += total ? fraction * prt.value / total : 0;
      }
      if(question.checker){
        const result=await this.python(question,variant,admitted);
        if(!result.valid)return invalid(result);
        for(const [key,value] of Object.entries(result.assessment||{}))validation.inputs[key].assessment=value;
        prts.checker={score:result.score,penalty:0,feedback:escape(result.feedback||''),notes:[],answerNotes:[],note:'',path:[],show_score:result.show_score};
        score+=result.score*(question.checker_value||1)/total;
      }
      // Six equal full-mark PRTs otherwise sum to 0.9999999999999999 in
      // JavaScript, making the common card display "partial, 100%". Preserve
      // exact full-mark semantics independently of weighted float arithmetic.
      if(total>0){
        const full=weighted.every(p=>p.value===0||prts[p.name].score===1);
        score=full?1:Math.min(1-Number.EPSILON,Math.max(0,score));
      }
      return {status:'graded',score,inputs:validation.inputs,prts,feedback:Object.values(prts).map(p => p.feedback).filter(Boolean).join(' ')};
    }
    async python(question,variant,admitted,node){
      if(typeof this.checker!=='function')throw fault('Python checker runtime is missing','runtime');
      const request={checker:question.checker||'',questionName:question.name,backend:'maxima',
        inputs:Object.fromEntries(question.inputs.map(i=>[i.name,{type:i.type,raw:admitted[i.name].raw,canonical:admitted[i.name].canonical}])),
        variables:Object.fromEntries(Object.entries(variant.env).map(([k,v])=>[k,written(v)])),
        teacher:Object.fromEntries(Object.entries(variant.teachers).map(([k,v])=>[k,written(v.source)])),
        assumptions:{positive:!!question.assumepositive,real:!!question.assumereal},
        variant:{n:variant.n??null,id:variant.id||'seed='+variant.seed,hash:variant.hash}};
      if(node)request.node={...node,tans:written(node.tans)};
      const result=await this.checker(request);
      if(!result||typeof result.valid!=='boolean'||result.valid&&(!Number.isFinite(result.score)||result.score<0||result.score>1))throw fault('Malformed Python checker result','runtime');
      return result;
    }
    async tests(question, variant) {
      const results = [];let authored;
      for (const [index,test] of question.qtests.entries()) {
        const actual = await this.grade(question,variant,variant.testInputs[index]);
        const checks = Object.entries(test.expected).map(([key,wanted]) => {
          const p = actual.prts[key];
          return {prt:key,passed:!!p && Math.abs(p.score-wanted.score)<1e-8 && Math.abs(p.penalty-wanted.penalty)<1e-8
            && testAnswerNote(wanted.note,p.answerNotes)};
        });
        results.push({testcase:test.testcase,seed:variant.seed,passed:checks.every(c => c.passed),checks,actual});
      }
      if(question.authored_tests){
        const outcomes=[];
        const verdict=score=>score>=1-1e-9?'correct':score<=1e-9?'wrong':'partial';
        const candidate={id:variant.id,hash:variant.hash};
        for(const [index,answers] of variant.authoredInputs.entries()){
          const grade=await this.grade(question,variant,answers),fields={};
          for(const input of question.inputs){
            if(!grade.inputs[input.name]?.valid){fields[input.name]={status:'invalid'};continue;}
            const direct=question.prts.filter(p=>p.nodes.every(n=>n.student===input.name));
            const weight=direct.reduce((s,p)=>s+p.value,0);
            if(weight&&grade.status==='graded'){
              const score=direct.reduce((s,p)=>s+p.value*grade.prts[p.name].score,0)/weight;
              fields[input.name]={score,status:verdict(score)};
            }
          }
          outcomes.push({name:question.authored_tests[index].name,declaration:question.authored_tests[index],candidate,status:grade.status==='graded'?verdict(grade.score):grade.status,score:grade.score,
            fields,'answer-note':Object.values(grade.prts).map(p=>p.note).filter(Boolean).join(' | ')});
        }
        if(typeof this.checker!=='function')throw fault('Authored test expectation checker is missing','runtime');
        const verified=await this.checker({operation:'test-results',backend:'maxima',questionName:question.name,
          candidate,tests:question.authored_tests,fields:question.inputs.map(i=>i.name),results:outcomes});
        if(JSON.stringify(verified?.candidate)!==JSON.stringify(candidate)||verified?.passed!==true||!Array.isArray(verified.results)||verified.results.length!==outcomes.length)throw fault('Malformed native authored-test verification','runtime');
        if(verified.results.some((row,index)=>row.name!==question.authored_tests[index].name||JSON.stringify(row.declaration)!==JSON.stringify(question.authored_tests[index])||JSON.stringify(row.candidate)!==JSON.stringify(candidate)))throw fault('Stale native authored-test verification','runtime');
        authored=verified;
        for(const row of verified.results)results.push({...row,testcase:'authored: '+row.name,seed:variant.seed});
      }
      return {passed:results.every(r => r.passed),results,...(authored?{authored}:{})};
    }
  }
  const api = {Engine,learnerSource,casttext,quote,testAnswerNote,written};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.CTMMaximaQuestions = api;
})(globalThis);
