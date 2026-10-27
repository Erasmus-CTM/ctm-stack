// SPDX-License-Identifier: AGPL-3.0-or-later
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {compileIR} from '../../_extensions/ctm-stack/native/author-compiler.mjs';

function question(text, variables='x:1;') {
  return {variables, inputs: [], prts: [], qtests: [], questiontext: text,
    generalfeedback: '', specificfeedback: '', questionnote: ''};
}

test('literal upstream markers cannot collide with compiler static strings', () => {
  const source='A sufficiently long static prefix {@x@} literal //CT2S0//';
  const compiled=compileIR(question(source));
  assert.ok(compiled.texts.questiontext.includes(' literal //CT2S0//'));
  assert.ok(Object.keys(compiled.statics).every(key=>!source.includes(key)));
  assert.ok(Object.keys(compiled.statics).every(key=>key.startsWith('//CTM_STATIC_')));
});

test('large exact author integers survive the JavaScript parser', () => {
  const value='90071992547409931234567890123456789';
  const compiled=compileIR(question('{@x@}', 'x:'+value+';'));
  assert.ok(compiled.variables.statement.includes(value));
});

test('absent feedback and question notes compile as empty strings', () => {
  const compiled=compileIR(question('Question {@x@}'));
  assert.equal(compiled.texts.generalfeedback,'""');
  assert.equal(compiled.texts.specificfeedback,'""');
  assert.equal(compiled.texts.questionnote,'""');
});

test('literal question-test decimals preserve raw precision', () => {
  const model=question('Question {@x@}');
  model.qtests=[{inputs:{ans:'17.50'}}];
  const compiled=compileIR(model);
  assert.ok(compiled.testInputs.includes('"17.50"'));
  assert.ok(!compiled.testInputs.includes('string(17.50)'));
});

test('inline mathematics closes before the next expression', () => {
  for(const source of [String.raw`\({@x@}\) outside {@x@}`, '$ {@x@} $ outside {@x@}']) {
    const compiled=compileIR(question(source));
    assert.match(compiled.texts.questiontext,/ct2_latex\(_ct2_tmp,"",_ct2_simp\)/);
    assert.match(compiled.texts.questiontext,/ct2_latex\(_ct2_tmp,"i",_ct2_simp\)/);
  }
});

test('author execution and scope mutation fail closed', () => {
  for(const source of ['x:system("id");', 'x:load("evil");', 'x:kill(all);',
      'ctm_score:1;', 'x::1;', 'f(x):=x;', 'x:assume(y>0);',
      'x:map(kill,[a]);', 'x:map(\'system,["id"]);', 'x:ctm_score;']) {
    assert.throws(()=>compileIR(question('{@x@}',source)),undefined,source);
  }
});

test('random callbacks are tracked for seeds and rejected in feedback',()=>{
  const compiled=compileIR(question('Question {@x@}','x:map(rand,[5,6]);'));
  assert.equal(compiled.variables.random,true);
  const model=question('Question {@x@}');
  model.prts=[{name:'p',feedbackvariables:'r:map(rand,[5]);',nodes:[]}];
  assert.throws(()=>compileIR(model),/random callbacks/);
});

test('strings cannot smuggle evaluator or random callbacks through pure calls',()=>{
  for(const source of ['a:subst("eval_string",sin,sin("2+3"));',
    'a:subst("parse_string",sin,sin("2+3"));',
    'a:subst("rand",sin,sin(5));','a:subst("random",sin,sin(5));',
    'a:map("eval_string",["2+3"]);','a:ev(1,parse_string);',
    'a:subst("unknown_function",sin,sin("2+3"));'])
    assert.throws(()=>compileIR(question('{@a@}',source)),/unsupported/);
});

test('function authority uses an explicit allowlist including every callback position',()=>{
  const lisp='"(progn (defun ctmx () 42) (ctmx))"';
  for(const source of [
    `s:[${lisp}];a:map(eval_string_lisp,s);`,
    `s:[${lisp},${lisp}];a:sort(s,eval_string_lisp);`,
    `a:map(?eval_string_lisp,[${lisp}]);`,
    `a:?eval_string_lisp(${lisp});`,
    `f:eval_string_lisp;a:map(f,[${lisp}]);`,
    `f:eval_string_lisp;a:f(${lisp});`,
    `f:[eval_string_lisp];a:map(first(f),[${lisp}]);`,
    `f:["eval_string_lisp"];a:map(first(f),[${lisp}]);`,
    `f:concat("eval_string","_lisp");a:map(f,[${lisp}]);`,
    `f:sconcat("eval_string","_lisp");a:map(f,[${lisp}]);`,
    `a:subst(eval_string_lisp,sin,sin(${lisp}));`,
    `a:map(subst,[[1,x,x]]);`,
    `a:ev(1,eval_string_lisp);`,
    `a:substinpart(eval_string_lisp,sin(${lisp}),0);`,
    `f:lambda([x],x);a:map(f,[1]);`,
    `a:map(lambda([sin],map(sin,[${lisp}])),[eval_string_lisp]);`,
    `a:makelist(map(sin,[${lisp}]),sin,[eval_string_lisp]);`,
    `a:'map(sin,[1]);`,
  ])assert.throws(()=>compileIR(question('{@a@}',source)),undefined,source);
});

test('ordinary strings remain data in variables, answers, labels and lambda collections',()=>{
  for(const label of ['none','red','true','real','all','max','e','eval_string','eval_string_lisp']){
    const source=`s:["${label}"];a:map(lambda([t],t),s);b:subst("${label}",x,x);c:ev("${label}");`;
    const compiled=compileIR(question('{@a@}',source));
    assert.ok(compiled.variables.statement.includes('"'+label+'"'),label);
  }
  const model=question('Question {@"red"@}');model.inputs=[{name:'ans',teacher:'"none"'}];
  assert.equal(compileIR(model).inputTeachers.ans,'"none"');
});
