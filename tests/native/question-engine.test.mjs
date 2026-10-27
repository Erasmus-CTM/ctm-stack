// SPDX-License-Identifier: AGPL-3.0-or-later
import assert from 'node:assert/strict';
import test from 'node:test';
import {createRequire} from 'node:module';
const {testAnswerNote}=createRequire(import.meta.url)('../../_extensions/ctm-stack/native/question-engine.js');

test('question test notes use ordered subsequences with explicit anchoring',()=>{
  for(const [expected,actual,passed] of [
    ['end',['start','end'],true],['start',['start','end'],false],
    ['start | end',['AT note','start','intermediate','end'],true],
    ['[ start | end ]',['AT note','start','end'],false],
    ['( start )',['AT note','start','end'],true],
    ['[ start | end ]',['start','end'],true],
    ['end | start',['start','end'],false],['a | a',['a'],false],
    ['()',['anything'],true],['NULL',[],true],['NULL',['x'],false],['',[],false],
  ])assert.equal(testAnswerNote(expected,actual),passed,JSON.stringify([expected,actual]));
});
