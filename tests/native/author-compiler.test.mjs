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

test('inline mathematics closes before the next expression', () => {
  for(const source of [String.raw`\({@x@}\) outside {@x@}`, '$ {@x@} $ outside {@x@}']) {
    const compiled=compileIR(question(source));
    assert.match(compiled.texts.questiontext,/ct2_latex\(_ct2_tmp,"",_ct2_simp\)/);
    assert.match(compiled.texts.questiontext,/ct2_latex\(_ct2_tmp,"i",_ct2_simp\)/);
  }
});

test('author execution and scope mutation fail closed', () => {
  for(const source of ['x:system("id");', 'x:load("evil");', 'x:kill(all);',
      'ctm_score:1;', 'x::1;', 'f(x):=x;', 'x:assume(y>0);']) {
    assert.throws(()=>compileIR(question('{@x@}',source)),undefined,source);
  }
});
